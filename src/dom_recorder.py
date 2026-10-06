"""Open the bot's browser and save the page HTML every time the DOM changes.

Usage: python dom_recorder.py
Snapshots go to data/page_dumps/recorder/<timestamp>.html. Close the window to stop.
Set CHROMIUM_EXE to launch a specific Chromium build (needed if the profile was
last opened by a newer Chromium than the installed Playwright ships).
"""
import asyncio
import hashlib
import os
from datetime import datetime
from playwright.async_api import async_playwright
from browser import PROFILE_DIR, MARKETPLACE_URL, DUMP_DIR

OUT_DIR = os.path.join(DUMP_DIR, "recorder")

# Facebook mutates the DOM constantly, so changes are debounced: one snapshot
# once the page has been quiet for DEBOUNCE_MS.
DEBOUNCE_MS = 1500
OBSERVER_JS = f"""
new MutationObserver(() => {{
    clearTimeout(window.__domRecTimer);
    window.__domRecTimer = setTimeout(() => window.__domChanged(), {DEBOUNCE_MS});
}}).observe(document, {{subtree: true, childList: true, attributes: true, characterData: true}});
"""


async def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    last_hash = {}

    async def on_change(source):
        page = source["page"]
        try:
            html = await page.content()
        except Exception:
            return  # page navigated or closed mid-read
        h = hashlib.md5(html.encode()).hexdigest()
        if last_hash.get(page) == h:
            return
        last_hash[page] = h
        name = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3] + ".html"
        with open(os.path.join(OUT_DIR, name), "w", encoding="utf-8") as f:
            f.write(f"<!-- {page.url} -->\n" + html)
        print(f"saved {name}  {page.url}", flush=True)

    async with async_playwright() as pw:
        context = await pw.chromium.launch_persistent_context(
            PROFILE_DIR,
            executable_path=os.environ.get("CHROMIUM_EXE") or None,
            headless=False,
            viewport={"width": 1280, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
        )
        await context.expose_binding("__domChanged", on_change)
        await context.add_init_script(OBSERVER_JS)  # runs on every page and navigation
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(MARKETPLACE_URL, wait_until="domcontentloaded")
        print(f"Recording to {os.path.abspath(OUT_DIR)}. Close the browser to stop.", flush=True)
        await context.wait_for_event("close", timeout=0)


if __name__ == "__main__":
    asyncio.run(main())
