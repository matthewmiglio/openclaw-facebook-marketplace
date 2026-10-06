"""Single chat entry point that routes to a local Ollama model or the Claude CLI.

Model names starting with "claude" go to the `claude` CLI (your Claude Code
login): "claude" uses Haiku, "claude:sonnet" / "claude:opus" pick another model.
Anything else is treated as an Ollama model name.

Returns an Ollama-shaped dict ({"message": {"content": ...}, "eval_count": ...})
so callers don't care which backend answered.
"""

import base64
import json
import mimetypes
import re
import shutil
import subprocess
import tempfile
import time

import ollama

DEFAULT_CLAUDE_MODEL = "haiku"


def is_claude(model: str) -> bool:
    return model.startswith("claude")


def chat(model: str, system: str, user: str, json_mode: bool = False, images: list[str] | None = None) -> dict:
    """Send one system + user turn (optionally with image paths) and return the reply."""
    if not is_claude(model):
        msg = {"role": "user", "content": user}
        if images:
            msg["images"] = images
        messages = ([{"role": "system", "content": system}] if system else []) + [msg]
        resp = ollama.chat(model=model, messages=messages, format="json" if json_mode else "")
        return {"message": {"content": resp["message"]["content"]}, "eval_count": resp.get("eval_count", "?")}

    _, _, alias = model.partition(":")
    if json_mode:
        system += "\n\nRespond with the JSON object only. No code fences, no commentary."
    text, tokens = _claude_cli(alias or DEFAULT_CLAUDE_MODEL, system, user, images or [])
    if json_mode:
        # ponytail: grab the outermost {...}; switch to --json-schema if the model ever wraps it badly
        text = text[text.find("{"): text.rfind("}") + 1]
    return {"message": {"content": text}, "eval_count": tokens}


def _claude_cli(model: str, system: str, user: str, images: list[str]) -> tuple[str, int | str]:
    exe = shutil.which("claude")
    if not exe:
        raise RuntimeError("Claude CLI not found on PATH. Install Claude Code and run `claude` once to log in.")

    content = []
    for path in images:
        with open(path, "rb") as f:
            data = base64.b64encode(f.read()).decode("ascii")
        media_type = mimetypes.guess_type(path)[0] or "image/png"
        content.append({"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}})
    content.append({"type": "text", "text": user})
    stdin = json.dumps({"type": "user", "message": {"role": "user", "content": content}})

    # Isolated run: no tools, no MCP, no skills, no user/project settings or hooks,
    # no saved session, and a neutral cwd so no CLAUDE.md gets pulled in.
    cmd = [
        exe, "-p",
        "--model", model,
        "--system-prompt", system or "You are a helpful assistant.",
        "--input-format", "stream-json",
        "--output-format", "stream-json", "--verbose",
        "--tools", "",
        "--setting-sources", "",
        "--strict-mcp-config",
        "--disable-slash-commands",
        "--no-session-persistence",
    ]
    # Retry server-side overloads (529 / 5xx) with backoff: 15s, 30s, 60s, 120s
    for attempt in range(5):
        proc = subprocess.run(cmd, input=stdin.encode("utf-8"), capture_output=True,
                              cwd=tempfile.gettempdir(), timeout=300)
        out = proc.stdout.decode("utf-8", errors="replace")

        for line in out.splitlines():
            if line.startswith("{") and '"type":"result"' in line:
                result = json.loads(line)
                if not result.get("is_error"):
                    return result["result"].strip(), result.get("usage", {}).get("output_tokens", "?")
                msg = str(result.get("result"))
                if attempt < 4 and re.search(r"Overloaded|API Error: 5\d\d", msg):
                    break
                raise RuntimeError(f"Claude CLI error: {msg}")
        else:
            err = proc.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"Claude CLI returned no result (exit {proc.returncode}): {err or out[-500:]}")
        time.sleep(15 * 2 ** attempt)


if __name__ == "__main__":
    # Live smoke test against the Claude CLI (costs a fraction of a cent).
    r = chat("claude", "Return the user's number doubled.", '{"n": 21}', json_mode=True)
    assert 42 in json.loads(r["message"]["content"]).values(), r
    print("ok:", r)
