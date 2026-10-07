"""Playwright-based browser automation for Facebook Marketplace.

Handles launching a persistent Chromium session (preserving Facebook login),
searching for listings, extracting listing data and images, and sending
messages to sellers. Uses randomized delays to mimic human behaviour.
"""

import json
import os
import asyncio
import random
import re
import tempfile
from playwright.async_api import async_playwright, Page, BrowserContext
import colors as c

PROFILE_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "browser_profile")
MARKETPLACE_URL = "https://www.facebook.com/marketplace"
DUMP_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "page_dumps")


async def dump_html(page: Page, name: str):
    """Save the page's current HTML to data/page_dumps/<name>.html, overwriting the last one.

    These are what to read when a selector stops matching and needs fixing.
    """
    try:
        os.makedirs(DUMP_DIR, exist_ok=True)
        with open(os.path.join(DUMP_DIR, f"{name}.html"), "w", encoding="utf-8") as f:
            f.write(f"<!-- {page.url} -->\n" + await page.content())
    except Exception as e:
        c.error(f"Could not save page HTML ({name}): {e}")


async def launch_browser(headless=False) -> tuple:
    """Launch a persistent Chromium browser with a saved profile (keeps your FB login)."""
    os.makedirs(PROFILE_DIR, exist_ok=True)
    pw = await async_playwright().start()
    context = await pw.chromium.launch_persistent_context(
        PROFILE_DIR,
        headless=headless,
        # The default headless build (chromium-headless-shell) can't read this profile and
        # crashes; the full Chromium build in headless mode can.
        channel="chromium",
        viewport={"width": 1280, "height": 900},
        args=["--disable-blink-features=AutomationControlled"],
    )
    page = context.pages[0] if context.pages else await context.new_page()
    return pw, context, page


async def login_session():
    """Open the browser to Facebook so the user can log in manually. Keeps session for future runs."""
    pw, context, page = await launch_browser(headless=False)
    await page.goto("https://www.facebook.com/login", wait_until="domcontentloaded")
    print("Log into Facebook in this browser window.")
    print("When you're done, close the browser to save your session.")
    # Wait until the user closes the browser
    try:
        await context.pages[0].wait_for_event("close", timeout=0)
    except Exception:
        pass
    await context.close()
    await pw.stop()
    print("Session saved.")


async def is_logged_in(page: Page, timeout_ms: int = 15000) -> bool:
    """Open Marketplace and look for your profile picture in the top bar.

    Facebook draws it as an SVG <image> pointing at a profile-photo URL
    (fbcdn ".../t39.30808-1/..."), which only shows up when logged in.
    """
    await page.goto("https://www.facebook.com/marketplace", wait_until="domcontentloaded")
    try:
        await page.wait_for_selector('svg image[*|href*="/t39.30808-1/"]', state="attached", timeout=timeout_ms)
        return True
    except Exception:
        await dump_html(page, "login_failed")
        return False


async def human_delay(min_s=1.0, max_s=3.0):
    """Random delay to look less robotic."""
    await asyncio.sleep(random.uniform(min_s, max_s))


async def search_marketplace(page: Page, query: str, location: str = None, max_price: float = None, min_price: float = None):
    """Navigate to Marketplace and search for a product."""
    search_url = f"{MARKETPLACE_URL}/search/?query={query}"

    if min_price is not None:
        search_url += f"&minPrice={int(min_price)}"
    if max_price is not None:
        search_url += f"&maxPrice={int(max_price)}"

    await page.goto(search_url, wait_until="domcontentloaded")
    await human_delay(2, 4)


async def scroll_for_listings(page: Page, target_count: int = 10):
    """Scroll down to load more listings, return listing link elements."""
    listings = []
    max_scrolls = 15

    for _ in range(max_scrolls):
        # Facebook Marketplace listings are typically anchor tags within the search results
        links = await page.query_selector_all('a[href*="/marketplace/item/"][href*="ref=search"]')
        listings = links
        if len(listings) >= target_count:
            break
        await page.evaluate("window.scrollBy(0, 1000)")
        await human_delay(1.5, 3.0)

    return listings[:target_count]


async def check_listing_sold(page: Page) -> bool:
    """Check if the listing page shows a 'Sold' badge."""
    try:
        span = await page.query_selector('div[role="main"] span:has-text("Sold")')
        if span and await span.is_visible():
            text = await span.inner_text()
            if text.strip() == "Sold":
                return True
    except Exception:
        pass
    return False


async def check_already_messaged(page: Page) -> bool:
    """Check if the listing page shows a 'Message again' button, meaning we already contacted this seller."""
    # The page holds several "Message again" copies and the first is hidden, so match only visible ones.
    again = 'div[role="main"] [aria-label="Message again"]:visible'
    try:
        # Give the seller box a moment to render ("Message again" if contacted, else "Send seller a message")
        await page.locator(f'{again}, div[role="main"] span:has-text("Send seller a message"):visible').first.wait_for(timeout=8000)
    except Exception:
        pass
    return await page.locator(again).count() > 0


async def extract_listing_data(page: Page) -> dict:
    """Extract structured data from a listing page. Waits for FB SPA content to render."""

    # Wait for the main marketplace content to actually render (not just the shell/nav)
    # Facebook listing pages have the content inside the main role area
    try:
        await page.wait_for_selector('div[role="main"]', timeout=10000)
        # Give the SPA a moment to hydrate the listing content
        await human_delay(2, 4)
    except Exception:
        c.extractor("WARNING: main content area did not appear in 10s")
        await human_delay(3, 5)

    data = await page.evaluate("""() => {
        // Scope everything to the main content area to avoid nav/notification junk
        const main = document.querySelector('div[role="main"]');
        if (!main) return { title: null, price: null, raw_text: 'NO MAIN CONTENT FOUND' };

        // Collect all text spans inside main content only
        const spans = [...main.querySelectorAll('span')];
        const allText = spans
            .map(s => s.innerText.trim())
            .filter(t => t.length > 0 && t.length < 500);

        // Price: first span matching $ pattern inside main
        const priceText = allText.find(t => /^\\$[\\d,.]+$/.test(t));
        const price = priceText ? parseFloat(priceText.replace(/[$,]/g, '')) : null;

        // Title: look for h1 inside main first, then the first large text span
        let title = null;
        const h1 = main.querySelector('h1');
        if (h1) {
            title = h1.innerText.trim();
        }
        // If h1 is missing or looks like junk (e.g. "Notifications"), try the first
        // substantial span that isn't a price
        if (!title || title === 'Notifications' || title.length < 3) {
            title = allText.find(t =>
                t.length > 5 &&
                !t.startsWith('$') &&
                !t.match(/^\\d+$/) &&
                t !== 'Notifications' &&
                !t.includes('unread notification')
            ) || null;
        }

        // Description: collect unique text fragments from main, skip duplicates and short junk
        const seen = new Set();
        const descParts = [];
        for (const t of allText) {
            if (!seen.has(t) && t.length > 3 && t !== title && !t.startsWith('$')) {
                seen.add(t);
                descParts.push(t);
            }
            if (descParts.length >= 20) break;
        }

        // Try to find seller name — often in a link with /marketplace/profile/ or near "Seller" text
        let seller = null;
        const sellerLink = main.querySelector('a[href*="/marketplace/profile/"]');
        if (sellerLink) {
            seller = sellerLink.innerText.trim();
        }

        // Try to find location — often contains city/state patterns or "Listed in"
        let location = null;
        const locationText = allText.find(t =>
            t.includes('Listed in') || t.includes('miles away') ||
            (t.includes(',') && t.length < 50 && !t.startsWith('$'))
        );
        if (locationText) {
            location = locationText.replace('Listed in ', '');
        }

        // Condition — look for common condition strings
        let condition = null;
        const condText = allText.find(t =>
            /^(New|Used - Like New|Used - Good|Used - Fair)$/i.test(t)
        );
        if (condText) condition = condText;

        return {
            title: title,
            price: price,
            seller: seller,
            location: location,
            condition: condition,
            raw_text: descParts.join(' | '),
        };
    }""")

    return {
        "title": data.get("title"),
        "price": data.get("price"),
        "seller": data.get("seller"),
        "location": data.get("location"),
        "condition": data.get("condition"),
        "description": data.get("raw_text", ""),
        "listing_url": page.url,
    }


async def extract_listing_images(page: Page, max_images: int = 5) -> list[str]:
    """Screenshot listing product photos by clicking through the carousel. Returns list of temp file paths."""
    c.images("Extracting listing images...")

    photo_paths = []

    # Count available images via thumbnail buttons (aria-label="Thumbnail 0", "Thumbnail 1", etc.)
    thumbnails = await page.query_selector_all('div[role="main"] div[aria-label^="Thumbnail "]')
    num_images = max(len(thumbnails), 1)  # at least 1 (the main image)
    num_to_capture = min(num_images, max_images)
    c.images(f"Found {num_images} thumbnails, capturing {num_to_capture}")

    for i in range(num_to_capture):
        try:
            # Find the main displayed product image (alt starts with "Product photo of")
            main_img = await page.query_selector('div[role="main"] img[alt^="Product photo of"]')
            if not main_img or not await main_img.is_visible():
                # Fallback: largest visible image in main
                imgs = await page.query_selector_all('div[role="main"] img')
                for img in imgs:
                    box = await img.bounding_box()
                    if box and box["width"] >= 200 and box["height"] >= 200 and await img.is_visible():
                        main_img = img
                        break

            if main_img:
                tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
                tmp.close()
                await main_img.screenshot(path=tmp.name)
                photo_paths.append(tmp.name)

            # Click "View next image" to advance the carousel (if more images to capture)
            if i < num_to_capture - 1:
                next_btn = await page.query_selector('div[role="main"] div[aria-label="View next image"]')
                if next_btn and await next_btn.is_visible():
                    await next_btn.click()
                    await human_delay(0.5, 1.0)
        except Exception:
            continue

    c.images(f"Captured {len(photo_paths)} product photos")
    return photo_paths


async def check_rate_limit_popup(page: Page) -> bool:
    """Check if Facebook's 'You've reached the messaging limit' popup appeared.

    Returns True if the rate-limit popup is detected (and dismisses it).
    """
    try:
        popup = await page.query_selector('text="You\'ve reached the messaging limit"')
        if popup and await popup.is_visible():
            c.messenger("RATE LIMIT DETECTED — Facebook messaging limit reached")
            # Dismiss the popup by clicking OK
            ok_button = await page.query_selector('div[aria-label="OK"]')
            if ok_button and await ok_button.is_visible():
                await ok_button.click()
                await human_delay(1, 2)
            return True
    except Exception:
        pass
    return False


async def send_marketplace_message(page: Page, message: str) -> str:
    """Message the seller of the open listing and save the page HTML as it was afterward.

    A first message goes through the listing's message dialog; if we already have a
    conversation with this seller, it goes into that chat as a follow-up.
    Returns: "sent", "failed", or "rate_limited"
    """
    if await check_already_messaged(page):
        result = await _send_followup(page, message)
    else:
        result = await _send_marketplace_message(page, message)
    await dump_html(page, f"message_{result}")
    return result


async def _open_chat(page: Page):
    """Open the existing chat with this listing's seller via "Message again". Returns its text box, or None."""
    btn = page.locator('div[role="main"] [aria-label="Message again"]:visible').first
    if not await btn.count():
        return None
    await btn.click()
    # Other chat popups (other sellers) stay docked across page loads, so pick the box
    # labeled "Write to <seller> · <this listing's title>", never just the last one.
    title = (await page.locator('div[role="main"] h1').first.inner_text()).strip()
    box = page.locator(f'div[role="textbox"][contenteditable="true"][aria-label$={json.dumps(" · " + title, ensure_ascii=False)}]').last
    try:
        await box.wait_for(state="visible", timeout=15000)
    except Exception:
        return None
    await human_delay(2, 3)  # let the message history load
    return box


async def _send_followup(page: Page, message: str) -> str:
    """Type a follow-up into the existing chat with the seller and press Enter."""
    c.messenger("Already talking to this seller, sending as a follow-up...")
    box = await _open_chat(page)
    if not box:
        c.messenger("Could not open the existing chat")
        return "failed"
    await box.click()
    await page.keyboard.type(message, delay=30)
    await human_delay(1, 2)
    await page.keyboard.press("Enter")
    await human_delay(2, 3)
    if await check_rate_limit_popup(page):
        return "rate_limited"
    c.messenger("Follow-up sent!")
    return "sent"


async def read_conversation(page: Page) -> list[dict]:
    """Read the chat with the open listing's seller, oldest first: [{"time", "sender", "text"}].

    Returns [] if we've never messaged this seller. Facebook labels each chat bubble
    "Enter, Message sent 4:01 PM by Lucas: <text>", which is what this parses.
    """
    if not await check_already_messaged(page):
        return []
    # Scope to this seller's chat popup; other sellers' popups may be docked on the page too.
    box = await _open_chat(page)
    if not box:
        return []
    chat = box.locator('xpath=ancestor::div[.//*[contains(@aria-label, "Message sent ")]][1]')
    messages = await _parse_bubbles(chat)
    await dump_html(page, "conversation")
    return messages


async def _parse_bubbles(page) -> list[dict]:
    """Parse every chat bubble on the page ("Enter, Message sent 4:01 PM by Lucas: <text>"), oldest first."""
    labels = await page.locator('[aria-label*="Message sent "]').evaluate_all("els => els.map(e => e.getAttribute('aria-label'))")
    messages, seen = [], set()
    for label in labels:
        m = re.search(r"Message sent (.+?) by (.+?): (.*)", label, re.S)
        if m and label not in seen:
            seen.add(label)
            messages.append({"time": m.group(1).replace(" ", " "), "sender": m.group(2), "text": m.group(3)})
    return messages


def clean_url(href: str) -> str:
    """Strip tracking params: https://www.facebook.com/marketplace/item/<id>/"""
    m = re.search(r"/marketplace/item/(\d+)", href or "")
    return f"https://www.facebook.com/marketplace/item/{m.group(1)}/" if m else href


MESSENGER_URL = "https://www.facebook.com/messages/t/"


async def list_marketplace_threads(page: Page, limit: int = 50) -> list[str]:
    """Open Messenger's Marketplace folder and return chat URLs, newest first.

    Messenger groups all Marketplace chats under one "Marketplace" row in the chat list;
    clicking it shows the individual chats.
    """
    await page.goto(MESSENGER_URL, wait_until="domcontentloaded")
    grid = page.locator('div[aria-label="Chats"][role="grid"]')
    await grid.wait_for(timeout=20000)
    await human_delay(2, 3)
    # The "Enter your PIN to restore your chats" box was dismissed on this profile (Oct 6 2026,
    # "Don't restore messages"). If it ever comes back, a click sent straight to the element
    # still gets through it.
    await grid.locator('div[role="row"]').filter(has_text="Marketplace").first.locator('[role="button"]').first.dispatch_event("click")
    await human_delay(3, 4)
    await dump_html(page, "messenger_marketplace")

    links = page.locator('div[role="grid"] a[href*="/messages/t/"]')
    urls = []
    for _ in range(15):
        for h in await links.evaluate_all("els => els.map(e => e.href)"):
            h = h.split("?")[0]
            if h not in urls:
                urls.append(h)
        if len(urls) >= limit or not await links.count():
            break
        # More chats load as the list scrolls; stop once a scroll adds nothing
        before = await links.count()
        await links.last.scroll_into_view_if_needed()
        await human_delay(1.5, 2.5)
        if await links.count() == before:
            break
    return urls[:limit]


async def read_thread(page: Page, url: str) -> dict:
    """Open one Messenger chat and return {thread_id, title, listing_url, messages}.

    Scrolls up until no older messages load, so long chats come back whole.
    """
    await page.goto(url, wait_until="domcontentloaded")
    bubbles = page.locator('[aria-label*="Message sent "]')
    try:
        await bubbles.first.wait_for(state="attached", timeout=20000)
    except Exception:
        pass

    count = -1
    for _ in range(20):
        if await bubbles.count() == count:
            break
        count = await bubbles.count()
        try:
            if count:
                await bubbles.first.scroll_into_view_if_needed(timeout=5000)
        except Exception:
            count = -1  # the bubble re-rendered mid-scroll; count again next pass
        await human_delay(1, 2)

    heading = page.locator('h3:has-text("Conversation titled")')
    title = (await heading.first.inner_text()).replace("Conversation titled ", "").strip() if await heading.count() else ""
    details = page.locator('a[aria-label="See details"][href*="/marketplace/item/"]')
    listing = clean_url(await details.first.get_attribute("href")) if await details.count() else None
    m = re.search(r"/messages/t/(\d+)", url)
    await dump_html(page, "messenger_thread")
    return {"thread_id": m.group(1) if m else url, "title": title, "listing_url": listing,
            "messages": await _parse_bubbles(page)}


async def _send_marketplace_message(page: Page, message: str) -> str:
    """Click the Message button on a listing page, which opens a dialog, then type and send.

    Facebook's flow:
    1. Listing page has a visible "Message" or "Send seller a message" area
    2. Clicking it opens a dialog (aria-label="Message <name>", role="dialog")
    3. Dialog has a textarea and quick-reply buttons
    4. Dialog has a "Send message" button (aria-disabled until text is typed)

    Returns: "sent", "failed", or "rate_limited"
    """
    c.messenger("Looking for Message button on listing page...")

    # Step 1: Check if a message dialog is already open
    dialog = await page.query_selector('div[role="dialog"][aria-label^="Message "]')
    if dialog and await dialog.is_visible():
        c.messenger("Message dialog already open")
    else:
        # Click the "Message" button to open the dialog
        msg_button = await page.query_selector('div[role="main"] div[role="button"][aria-label="Message"]')
        if not msg_button:
            msg_button = await page.query_selector('div[role="main"] div[role="button"]:has-text("Message")')
        if not msg_button:
            # Try the "Send seller a message" span area
            msg_button = await page.query_selector('div[role="main"] span:has-text("Send seller a message")')

        if not msg_button:
            c.messenger("No Message button found on page")
            return "failed"

        is_visible = await msg_button.is_visible()
        if not is_visible:
            c.messenger("Message button found but not visible")
            return "failed"

        c.messenger("Clicking Message button...")
        await msg_button.click()
        await human_delay(2, 3)

        # Step 2: Wait for the message dialog to appear
        c.messenger("Waiting for message dialog...")
        try:
            # Try the specific marketplace message dialog first
            dialog = await page.wait_for_selector('div[role="dialog"][aria-label^="Message "]', timeout=15000)
        except Exception:
            try:
                # Fallback: any dialog
                dialog = await page.wait_for_selector('div[role="dialog"]', timeout=5000)
            except Exception:
                if await check_rate_limit_popup(page):
                    return "rate_limited"
                c.messenger("Message dialog did not appear")
                return "failed"

    c.messenger("Dialog opened")

    # Step 3: Find the textarea inside the dialog and type our message
    textarea = await dialog.query_selector('textarea')
    if not textarea:
        c.messenger("No textarea found in dialog")
        return "failed"

    # Wait briefly for textarea to be interactive
    await human_delay(0.5, 1.0)

    is_visible = await textarea.is_visible()
    if not is_visible:
        textareas = await dialog.query_selector_all('textarea')
        for ta in textareas:
            if await ta.is_visible():
                textarea = ta
                is_visible = True
                break

    if not is_visible:
        c.messenger("No visible textarea in dialog")
        return "failed"

    c.messenger("Found textarea, typing message...")
    await textarea.click()
    await human_delay(0.3, 0.6)
    await textarea.fill("")
    await human_delay(0.3, 0.6)
    await textarea.fill(message)
    await human_delay(1.0, 2.0)

    # Step 4: Click the Send button — it starts aria-disabled="true" and enables after typing
    send_button = await dialog.query_selector('div[aria-label="Send message"][role="button"]')
    if not send_button:
        send_button = await dialog.query_selector('div[aria-label^="Send message"]')
    if not send_button:
        send_button = await dialog.query_selector('div[role="button"]:has-text("Send")')

    if send_button and await send_button.is_visible():
        # Check if the button is still disabled — wait a moment for it to enable
        is_disabled = await send_button.get_attribute("aria-disabled")
        if is_disabled == "true":
            c.messenger("Send button disabled, waiting for it to enable...")
            await human_delay(1.0, 2.0)

        c.messenger("Clicking Send button...")
        await send_button.click()
        await human_delay(1, 2)
    else:
        c.messenger("No Send button found, pressing Enter...")
        await textarea.press("Enter")
        await human_delay(1, 2)

    if await check_rate_limit_popup(page):
        return "rate_limited"

    c.messenger("Message sent!")
    return "sent"
