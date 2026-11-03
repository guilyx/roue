"""The MCP server: the protocol, each tool, cancellation, and stdout hygiene."""

from __future__ import annotations

import itertools
import json
import queue
import subprocess
import sys
import textwrap
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from roue import mcp

UPPER = (
    "id: upper\nname: Upper\nbackend: command\naccepts: text/*\noutput_ext: txt\n"
    "suffix: ' (up)'\n"
    "params: {command: [sh, -c, 'tr a-z A-Z < \"$0\" > \"$1\"', '{in}', '{out}']}\n"
)
SLOW = (
    "id: slow\nname: Slow\nbackend: command\naccepts: text/*\noutput_ext: txt\n"
    "suffix: ' (slow)'\n"
    "params: {command: [sh, -c, 'sleep 30; cp \"$0\" \"$1\"', '{in}', '{out}']}\n"
)


class Pipe:
    """Stands in for stdout: collects the server's messages, one per line."""

    def __init__(self) -> None:
        self.messages: queue.Queue[dict[str, Any]] = queue.Queue()
        self._partial = ""

    def write(self, text: str) -> int:
        self._partial += text
        while "\n" in self._partial:
            line, self._partial = self._partial.split("\n", 1)
            self.messages.put(json.loads(line))
        return len(text)

    def flush(self) -> None:
        pass


class Client:
    def __init__(self) -> None:
        self.pipe = Pipe()
        self.server = mcp.Server(self.pipe)  # type: ignore[arg-type]
        self.ids = itertools.count(1)
        self.notifications: list[dict[str, Any]] = []

    def send(self, message: dict[str, Any]) -> None:
        self.server.handle(json.dumps({"jsonrpc": "2.0", **message}))

    def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        request_id = next(self.ids)
        self.send({"id": request_id, "method": method, "params": params or {}})
        return self.response(request_id)

    def response(self, request_id: int | None, timeout: float = 30) -> dict[str, Any]:
        while True:
            message = self.pipe.messages.get(timeout=timeout)
            if "method" in message:
                self.notifications.append(message)
            elif message.get("id") == request_id:
                return message

    def call(self, name: str, **arguments: Any) -> dict[str, Any]:
        result: dict[str, Any] = self.request("tools/call", {"name": name, "arguments": arguments})[
            "result"
        ]
        return result


@pytest.fixture
def client() -> Iterator[Client]:
    c = Client()
    yield c
    c.server.close()


@pytest.fixture
def presets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Custom presets that need no conversion tools, and a text file for them."""
    preset_dir = tmp_path / "config" / "roue" / "presets"
    preset_dir.mkdir(parents=True)
    (preset_dir / "upper.yaml").write_text(UPPER)
    (preset_dir / "slow.yaml").write_text(SLOW)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    text = tmp_path / "notes.txt"
    text.write_text("hey")
    return text


@pytest.mark.parametrize(
    ("asked", "answered"),
    [("2025-06-18", "2025-06-18"), ("2024-11-05", "2024-11-05"), ("1999-01-01", "2025-11-25")],
)
def test_initialize_agrees_on_a_protocol_version(client: Client, asked: str, answered: str) -> None:
    result = client.request("initialize", {"protocolVersion": asked, "capabilities": {}})["result"]
    assert result["protocolVersion"] == answered
    assert result["capabilities"] == {"tools": {"listChanged": False}}
    assert result["serverInfo"]["name"] == "roue"
    assert "list_presets" in result["instructions"]


def test_every_tool_is_listed_with_a_strict_schema(client: Client) -> None:
    listed = client.request("tools/list")["result"]["tools"]
    assert [t["name"] for t in listed] == list(mcp.HANDLERS)
    for tool in listed:
        assert tool["inputSchema"]["type"] == "object"
        assert tool["inputSchema"]["additionalProperties"] is False
        assert tool["description"] and tool["title"] and tool["annotations"]


def test_convert_writes_next_to_the_original_and_undo_trashes_it(
    client: Client, presets: Path
) -> None:
    client.send(
        {
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "convert",
                "arguments": {"preset": "upper", "files": [str(presets)]},
                "_meta": {"progressToken": "p"},
            },
        }
    )
    result = client.response(1)["result"]
    assert result["isError"] is False
    data = result["structuredContent"]
    assert json.loads(result["content"][0]["text"]) == data
    assert data["summary"] == "1 file converted"
    out = Path(data["jobs"][0]["outputs"][0])
    assert out == presets.with_name("notes (up).txt")
    assert out.read_text() == "HEY"
    progress = [n["params"] for n in client.notifications]
    assert progress[-1] == {
        "progressToken": "p",
        "progress": 1,
        "total": 1,
        "message": "notes.txt: done",
    }

    undone = client.call("undo_last")["structuredContent"]
    assert undone == {"undone": True, "preset": "Upper", "trashed": [str(out)]}
    assert not out.exists() and presets.exists()
    assert client.call("undo_last")["structuredContent"]["undone"] is False


def test_presets_that_fit_the_files(client: Client, presets: Path) -> None:
    fits = client.call("list_presets", files=[str(presets)])["structuredContent"]["presets"]
    ids = [p["id"] for p in fits]
    assert "upper" in ids and "jpg" not in ids
    images = client.call("list_presets", group="image")["structuredContent"]["presets"]
    assert {p["group"] for p in images} == {"image"}
    assert "jpg" in [p["id"] for p in images]


def test_file_info_and_check_tools(client: Client, presets: Path) -> None:
    files = client.call("file_info", files=[str(presets), str(presets.with_name("gone.png"))])
    found, gone = files["structuredContent"]["files"]
    assert found["exists"] and found["type"] == "text/plain" and found["size_bytes"] == 3
    assert "upper" in found["presets"]
    assert gone == {
        "path": str(presets.with_name("gone.png")),
        "exists": False,
        "type": "image/png",
        "kind": "image",
        "presets": [],
    }
    report = client.call("check_tools")["structuredContent"]
    assert "ffmpeg" in [t["id"] for t in report["tools"]]
    assert report["presets_total"] >= 27


def test_a_failed_conversion_is_a_tool_error(client: Client, tmp_path: Path) -> None:
    result = client.call("convert", preset="jpg", files=[str(tmp_path / "missing.png")])
    assert result["isError"] is True
    job = result["structuredContent"]["jobs"][0]
    assert job["state"] == "failed" and "doesn't exist" in job["message"]


@pytest.mark.parametrize(
    ("arguments", "says"),
    [
        ({"preset": "nope", "files": ["/x.png"]}, "Call list_presets"),
        ({"preset": "web", "files": ["/x.png"]}, "Did you mean: webp"),
        ({"preset": "jpg", "file": ["/x.png"]}, "Unknown argument 'file'"),
        ({"preset": "jpg"}, "Missing argument 'files'"),
        ({"preset": "jpg", "files": "/x.png"}, "must be a list of paths"),
        ({"preset": "jpg", "files": []}, "at least one path"),
        ({"preset": "jpg", "files": ["/x.png"], "recursive": "yes"}, "true or false"),
    ],
)
def test_mistakes_go_back_to_the_model(
    client: Client, arguments: dict[str, Any], says: str
) -> None:
    result = client.call("convert", **arguments)
    assert result["isError"] is True
    assert says in result["content"][0]["text"]


def test_protocol_errors(client: Client) -> None:
    error = client.request("tools/call", {"name": "nope", "arguments": {}})["error"]
    assert error["code"] == mcp.INVALID_PARAMS
    assert client.request("resources/list")["error"]["code"] == mcp.METHOD_NOT_FOUND
    client.server.handle("{not json")
    assert client.response(None)["error"]["code"] == mcp.PARSE_ERROR
    client.server.handle(json.dumps([{"jsonrpc": "2.0", "id": 9, "method": "ping"}]))
    assert client.response(None)["error"]["code"] == mcp.INVALID_REQUEST
    # Notifications and responses get no answer.
    client.send({"method": "notifications/initialized"})
    client.send({"id": 99, "result": {}})
    assert client.request("ping")["result"] == {}
    assert client.pipe.messages.empty()


def test_cancelling_stops_a_running_conversion(client: Client, presets: Path) -> None:
    started = time.monotonic()
    client.send(
        {
            "id": 7,
            "method": "tools/call",
            "params": {"name": "convert", "arguments": {"preset": "slow", "files": [str(presets)]}},
        }
    )
    time.sleep(0.5)
    assert client.request("ping")["result"] == {}  # still answering while it converts
    client.send({"method": "notifications/cancelled", "params": {"requestId": 7}})
    while client.server._calls:
        assert time.monotonic() - started < 15, "the conversion kept running"
        time.sleep(0.05)
    assert client.request("ping")["result"] == {}
    assert client.pipe.messages.empty()  # a cancelled request gets no response
    assert not presets.with_name("notes (slow).txt").exists()


def test_stdout_carries_only_the_protocol(tmp_path: Path) -> None:
    """Prints and child processes during a tool call land on stderr."""
    script = textwrap.dedent(
        """
        import os, sys
        from roue import mcp
        from roue.cli import main

        real = mcp.HANDLERS["check_tools"]

        def noisy(arguments, call):
            print("stray print")
            os.system("echo stray child")
            return real(arguments, call)

        mcp.HANDLERS["check_tools"] = noisy
        sys.exit(main(["mcp"]))
        """
    )
    messages = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"capabilities": {}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "check_tools"}},
    ]
    proc = subprocess.run(
        [sys.executable, "-c", script],
        input="".join(json.dumps(m) + "\n" for m in messages),
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    replies = [json.loads(line) for line in proc.stdout.splitlines()]
    assert [r["id"] for r in replies] == [1, 2]
    assert replies[1]["result"]["isError"] is False
    assert "stray print" in proc.stderr and "stray child" in proc.stderr


def test_sigterm_stops_running_conversions(presets: Path) -> None:
    """Clients close stdin, then send SIGTERM: the server must not hang on a long job."""
    proc = subprocess.Popen(
        [sys.executable, "-m", "roue", "mcp"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert proc.stdin and proc.stdout
    call = {"name": "convert", "arguments": {"preset": "slow", "files": [str(presets)]}}
    proc.stdin.write(
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": call})
    )
    proc.stdin.write("\n")
    proc.stdin.close()  # end of input: the server finishes what's running...
    time.sleep(1)
    assert proc.poll() is None
    started = time.monotonic()
    proc.terminate()  # ...until it's told to stop
    assert proc.wait(timeout=15) == 0
    assert time.monotonic() - started < 10
    assert proc.stdout.read() == ""
    assert not presets.with_name("notes (slow).txt").exists()
