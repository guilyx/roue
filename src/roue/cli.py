"""The ``roue`` command.

roue                         open the drop panel (or show help without a desktop)
roue jpg photo.heic          shorthand for 'roue convert jpg photo.heic'
roue convert PRESET FILE...  convert files with a preset
roue list [--for FILE...]    list presets
roue info FILE...            what Roue sees in a file
roue doctor                  check which tools are installed
roue history / roue undo     recent conversions, and undo the last one
roue setup                   add the launcher, hotkey and Files menu
roue wheel [FILE...]         open the wheel (the hotkey runs this)
roue panel [FILE...]         open the full panel
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any, TextIO

from . import APP_NAME, WEBSITE, __version__
from .engine import tools
from .engine.backends import is_available, missing_tools
from .engine.detect import kind_of, mime_type, noun_for
from .engine.errors import PresetError, RoueError
from .engine.history import History
from .engine.presets import GROUPS, Preset, PresetRegistry, load_presets
from .engine.runner import Batch, Job, JobState, Runner, human_size
from .engine.settings import Settings
from .integrations import session

EXIT_OK, EXIT_FAILED, EXIT_USAGE, EXIT_INTERRUPTED = 0, 1, 2, 130

COMMANDS = (
    "convert",
    "list",
    "info",
    "doctor",
    "history",
    "undo",
    "setup",
    "panel",
    "wheel",
    "gui",
    "quit",
)


class Style:
    """Tiny ANSI helper that respects NO_COLOR and pipes."""

    def __init__(self, stream: TextIO):
        self.enabled = stream.isatty() and not os.environ.get("NO_COLOR")

    def _wrap(self, code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.enabled else text

    def bold(self, text: str) -> str:
        return self._wrap("1", text)

    def dim(self, text: str) -> str:
        return self._wrap("2", text)

    def green(self, text: str) -> str:
        return self._wrap("32", text)

    def red(self, text: str) -> str:
        return self._wrap("31", text)

    def yellow(self, text: str) -> str:
        return self._wrap("33", text)


def _registry(
    settings: Settings | None = None, *, include_disabled: bool = False
) -> PresetRegistry:
    registry = load_presets()
    for problem in registry.problems:
        print(f"warning: {problem}", file=sys.stderr)
    if settings and not include_disabled:
        registry = registry.without(settings.disabled_presets)
    return registry


# -- convert ---------------------------------------------------------------


class Progress:
    """Prints one line per finished file and a live status line on terminals."""

    def __init__(self, total: int, *, quiet: bool, verbose: bool, out: TextIO | None = None):
        out = out or sys.stderr
        self.total, self.quiet, self.verbose, self.out = total, quiet, verbose, out
        self.style = Style(out)
        self.live = out.isatty() and not quiet
        self.finished = 0
        self.running: dict[int, Job] = {}
        self.lock = threading.Lock()
        self._last_draw = 0.0

    def update(self, job: Job) -> None:
        with self.lock:
            if job.state == JobState.RUNNING:
                self.running[job.id] = job
                if time.monotonic() - self._last_draw > 0.1:
                    self._draw()
                return
            if not job.state.finished:
                return
            self.running.pop(job.id, None)
            self.finished += 1
            self._clear()
            if not self.quiet or job.state == JobState.FAILED:
                print(self._line(job), file=self.out)
            self._draw()

    def _line(self, job: Job) -> str:
        s = self.style
        name = job.source.name
        if job.state == JobState.DONE:
            outputs = ", ".join(p.name for p in job.outputs)
            size = s.dim(f"({human_size(job.output_bytes)})")
            line = f"{s.green('✓')} {name} → {outputs} {size}"
            if job.message:
                line += f"\n  {s.dim(job.message)}"
            return line
        if job.state == JobState.SKIPPED:
            return f"{s.yellow('-')} {name}: {job.message}"
        if job.state == JobState.CANCELLED:
            return f"{s.yellow('-')} {name}: cancelled"
        line = f"{s.red('✗')} {name}: {job.message}"
        if job.error and job.error.hint:
            line += f"\n  {job.error.hint}"
        if self.verbose and job.error and job.error.details:
            details = "\n".join("    " + ln for ln in job.error.details.splitlines()[-25:])
            line += f"\n{s.dim(details)}"
        return line

    def _clear(self) -> None:
        if self.live:
            self.out.write("\r\033[K")

    def _draw(self) -> None:
        if not self.live or not self.running:
            return
        self._last_draw = time.monotonic()
        job = next(iter(self.running.values()))
        pct = "" if job.progress is None else f" {job.progress * 100:3.0f}%"
        status = f"[{self.finished + 1}/{self.total}] {job.source.name}{pct}"
        self.out.write("\r\033[K" + self.style.dim(status[:100]))
        self.out.flush()


def _job_json(job: Job) -> dict[str, Any]:
    return {
        "source": str(job.source),
        "state": job.state.value,
        "outputs": [str(p) for p in job.outputs],
        "message": job.message,
        "input_bytes": job.input_bytes,
        "output_bytes": job.output_bytes,
    }


def cmd_convert(args: argparse.Namespace) -> int:
    settings = Settings.load()
    registry = _registry(settings, include_disabled=True)
    preset = registry.get(args.preset)
    paths = [Path(p).expanduser() for p in args.files]
    total = sum(1 for _ in paths)
    progress = Progress(total, quiet=args.quiet or args.json, verbose=args.verbose)
    runner = Runner(
        max_workers=args.jobs or settings.max_jobs or None,
        on_update=progress.update,
    )
    out_dir = Path(args.output_dir).expanduser() if args.output_dir else settings.output_path
    try:
        batch = runner.submit(
            preset,
            paths,
            recursive=args.recursive or settings.recursive_folders,
            out_dir=out_dir,
        )
        progress.total = len(batch.jobs)
        while not batch.finished:
            batch.wait(0.2)
    except KeyboardInterrupt:
        runner.cancel_all()
        runner.shutdown()
        print("\nCancelled.", file=sys.stderr)
        return EXIT_INTERRUPTED
    finally:
        runner.shutdown()
    History().record(batch)
    return _report(batch, args, progress)


def _report(batch: Batch, args: argparse.Namespace, progress: Progress) -> int:
    failed = batch.count(JobState.FAILED)
    if args.json:
        print(json.dumps({"preset": batch.preset.id, "jobs": [_job_json(j) for j in batch.jobs]}))
    elif not args.quiet and len(batch.jobs) > 1:
        print(progress.style.bold(batch.summary()), file=sys.stderr)
    if not batch.jobs and not args.json:
        print("No files to convert.", file=sys.stderr)
    if args.notify:
        from .integrations import notify

        title = f"{batch.preset.name}: {batch.summary()}"
        body = ""
        if failed:
            first = next(j for j in batch.jobs if j.state == JobState.FAILED)
            body = f"{first.source.name}: {first.message}"
        elif batch.outputs:
            body = ", ".join(p.name for p in batch.outputs[:3])
        notify.send(title, body, error=bool(failed))
    return EXIT_FAILED if failed else EXIT_OK


# -- list / info -----------------------------------------------------------


def _preset_json(preset: Preset) -> dict[str, Any]:
    return {
        "id": preset.id,
        "name": preset.name,
        "group": preset.group,
        "description": preset.description,
        "icon": preset.icon,
        "accepts": list(preset.accepts),
        "rejects": list(preset.rejects),
        "output_ext": preset.output_ext,
        "available": is_available(preset),
        "builtin": preset.builtin,
    }


def cmd_list(args: argparse.Namespace) -> int:
    settings = Settings.load()
    registry = _registry(settings, include_disabled=args.all)
    if args.files:
        presets = registry.matching_files(Path(f) for f in args.files)
    else:
        presets = registry.ordered()
    if args.group:
        presets = [p for p in presets if p.group == args.group]
    if args.json:
        print(json.dumps([_preset_json(p) for p in presets], indent=2))
        return EXIT_OK
    s = Style(sys.stdout)
    if not presets:
        print("No presets match." if args.files else "No presets.")
        return EXIT_OK
    width = max(len(p.id) for p in presets)
    current = None
    for preset in presets:
        if preset.group != current and not args.files:
            current = preset.group
            print(("\n" if current != presets[0].group else "") + s.bold(preset.group_label))
        mark = "" if is_available(preset) else s.yellow("  (needs tools: roue doctor)")
        print(f"  {preset.id:<{width}}  {preset.name:<16} {s.dim(preset.description)}{mark}")
    return EXIT_OK


def cmd_info(args: argparse.Namespace) -> int:
    registry = _registry(Settings.load())
    s = Style(sys.stdout)
    for name in args.files:
        path = Path(name).expanduser()
        mime = mime_type(path)
        print(s.bold(path.name))
        print(f"  type     {mime} ({noun_for(mime)})")
        if path.exists():
            print(f"  size     {human_size(path.stat().st_size)}")
        if kind_of(mime) in ("video", "audio") and tools.which("ffprobe") and path.exists():
            from .engine.detect import probe

            try:
                info = probe(path)
            except RoueError as exc:
                print(f"  media    {exc.message}")
            else:
                if info.duration:
                    print(f"  length   {info.duration:.1f} s")
                if info.has_video:
                    print(f"  video    {info.video_codec} {info.width}x{info.height}")
                print(f"  audio    {info.audio_codec or 'none'}")
        matches = registry.matching([mime])
        ids = ", ".join(p.id for p in matches) or "none"
        print(f"  presets  {ids}")
    return EXIT_OK


# -- doctor ----------------------------------------------------------------


def _gui_status() -> tuple[bool, str]:
    try:
        import gi

        gi.require_version("Gtk", "4.0")
        gi.require_version("Adw", "1")
        from gi.repository import Adw, Gtk
    except (ImportError, ValueError) as exc:
        return False, f"missing ({exc})"
    return True, (
        f"GTK {Gtk.get_major_version()}.{Gtk.get_minor_version()}, "
        f"libadwaita {Adw.get_major_version()}.{Adw.get_minor_version()}"
    )


def cmd_doctor(args: argparse.Namespace) -> int:
    from .integrations import desktop, gnome_shell, hotkey

    s = Style(sys.stdout)
    print(s.bold(f"{APP_NAME} {__version__}") + s.dim(" · checking your system\n"))
    missing_ids: list[str] = []
    print(s.bold("Tools"))
    for tool in tools.TOOLS.values():
        path = tools.which(tool.id)
        if path:
            print(f"  {s.green('✓')} {tool.label:<12} {s.dim(path)}")
        else:
            missing_ids.append(tool.id)
            print(f"  {s.red('✗')} {tool.label:<12} {s.dim('not installed · ' + tool.purpose)}")
    engine = tools.pdf_engine()
    pdf_line = engine or "none (Markdown → PDF goes through LibreOffice)"
    print(f"  {s.dim('·')} {'PDF engine':<12} {s.dim(pdf_line)}")

    registry = _registry(include_disabled=True)
    ready = [p for p in registry if is_available(p)]
    print(s.bold(f"\nPresets: {len(ready)} of {len(registry)} ready"))
    for preset in registry:
        missing = missing_tools(preset)
        if missing:
            needs = " + ".join(" or ".join(tools.label(t) for t in group) for group in missing)
            print(f"  {s.yellow('-')} {preset.id:<16} needs {needs}")
    if missing_ids:
        command = tools.install_command(missing_ids)
        if command:
            print(f"\n  Install everything: {s.bold(command)}")

    print(s.bold("\nDesktop"))
    ok, gui = _gui_status()
    mark = s.green("✓") if ok else s.red("✗")
    print(f"  {mark} {'Drop panel':<12} {s.dim(gui)}")
    if not ok:
        print("    Install: sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1")
    print(f"  {s.dim('·')} {'Session':<12} {s.dim(session.session_type())}")
    print(f"    {session.trigger_explanation()}")
    binding = hotkey.current_binding()
    mark = s.green("✓") if binding else s.yellow("-")
    print(f"  {mark} {'Hotkey':<12} {s.dim(binding or 'not set · run: roue setup')}")
    has_ext = desktop.desktop_targets()["nautilus"].exists() or desktop.system_installed("nautilus")
    mark = s.green("✓") if has_ext else s.yellow("-")
    detail = "installed" if has_ext else "not installed · run: roue setup"
    if not desktop.nautilus_python_available():
        detail += " (needs python3-nautilus)"
    print(f"  {mark} {'Files menu':<12} {s.dim(detail)}")
    if gnome_shell.wanted():
        state = gnome_shell.state()
        mark = s.green("✓") if state is gnome_shell.State.ACTIVE else s.yellow("-")
        detail = gnome_shell.describe(state)
        if state in (gnome_shell.State.OFF, gnome_shell.State.MISSING):
            detail += " · run: roue setup"
        print(f"  {mark} {'GNOME helper':<12} {s.dim(detail)}")
    return EXIT_OK


# -- history / undo --------------------------------------------------------


def cmd_history(args: argparse.Namespace) -> int:
    s = Style(sys.stdout)
    entries = History().entries()[: args.limit]
    if not entries:
        print("No conversions yet.")
        return EXIT_OK
    for entry in entries:
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(entry.time))
        undone = s.dim(" (undone)") if entry.undone else ""
        print(f"{s.dim(when)}  {s.bold(entry.preset_name)}  {entry.summary}{undone}")
        for output in entry.outputs[:5]:
            print(f"    {s.dim(output)}")
        if len(entry.outputs) > 5:
            print(s.dim(f"    … and {len(entry.outputs) - 5} more"))
    return EXIT_OK


def cmd_undo(args: argparse.Namespace) -> int:
    result = History().undo_last()
    if result is None:
        print("Nothing to undo.")
        return EXIT_OK
    entry, trashed = result
    print(f"Moved {len(trashed)} file(s) from '{entry.preset_name}' to the trash.")
    for path in trashed:
        print(f"  {path}")
    return EXIT_OK


# -- setup -----------------------------------------------------------------


def cmd_setup(args: argparse.Namespace) -> int:
    from .integrations import desktop, gnome_shell, hotkey

    s = Style(sys.stdout)
    if args.remove:
        removed = desktop.uninstall()
        gnome_shell.disable()
        removed += gnome_shell.uninstall()
        hotkey_removed = hotkey.remove()
        for path in removed:
            print(f"  removed {path}")
        if hotkey_removed:
            print("  removed the keyboard shortcut")
        if args.restart_files:
            desktop.restart_nautilus()
        return EXIT_OK

    command = desktop.roue_command()
    if desktop.system_installed("desktop"):
        print(f"  {s.green('✓')} launcher and D-Bus service: installed by your package")
    else:
        for item in desktop.install_desktop_files(command):
            print(f"  {s.green('✓')} {item.what}: {s.dim(str(item.path))}")
    if not args.no_nautilus:
        if not desktop.nautilus_python_available():
            print(
                f"  {s.yellow('-')} Files menu skipped: install python3-nautilus, "
                "then run roue setup again"
            )
        else:
            if desktop.system_installed("nautilus"):
                print(f"  {s.green('✓')} Files right-click menu: installed by your package")
            else:
                item = desktop.install_nautilus_extension(command)
                print(f"  {s.green('✓')} {item.what}: {s.dim(str(item.path))}")
            menu = desktop.desktop_targets(
                desktop.SYSTEM_DATA if desktop.system_installed("nautilus") else None
            )["nautilus"]
            if desktop.nautilus_started_before(menu.stat().st_mtime):
                if args.restart_files:
                    desktop.restart_nautilus()
                else:
                    print(s.dim("    Restart Files to see the menu: nautilus -q"))
    if gnome_shell.wanted() and not args.no_gnome_helper:
        if not gnome_shell.installed():
            item = gnome_shell.install()
            print(f"  {s.green('✓')} {item.what}: {s.dim(str(item.path))}")
        state = gnome_shell.enable()
        mark = s.green("✓") if state is gnome_shell.State.ACTIVE else s.yellow("-")
        print(f"  {mark} GNOME helper: {gnome_shell.describe(state)}")
    if not args.no_hotkey:
        wheel = f"{command} wheel"
        if hotkey.can_install():
            try:
                hotkey.install(wheel, args.binding)
                print(f"  {s.green('✓')} hotkey {args.binding} opens the wheel")
            except hotkey.HotkeyError as exc:
                print(f"  {s.red('✗')} hotkey: {exc}")
        else:
            print(f"  {s.yellow('-')} hotkey: set it up by hand.")
            print("    " + hotkey.manual_instructions(wheel, args.binding).replace("\n", "\n    "))
    print(f"\n{session.trigger_explanation()}")
    return EXIT_OK


# -- GUI -------------------------------------------------------------------


def _run_gui(argv: list[str]) -> int:
    try:
        from .ui import launcher

        return int(launcher.main(argv))
    except (ImportError, ValueError) as exc:
        print(
            f"The drop panel needs GTK 4 and libadwaita ({exc}).\n"
            "Install them with: sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1\n"
            "Everything else works from the terminal: roue --help",
            file=sys.stderr,
        )
        return EXIT_FAILED


def cmd_panel(args: argparse.Namespace) -> int:
    argv = ["roue"]
    if args.preferences:
        argv.append("--preferences")
    argv += [str(Path(f).expanduser().resolve()) for f in args.files]
    return _run_gui(argv)


def cmd_wheel(args: argparse.Namespace) -> int:
    files = [str(Path(f).expanduser().resolve()) for f in args.files]
    return _run_gui(["roue", "--wheel", *files])


def cmd_quit(args: argparse.Namespace) -> int:
    from .integrations import desktop

    if desktop.call_app_action("quit"):
        print("Roue stopped.")
        return EXIT_OK
    print("Roue isn't running.")
    return EXIT_OK


# -- parser ----------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="roue",
        description="Drop a file, get the file you wanted. Local, offline file conversions.",
        epilog=f"Shorthand: roue PRESET FILE... · Docs: {WEBSITE}",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    p = sub.add_parser("convert", help="convert files with a preset")
    p.add_argument("preset", help="preset id, see 'roue list'")
    p.add_argument("files", nargs="+", metavar="FILE", help="files or folders")
    p.add_argument("-o", "--output-dir", help="write results here instead of next to the originals")
    p.add_argument("-j", "--jobs", type=int, default=0, help="parallel conversions (default: CPUs)")
    p.add_argument("-r", "--recursive", action="store_true", help="include sub-folders")
    p.add_argument("--notify", action="store_true", help="show a desktop notification at the end")
    p.add_argument("--json", action="store_true", help="print results as JSON")
    p.add_argument("-q", "--quiet", action="store_true", help="only print errors")
    p.add_argument("-v", "--verbose", action="store_true", help="show tool output on errors")
    p.set_defaults(func=cmd_convert)

    p = sub.add_parser("list", help="list presets")
    p.add_argument("--for", dest="files", nargs="+", metavar="FILE", help="only presets for these")
    p.add_argument("--group", choices=list(GROUPS), help="only one group")
    p.add_argument("--all", action="store_true", help="include presets disabled in settings")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("info", help="show what Roue sees in files")
    p.add_argument("files", nargs="+", metavar="FILE")
    p.set_defaults(func=cmd_info)

    p = sub.add_parser("doctor", help="check installed tools and desktop integration")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("history", help="recent conversions")
    p.add_argument("-n", "--limit", type=int, default=10)
    p.set_defaults(func=cmd_history)

    p = sub.add_parser("undo", help="move the results of the last conversion to the trash")
    p.set_defaults(func=cmd_undo)

    p = sub.add_parser("setup", help="add the launcher, hotkey and Files menu for this user")
    p.add_argument("--binding", default="<Super><Shift>d", help="hotkey (default: Super+Shift+D)")
    p.add_argument("--no-hotkey", action="store_true", help="don't set up the hotkey")
    p.add_argument("--no-nautilus", action="store_true", help="don't add the Files menu")
    p.add_argument("--restart-files", action="store_true", help="restart Files to load the menu")
    p.add_argument(
        "--no-gnome-helper",
        action="store_true",
        help="don't turn on the GNOME helper (wheel on top, at the pointer)",
    )
    p.add_argument("--remove", action="store_true", help="undo 'roue setup'")
    p.set_defaults(func=cmd_setup)

    p = sub.add_parser("wheel", help="open the wheel (with files: at the pointer)")
    p.add_argument("files", nargs="*", metavar="FILE", help="files to convert")
    p.set_defaults(func=cmd_wheel)

    p = sub.add_parser("panel", help="open the full panel")
    p.add_argument("files", nargs="*", metavar="FILE", help="files to stage in the panel")
    p.add_argument("--preferences", action="store_true", help="open preferences")
    p.set_defaults(func=cmd_panel)

    p = sub.add_parser("quit", help="stop Roue running in the background")
    p.set_defaults(func=cmd_quit)

    # "roue gui ARGS..." (used by D-Bus activation) is handled in main(): argparse
    # can't pass through options like --gapplication-service untouched.
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args_list = list(sys.argv[1:] if argv is None else argv)
    if not args_list:
        if session.has_display():
            return _run_gui(["roue"])
        build_parser().print_help()
        return EXIT_OK
    first = args_list[0]
    if first == "gui":
        # Internal: hand raw arguments to the GTK application.
        return _run_gui(["roue", *args_list[1:]])
    if not first.startswith("-") and first not in COMMANDS and len(args_list) > 1:
        args_list = ["convert", *args_list]  # roue PRESET FILE...
    parser = build_parser()
    args = parser.parse_args(args_list)
    if not getattr(args, "func", None):
        parser.print_help()
        return EXIT_USAGE
    try:
        return int(args.func(args))
    except RoueError as exc:
        print(f"roue: {exc.message}", file=sys.stderr)
        if exc.hint:
            print(f"  {exc.hint}", file=sys.stderr)
        return EXIT_USAGE if isinstance(exc, PresetError) else EXIT_FAILED
    except KeyboardInterrupt:
        return EXIT_INTERRUPTED
    except BrokenPipeError:
        return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
