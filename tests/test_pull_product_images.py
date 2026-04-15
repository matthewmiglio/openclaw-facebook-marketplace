"""Test harness for product image extraction from a listing page.

Navigates to a hardcoded listing URL, clicks through the carousel,
and prints each product image's src URL and alt text.

Usage:
    poetry run python tests/test_pull_product_images.py <listing_url>
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from browser import launch_browser, human_delay


async def main():
    if len(sys.argv) < 2:
        print("Usage: poetry run python tests/test_pull_product_images.py <listing_url>")
        sys.exit(1)

    test_url = sys.argv[1]
    print(f"Launching browser...")
    pw, context, page = await launch_browser()

    try:
        print(f"Navigating to: {test_url}")
        await page.goto(test_url, wait_until="domcontentloaded")
        await human_delay(2, 3)

        # Count thumbnails
        thumbnails = await page.query_selector_all('div[role="main"] div[aria-label^="Thumbnail "]')
        print(f"Found {len(thumbnails)} thumbnails\n")

        seen_srcs = set()
        image_num = 0

        for i in range(max(len(thumbnails), 1)):
            # Grab the main displayed product image
            main_img = await page.query_selector('div[role="main"] img[alt^="Product photo of"]')
            if not main_img:
                print(f"  Image {i+1}: no product image found on this slide")
            else:
                src = await main_img.get_attribute("src") or "(no src)"
                alt = await main_img.get_attribute("alt") or "(no alt)"

                if src not in seen_srcs:
                    seen_srcs.add(src)
                    image_num += 1
                    print(f"  Image {image_num}:")
                    print(f"    alt:  {alt}")
                    print(f"    src:  {src}")
                    print()

            # Click next
            next_btn = await page.query_selector('div[role="main"] div[aria-label="View next image"]')
            if next_btn and await next_btn.is_visible():
                await next_btn.click()
                await human_delay(0.5, 1.0)
            else:
                break

        print(f"Total unique product images: {image_num}")

    finally:
        await context.close()
        await pw.stop()


if __name__ == "__main__":
    asyncio.run(main())
