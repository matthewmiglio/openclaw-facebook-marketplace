"""Check whether the saved browser profile is still logged into Facebook.

Opens Marketplace with the agent's profile and looks for your profile picture.
Exits 0 if logged in, 1 if not. Close any other agent browser window first
(the profile can only be open in one window at a time).

Usage:
    poetry run python tests/test_login.py
"""

import asyncio
import os
import sys

# Add src to path so we can import project modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from browser import launch_browser, is_logged_in


async def main() -> bool:
    # ponytail: headed, because the headless build crashes on this profile (it was made by full Chromium)
    pw, context, page = await launch_browser(headless=False)
    try:
        return await is_logged_in(page)
    finally:
        await context.close()
        await pw.stop()


if __name__ == "__main__":
    ok = asyncio.run(main())
    print("Logged in." if ok else "NOT logged in. Run `python src/main.py login`.")
    sys.exit(0 if ok else 1)
