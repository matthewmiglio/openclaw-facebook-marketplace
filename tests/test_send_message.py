"""Test harness for sending a message on a listing page.

Usage:
    poetry run python tests/test_send_message.py <listing_url> <message>

Example:
    poetry run python tests/test_send_message.py "https://www.facebook.com/marketplace/item/962829479941310/" "hey is this still available?"
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from browser import launch_browser, human_delay, send_marketplace_message


async def main():
    if len(sys.argv) < 3:
        print("Usage: poetry run python tests/test_send_message.py <listing_url> <message>")
        sys.exit(1)

    url = sys.argv[1]
    message = sys.argv[2]

    print(f"Launching browser...")
    pw, context, page = await launch_browser()

    try:
        print(f"Navigating to: {url}")
        await page.goto(url, wait_until="domcontentloaded")
        await human_delay(2, 3)
        print(f"Page loaded")
        print(f"Message to send: \"{message}\"")
        print()

        result = await send_marketplace_message(page, message)
        print(f"\nResult: {result.upper()}")

        if result != "sent":
            print("\nBrowser left open for inspection. Close the browser window to exit.")
            try:
                await page.wait_for_event("close", timeout=0)
            except Exception:
                pass

    finally:
        await context.close()
        await pw.stop()


if __name__ == "__main__":
    asyncio.run(main())
