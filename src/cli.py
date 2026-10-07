"""Command-line Marketplace actions for an agent (used by the `marketplace` Claude skill).

Each command opens the saved-login browser, does one thing, closes it, and prints
one JSON result to stdout. Progress logs go to stderr.

    python src/cli.py check-login
    python src/cli.py search "rx 7800 xt" --max-price 450 --count 20
    python src/cli.py listing <url>
    python src/cli.py message <url> "<text>"
    python src/cli.py replies <url>
    python src/cli.py sync-messages [--limit 50]
    python src/cli.py lookup "<listing name>"     (local database only, no browser)

Only one command can run at a time: the browser profile opens in one window only.
"""

import argparse
import asyncio
import contextlib
import json
import os
import re
import sys

from browser import (launch_browser, is_logged_in, search_marketplace, scroll_for_listings, check_listing_sold,
                     check_already_messaged, extract_listing_data, extract_listing_images, send_marketplace_message,
                     read_conversation, list_marketplace_threads, read_thread, clean_url, dump_html, human_delay)
from storage import get_db, save_conversation, find_listing


def parse_card(text: str) -> dict:
    """Split a search-result card's text ("$400\\nUsed 7800xt\\nCanton, MI") into price, title, location."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    is_price = lambda l: l.startswith("$") or l.lower() == "free"
    prices = [i for i, l in enumerate(lines) if is_price(l)]
    # Badges like "Just listed" come before the price; title and location come after it
    rest = lines[prices[-1] + 1:] if prices else lines
    return {"price": lines[prices[0]] if prices else None, "title": rest[0] if rest else None,
            "location": rest[-1] if len(rest) > 1 else None}


async def cmd_search(page, a):
    await search_marketplace(page, a.query, max_price=a.max_price, min_price=a.min_price)
    await dump_html(page, "search")
    out, seen = [], set()
    for el in await scroll_for_listings(page, target_count=a.count):
        url = clean_url(await el.get_attribute("href") or "")
        if url not in seen:
            seen.add(url)
            out.append({"url": url, **parse_card(await el.inner_text())})
    return out


async def open_listing(page, url):
    await page.goto(url, wait_until="domcontentloaded")
    await human_delay(1, 2)
    await dump_html(page, "listing")


async def cmd_listing(page, a):
    await open_listing(page, a.url)
    data = await extract_listing_data(page)
    data["listing_url"] = clean_url(data["listing_url"])
    data["sold"] = await check_listing_sold(page)
    data["already_messaged"] = await check_already_messaged(page)
    data["image_paths"] = [] if data["sold"] else await extract_listing_images(page, max_images=a.images)
    return data


async def cmd_message(page, a):
    await open_listing(page, a.url)
    if await check_listing_sold(page):
        return {"result": "sold"}
    return {"result": await send_marketplace_message(page, a.text)}


async def cmd_replies(page, a):
    await open_listing(page, a.url)
    return {"messages": await read_conversation(page)}


async def cmd_sync(page, a):
    """Copy recent Marketplace chats from Messenger into the local database."""
    db = get_db()
    synced = []
    for url in await list_marketplace_threads(page, limit=a.limit):
        try:
            t = await read_thread(page, url)
        except Exception as e:
            synced.append({"url": url, "error": f"{type(e).__name__}: {e}"})
            continue
        new = save_conversation(db, t["thread_id"], t["title"], t["listing_url"], t["messages"])
        last = t["messages"][-1] if t["messages"] else None
        synced.append({"title": t["title"], "listing_url": t["listing_url"], "messages": len(t["messages"]),
                       "new": new, "last": f'{last["sender"]}: {last["text"]}' if last else None})
        await human_delay(1, 2)
    return {"chats": synced}


async def run(a):
    # Headless by default. `message` stays visible because sending hasn't been tested headless;
    # set MP_HEADED=1 to watch any command.
    headless = a.cmd != "message" and os.environ.get("MP_HEADED") != "1"
    pw, context, page = await launch_browser(headless=headless)
    try:
        if not await is_logged_in(page):
            return {"error": "not_logged_in", "fix": "Run `python src/main.py login`, log in, close the window."}
        if a.cmd == "check-login":
            return {"logged_in": True}
        return await {"search": cmd_search, "listing": cmd_listing, "message": cmd_message, "replies": cmd_replies,
                      "sync-messages": cmd_sync}[a.cmd](page, a)
    finally:
        await context.close()
        await pw.stop()


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check-login")
    s = sub.add_parser("search")
    s.add_argument("query")
    s.add_argument("--max-price", type=float)
    s.add_argument("--min-price", type=float)
    s.add_argument("--count", type=int, default=20)
    l = sub.add_parser("listing")
    l.add_argument("url")
    l.add_argument("--images", type=int, default=5)
    m = sub.add_parser("message")
    m.add_argument("url")
    m.add_argument("text")
    r = sub.add_parser("replies")
    r.add_argument("url")
    sm = sub.add_parser("sync-messages")
    sm.add_argument("--limit", type=int, default=50)
    lk = sub.add_parser("lookup")
    lk.add_argument("name")
    a = p.parse_args()

    if a.cmd == "lookup":
        found = {}
        for r in find_listing(get_db(), a.name):
            found.setdefault(clean_url(r["url"]), {**r, "url": clean_url(r["url"])})
        print(json.dumps(list(found.values()), indent=1, ensure_ascii=False))
        return

    # Keep stdout clean for the JSON result; the browser helpers print progress
    with contextlib.redirect_stdout(sys.stderr):
        result = asyncio.run(run(a))
    print(json.dumps(result, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    assert parse_card("$400\nUsed 7800xt graphics card\nCanton, MI") == \
        {"price": "$400", "title": "Used 7800xt graphics card", "location": "Canton, MI"}
    assert parse_card("Just listed\n$335\n$400\nRX 6800\nNovi, MI") == \
        {"price": "$335", "title": "RX 6800", "location": "Novi, MI"}
    assert clean_url("https://www.facebook.com/marketplace/item/123/?ref=search&x=1") == \
        "https://www.facebook.com/marketplace/item/123/"
    main()
