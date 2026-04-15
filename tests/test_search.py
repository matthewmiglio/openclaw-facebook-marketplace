"""Test harness for Facebook Marketplace search.

Runs real searches against Marketplace and dumps the results (URLs, titles,
prices, descriptions) so you can eyeball whether the search is returning
relevant listings or garbage.

Usage:
    poetry run python tests/test_search.py
"""

import asyncio
import json
import os
import sys
import time

# Add src to path so we can import project modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from browser import launch_browser, search_marketplace, scroll_for_listings, extract_listing_data, human_delay


# ── Test cases ────────────────────────────────────────────────
# Each test: (search_query, max_price, min_price, expected_keywords)
# expected_keywords = words we'd expect to see in relevant results
TEST_SEARCHES = [
    {
        "query": "Even Realities G1 smart glasses",
        "max_price": 200,
        "min_price": None,
        "expect_keywords": ["even", "realities", "g1", "glasses", "smart"],
    },
    {
        "query": "Even Realities G2 smart glasses",
        "max_price": 400,
        "min_price": None,
        "expect_keywords": ["even", "realities", "g2", "glasses", "smart"],
    },
    {
        "query": "PlayStation 5 controller",
        "max_price": 50,
        "min_price": None,
        "expect_keywords": ["ps5", "playstation", "controller", "dualsense"],
    },
]


def relevance_check(title: str, description: str, keywords: list[str]) -> dict:
    """Check how many expected keywords appear in the listing text."""
    text = f"{title} {description}".lower()
    hits = [kw for kw in keywords if kw.lower() in text]
    misses = [kw for kw in keywords if kw.lower() not in text]
    return {
        "hits": hits,
        "misses": misses,
        "hit_count": len(hits),
        "total_keywords": len(keywords),
        "relevant": len(hits) >= 2,  # at least 2 keyword matches = probably relevant
    }


async def run_single_search(page, test: dict, search_index: int) -> dict:
    """Run one search and extract data from the first few listings."""
    query = test["query"]
    max_price = test["max_price"]
    min_price = test["min_price"]
    keywords = test["expect_keywords"]

    print(f"\n{'='*70}")
    print(f"SEARCH {search_index}: \"{query}\" (price: {min_price or 0}-{max_price or 'any'})")
    print(f"{'='*70}")

    # Search
    t0 = time.time()
    await search_marketplace(page, query=query, max_price=max_price, min_price=min_price)
    search_url = page.url
    print(f"[{time.time()-t0:.1f}s] Search URL: {search_url}")

    # Collect listing links
    t0 = time.time()
    listing_elements = await scroll_for_listings(page, target_count=8)

    hrefs = []
    for el in listing_elements:
        href = await el.get_attribute("href")
        if href:
            if href.startswith("/"):
                href = "https://www.facebook.com" + href
            hrefs.append(href)

    print(f"[{time.time()-t0:.1f}s] Found {len(hrefs)} listing links")

    # Visit each listing and extract data
    listings = []
    relevant_count = 0
    irrelevant_count = 0

    for i, href in enumerate(hrefs[:8]):  # cap at 8 per search
        print(f"\n  --- Result {i+1}/{min(len(hrefs), 8)} ---")
        print(f"  URL: {href[:70]}...")
        try:
            t0 = time.time()
            await page.goto(href, wait_until="domcontentloaded")
            await human_delay(1, 2)

            data = await extract_listing_data(page)
            elapsed = time.time() - t0

            title = data.get("title") or "(no title)"
            price = data.get("price")
            desc = data.get("description", "")
            location = data.get("location", "")

            # Relevance check
            rel = relevance_check(title, desc, keywords)

            tag = "RELEVANT" if rel["relevant"] else "IRRELEVANT"
            if rel["relevant"]:
                relevant_count += 1
            else:
                irrelevant_count += 1

            price_str = f"${price}" if price is not None else "no price"
            print(f"  [{elapsed:.1f}s] [{tag}] {title} — {price_str}")
            print(f"    Keywords matched: {rel['hits']} | Missed: {rel['misses']}")
            if desc:
                print(f"    Description: {desc[:150]}...")

            listings.append({
                "url": href,
                "title": title,
                "price": price,
                "description": desc[:300],
                "location": location,
                "relevance": tag,
                "keyword_hits": rel["hits"],
                "keyword_misses": rel["misses"],
            })

        except Exception as e:
            print(f"  ERROR: {type(e).__name__}: {e}")
            listings.append({"url": href, "error": str(e)})

    # Summary for this search
    total = relevant_count + irrelevant_count
    pct = (relevant_count / total * 100) if total > 0 else 0
    print(f"\n  SEARCH SUMMARY: {relevant_count}/{total} relevant ({pct:.0f}%)")
    if irrelevant_count > 0:
        print(f"  WARNING: {irrelevant_count} irrelevant results detected")
        irr = [l for l in listings if l.get("relevance") == "IRRELEVANT"]
        for l in irr:
            print(f"    - \"{l.get('title')}\" (${l.get('price')})")

    return {
        "query": query,
        "max_price": max_price,
        "search_url": search_url,
        "total_links": len(hrefs),
        "inspected": len(listings),
        "relevant": relevant_count,
        "irrelevant": irrelevant_count,
        "relevance_pct": pct,
        "listings": listings,
    }


async def main():
    print("Launching browser...")
    pw, context, page = await launch_browser()

    try:
        all_results = []
        for i, test in enumerate(TEST_SEARCHES):
            result = await run_single_search(page, test, i + 1)
            all_results.append(result)

        # Final report
        print(f"\n\n{'='*70}")
        print("FINAL REPORT")
        print(f"{'='*70}")
        for r in all_results:
            pct = r["relevance_pct"]
            status = "OK" if pct >= 50 else "BAD"
            print(f"  [{status}] \"{r['query']}\" — {r['relevant']}/{r['inspected']} relevant ({pct:.0f}%)")
            print(f"       Search URL: {r['search_url'][:80]}...")

        # Dump full results to JSON for inspection
        out_path = os.path.join(os.path.dirname(__file__), "_search_results.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(all_results, f, indent=2, ensure_ascii=False)
        print(f"\nFull results saved to: {out_path}")

    finally:
        await context.close()
        await pw.stop()


if __name__ == "__main__":
    asyncio.run(main())
