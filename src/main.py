"""Entry point for the OpenClaw Facebook Marketplace agent.

Supports three modes:
  - ``python main.py login``        — open a browser for manual Facebook login
  - ``python main.py <prompt>``     — run a one-shot agent command
  - ``python main.py``              — interactive REPL loop

Add ``--claude`` (or ``--claude=sonnet``) to use the Claude CLI instead of Ollama.
"""

import asyncio
import sys
from agent import run_agent
from browser import login_session

BANNER = """
 ___                    ___ _
/ _ \\ _ __  ___ _ _   / __| |__ ___ __ __
| (_) | '_ \\/ -_) ' \\ | (__| / _` \\ V  V /
\\___/| .__/\\___|_||_| \\___|_\\__,_|\\_/\\_/
     |_|
Facebook Marketplace Agent

Type your request, or 'quit' to exit.
"""


def main():
    """Parse CLI args and run the appropriate mode (login / one-shot / interactive REPL)."""
    model = "mistral"

    # --claude (Haiku) or --claude=sonnet routes all AI calls through the Claude CLI
    for arg in sys.argv[1:]:
        if arg == "--claude" or arg.startswith("--claude="):
            model = "claude" + (":" + arg.split("=", 1)[1] if "=" in arg else "")
            sys.argv.remove(arg)
            break

    # Login mode: open browser for manual FB authentication
    if len(sys.argv) > 1 and sys.argv[1] == "login":
        asyncio.run(login_session())
        return

    # One-shot command via args
    if len(sys.argv) > 1:
        prompt = " ".join(sys.argv[1:])
        print(f"\n> {prompt}\n")
        asyncio.run(run_agent(prompt, model=model))
        return

    # Interactive mode
    print(BANNER)

    while True:
        try:
            prompt = input("you: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            break

        if not prompt:
            continue
        if prompt.lower() in ("quit", "exit", "q"):
            print("Bye.")
            break

        print()
        asyncio.run(run_agent(prompt, model=model))
        print()


if __name__ == "__main__":
    main()
