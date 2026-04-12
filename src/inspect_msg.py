"""Inspect a Facebook Marketplace listing page to understand the message UI structure."""
import asyncio
import json
from browser import launch_browser, human_delay

JS_INSPECT = """() => {
    const main = document.querySelector('div[role="main"]');
    if (!main) return {error: "no main element found"};

    // Find all buttons/links with message-related text
    const allEls = [...main.querySelectorAll('div[role="button"], a[role="button"], button, span')];
    const msgEls = allEls.map(el => ({
        tag: el.tagName,
        role: el.getAttribute('role'),
        text: el.innerText.trim().substring(0, 100),
        ariaLabel: el.getAttribute('aria-label') || '',
        visible: el.offsetParent !== null,
        rect: el.getBoundingClientRect().toJSON(),
    })).filter(el => {
        const t = (el.text + ' ' + el.ariaLabel).toLowerCase();
        return t.includes('message') || t.includes('send') || t.includes('contact') ||
               t.includes('still available') || t.includes('seller');
    });

    // Find all textareas and contenteditable divs
    const inputs = [...document.querySelectorAll('textarea, div[contenteditable="true"]')];
    const inputInfo = inputs.map(i => ({
        tag: i.tagName,
        placeholder: i.getAttribute('placeholder') || '',
        ariaLabel: i.getAttribute('aria-label') || '',
        visible: i.offsetParent !== null,
        rect: i.getBoundingClientRect().toJSON(),
        role: i.getAttribute('role') || '',
        parent: i.parentElement ? i.parentElement.className.substring(0, 60) : '',
    }));

    // Check for dialog/modal that might contain the message form
    const dialogs = [...document.querySelectorAll('div[role="dialog"]')];
    const dialogInfo = dialogs.map(d => ({
        ariaLabel: d.getAttribute('aria-label') || '',
        visible: d.offsetParent !== null,
        textPreview: d.innerText.trim().substring(0, 200),
    }));

    return {msgEls, inputInfo, dialogInfo};
}"""


async def main():
    pw, context, page = await launch_browser(headless=False)

    # Navigate to a known listing
    url = "https://www.facebook.com/marketplace/item/3895705457401911/"
    print(f"Navigating to {url}")
    await page.goto(url, wait_until="domcontentloaded")
    await human_delay(4, 5)

    # Inspect before clicking anything
    print("\n=== BEFORE clicking message button ===")
    result = await page.evaluate(JS_INSPECT)
    print("Message-related elements:")
    for el in result.get("msgEls", []):
        v = "VISIBLE" if el["visible"] else "hidden"
        print(f"  [{v}] <{el['tag']} role={el['role']}> text=\"{el['text'][:60]}\" aria=\"{el['ariaLabel'][:40]}\"")
    print("Inputs:")
    for inp in result.get("inputInfo", []):
        v = "VISIBLE" if inp["visible"] else "hidden"
        print(f"  [{v}] <{inp['tag']}> placeholder=\"{inp['placeholder']}\" aria=\"{inp['ariaLabel']}\" role=\"{inp['role']}\"")
    print("Dialogs:")
    for d in result.get("dialogInfo", []):
        v = "VISIBLE" if d["visible"] else "hidden"
        print(f"  [{v}] aria=\"{d['ariaLabel']}\" text=\"{d['textPreview'][:80]}\"")

    # Try clicking the "Send seller a message" / "Message" area
    print("\n=== Attempting to click message area ===")
    # Try multiple selectors
    selectors = [
        'div[role="main"] span:text-is("Send seller a message")',
        'div[role="main"] span:text-is("Send")',
        'div[role="main"] div[role="button"]:has-text("Send seller a message")',
        'div[role="main"] div[aria-label*="Message"]',
        'div[role="main"] div[role="button"]:has-text("Message")',
    ]

    clicked = False
    for sel in selectors:
        el = await page.query_selector(sel)
        if el:
            visible = await el.is_visible()
            print(f"  Found: {sel} (visible={visible})")
            if visible:
                await el.click()
                clicked = True
                print(f"  Clicked: {sel}")
                break
        else:
            print(f"  Not found: {sel}")

    if clicked:
        await human_delay(3, 4)

        # Inspect after clicking
        print("\n=== AFTER clicking ===")
        result2 = await page.evaluate(JS_INSPECT)
        print("Inputs now:")
        for inp in result2.get("inputInfo", []):
            v = "VISIBLE" if inp["visible"] else "hidden"
            print(f"  [{v}] <{inp['tag']}> placeholder=\"{inp['placeholder']}\" aria=\"{inp['ariaLabel']}\" role=\"{inp['role']}\"")
        print("Dialogs now:")
        for d in result2.get("dialogInfo", []):
            v = "VISIBLE" if d["visible"] else "hidden"
            print(f"  [{v}] aria=\"{d['ariaLabel']}\" text=\"{d['textPreview'][:120]}\"")

    await context.close()
    await pw.stop()

asyncio.run(main())
