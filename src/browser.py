"""Playwright-based browser automation for Facebook Marketplace.

Handles launching a persistent Chromium session (preserving Facebook login),
searching for listings, extracting listing data and images, and sending
messages to sellers. Uses randomized delays to mimic human behaviour.
"""

import os
import asyncio
import random
import tempfile
from playwright.async_api import async_playwright, Page, BrowserContext
import colors as c

PROFILE_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "browser_profile")
MARKETPLACE_URL = "https://www.facebook.com/marketplace"


async def launch_browser(headless=False) -> tuple:
    """Launch a persistent Chromium browser with a saved profile (keeps your FB login)."""
    os.makedirs(PROFILE_DIR, exist_ok=True)
    pw = await async_playwright().start()
    context = await pw.chromium.launch_persistent_context(
        PROFILE_DIR,
        headless=headless,
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
    """Click the Message button on a listing page, which opens a dialog, then type and send.

    Facebook's flow:
    1. Listing page has a visible "Message" button (div[aria-label="Message"])
    2. Clicking it opens a dialog (div[role="dialog"]) with the message composer
    3. Dialog has a textarea for the message
    4. Dialog has a "Send" button (div[aria-label^="Send message"])

    Returns: "sent", "failed", or "rate_limited"
    """
    c.messenger("Looking for Message button on listing page...")

    # Step 1: Click the "Message" button to open the dialog
    msg_button = await page.query_selector('div[role="main"] div[role="button"][aria-label="Message"]')
    if not msg_button:
        msg_button = await page.query_selector('div[role="main"] div[role="button"]:has-text("Message")')

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
        dialog = await page.wait_for_selector('div[role="dialog"]', timeout=10000)
    except Exception:
        # The rate-limit popup can appear instead of the message dialog
        if await check_rate_limit_popup(page):
            return "rate_limited"
        c.messenger("Message dialog did not appear")
        return "failed"

    c.messenger("Dialog opened")

    # Step 3: Find the textarea inside the dialog and clear + type our message
    textarea = await dialog.query_selector('textarea')
    if not textarea:
        c.messenger("No textarea found in dialog")
        return "failed"

    is_visible = await textarea.is_visible()
    c.messenger(f"Found textarea in dialog (visible={is_visible})")

    if not is_visible:
        # There might be multiple textareas; find the visible one
        textareas = await dialog.query_selector_all('textarea')
        for ta in textareas:
            if await ta.is_visible():
                textarea = ta
                is_visible = True
                c.messenger("Found alternative visible textarea")
                break

    if not is_visible:
        c.messenger("No visible textarea in dialog")
        return "failed"

    # Clear any pre-filled text and type our message
    await textarea.click()
    await human_delay(0.3, 0.6)
    await textarea.fill("")
    await human_delay(0.3, 0.6)
    await textarea.fill(message)
    await human_delay(0.5, 1.0)
    c.messenger("Typed message into textarea")

    # Step 4: Click the Send button inside the dialog
    send_button = await dialog.query_selector('div[aria-label^="Send message"]')
    if not send_button:
        send_button = await dialog.query_selector('div[role="button"][aria-label*="Send"]')
    if not send_button:
        send_button = await dialog.query_selector('div[role="button"]:has-text("Send")')

    if send_button and await send_button.is_visible():
        c.messenger("Clicking Send button...")
        await send_button.click()
        await human_delay(1, 2)
    else:
        # Fallback: press Enter in the textarea
        c.messenger("No Send button found, pressing Enter...")
        await textarea.press("Enter")
        await human_delay(1, 2)

    # Check if the rate-limit popup appeared after sending
    if await check_rate_limit_popup(page):
        return "rate_limited"

    c.messenger("Message sent!")
    return "sent"
