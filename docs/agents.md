# AI agents

Ask your coding agent or assistant to "make these photos smaller" or "turn
this recording into a GIF", and it can use Roue to do it: same presets, same
engine, same rules as the wheel. Everything still runs on your computer.

Roue gives agents two things:

- **An MCP server**, `roue mcp`. It's part of Roue (nothing else to install) and
  works with any agent that speaks the
  [Model Context Protocol](https://modelcontextprotocol.io): Claude Code,
  Codex, VS Code, Cursor, Zed, Gemini CLI, Goose...
- **A skill** that tells the agent when to reach for Roue and which preset fits
  which request. It works with or without the MCP server: without it, the
  agent uses the `roue` command instead.

Install Roue first ([Install](install.md)): both talk to the `roue` command on
your computer.

## Claude Code

The Roue plugin bundles the MCP server and the skill. In Claude Code:

```text
/plugin install roue --marketplace guilyx/roue
```

On Claude Code older than 2.1.275, add the marketplace first:

```text
/plugin marketplace add guilyx/roue
/plugin install roue@roue
```

Then ask away: *"Convert ~/Pictures/IMG_2041.HEIC to JPG"*, *"Make
demo.mov small enough for Discord"*. Plugin updates arrive with Roue releases.

Just the MCP server, without the skill:

```sh
claude mcp add --scope user roue -- roue mcp
```

## Other agents

Codex:

```sh
codex mcp add roue -- roue mcp
```

VS Code (Copilot agent mode):

```sh
code --add-mcp '{"name": "roue", "command": "roue", "args": ["mcp"]}'
```

Cursor (`~/.cursor/mcp.json`), Gemini CLI (`~/.gemini/settings.json`) and most
other clients take the same JSON:

```json
{
  "mcpServers": {
    "roue": { "command": "roue", "args": ["mcp"] }
  }
}
```

For the skill, copy
[`plugin/skills/convert-files`](https://github.com/guilyx/roue/tree/main/plugin/skills/convert-files)
into your agent's skills folder (for Claude Code, `~/.claude/skills/`).

## Tools

| Tool | What it does |
|---|---|
| `list_presets` | The presets, or only those that fit the given files, most relevant first. Each says whether its tools are installed. |
| `file_info` | Type, size, length, codecs and resolution of files, and the presets that fit them. |
| `convert` | Convert files or folders with a preset. Takes `output_dir` and `recursive`, like the command line. Returns the paths it wrote, and sizes before and after. |
| `undo_last` | Move the files the last conversion wrote to the trash. |
| `check_tools` | Which conversion tools are installed, and the command that installs the missing ones. |

`convert` reports progress while it runs, and the agent can cancel it. Results
show up in `roue history`, so `roue undo` works on them too.

## What the agent can and can't do

- It **converts files you point it at**, with your user's permissions, like
  `roue convert` in a terminal.
- It **never overwrites anything**: results get a new name next to the
  original (or in `output_dir`), and originals are never touched.
- It **doesn't see what's in your files** through Roue: the tools return paths,
  types and sizes. The agent can still open files with its own tools, if you let it.
- It **doesn't install anything**: when a tool is missing, `check_tools` gives
  the install command, and the agent asks you to run it.

Most agents ask before running a tool the first time. `convert` and `undo_last`
change files on disk, so it's a good idea to keep that prompt for them.

## Try the server by hand

`roue mcp` speaks JSON-RPC over stdin and stdout, one message per line:

```sh
printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{}}}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"list_presets","arguments":{"files":["/path/to/photo.heic"]}}}' \
  | roue mcp
```

Or point the [MCP Inspector](https://github.com/modelcontextprotocol/inspector)
at it: `npx @modelcontextprotocol/inspector roue mcp`.
