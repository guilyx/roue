# Security policy

## Supported versions

Security fixes go into the latest release. Roue is young: please upgrade to
the newest version before reporting.

| Version | Supported |
|---|---|
| 0.1.x | ✓ |

## Reporting a vulnerability

Please **don't open a public issue**. Use GitHub's private reporting:
[**Report a vulnerability**](https://github.com/guilyx/roue/security/advisories/new).

Include what you did, what happened, and the output of `roue --version` and
`roue doctor`. We'll acknowledge within a few days, keep you posted, and
credit you in the release notes unless you'd rather stay anonymous.

## Threat model, briefly

What Roue promises:

- **Files never leave your machine.** Roue makes no network requests, has no
  accounts and sends no telemetry. A conversion that talks to the network is
  a bug.
- **Nothing is overwritten or deleted.** Results get a free name
  (`photo (2).jpg`); undo moves files to the trash.
- **No shell.** Tools are run with argument lists, never through a shell, so
  file names can't inject commands.

What it relies on:

- **Conversion tools.** Roue feeds your files to FFmpeg, libvips,
  ImageMagick, Ghostscript, Pandoc and LibreOffice. A malicious file can
  target bugs in those tools, so keep them updated through your
  distribution. Ghostscript runs with `-dSAFER`.
- **Your presets.** Presets using the `command` backend run the command they
  contain. Roue only loads presets shipped with the app and files in *your
  own* `~/.config/roue/presets` folder, so only add preset files you have
  read and trust (the same as any shell script).
- **Your session.** The panel accepts actions over the session D-Bus, like
  every GTK application. Anything that can talk to your session bus can
  already run programs as you.

Out of scope: vulnerabilities in the external tools themselves (report them
upstream), and attacks that need an already-compromised user account.
