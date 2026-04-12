import asyncio
import json
import random
import time
from prompt_parser import parse_prompt
from browser import launch_browser, search_marketplace, scroll_for_listings, extract_listing_data, extract_listing_images, send_marketplace_message, human_delay
from scorer import score_listing
from vision import describe_listing_images, cleanup_image_files
from messenger import compose_message
from storage import get_db, save_listing, save_message, save_session


def safe_print(text: str):
    """Print with Unicode chars replaced to avoid Windows console crashes."""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", errors="replace").decode("ascii"))


def log(msg: str):
    safe_print(f"  >> {msg}")


def timestamp():
    return time.strftime("%H:%M:%S")


async def run_agent(user_prompt: str, model: str = "mistral"):
    """Main agent loop: parse prompt -> search -> extract -> score -> message -> report."""
    run_start = time.time()
    print(f"\n{'='*60}")
    print(f"[{timestamp()}] Agent started")
    print(f"{'='*60}")

    # Step 1: Parse the prompt
    print(f"\n--- Step 1: Parse prompt ---")
    t0 = time.time()
    intent = parse_prompt(user_prompt, model=model)
    print(f"[{timestamp()}] Parsing took {time.time() - t0:.1f}s total")

    product = intent['product']
    max_price = intent['max_price']
    location = intent['location']
    quantity = intent['quantity']
    price_str = f", max ${max_price}" if max_price else ""
    location_str = f", in {location}" if location else ""
    log(f"Plan: search for '{product}'{price_str}{location_str}, find {quantity} listings")

    if intent.get('exclusions'):
        log(f"Exclusions: {intent['exclusions']}")

    should_message = intent["action"] in ("message", "search_and_message")
    if should_message:
        log(f"Will message sellers: {intent['message_intent']}")
    else:
        log(f"Search only — no messaging")

    # Step 2: Launch browser and search
    print(f"\n--- Step 2: Launch browser + search ---")
    t0 = time.time()
    pw, context, page = await launch_browser()
    print(f"[{timestamp()}] Browser launched in {time.time() - t0:.1f}s")
    db = get_db()

    try:
        t0 = time.time()
        log(f"Navigating to Marketplace search: '{intent['product']}'")
        await search_marketplace(
            page,
            query=intent["product"],
            max_price=intent["max_price"],
            min_price=intent["min_price"],
        )
        print(f"[{timestamp()}] Search page loaded in {time.time() - t0:.1f}s")
        print(f"[{timestamp()}] URL: {page.url}")

        # Step 3: Collect listings
        print(f"\n--- Step 3: Scroll + collect listings ---")
        t0 = time.time()
        listing_elements = await scroll_for_listings(page, target_count=intent["quantity"])
        print(f"[{timestamp()}] Scrolling took {time.time() - t0:.1f}s — found {len(listing_elements)} links")

        # Collect hrefs before navigating
        hrefs = []
        for el in listing_elements:
            href = await el.get_attribute("href")
            if href:
                if href.startswith("/"):
                    href = "https://www.facebook.com" + href
                hrefs.append(href)

        print(f"[{timestamp()}] Collected {len(hrefs)} valid hrefs")
        for i, h in enumerate(hrefs):
            print(f"  [{i+1}] {h[:100]}")

        # Step 4: Visit each listing, extract data, score it
        print(f"\n--- Step 4: Extract + score listings ---")
        results = []
        skipped = 0
        errors = 0
        messages_sent = 0
        rate_limited = False
        last_message_time = None

        # Cooldown between messages to avoid Facebook rate limits (seconds)
        MESSAGE_COOLDOWN_MIN = 180  # 3 minutes
        MESSAGE_COOLDOWN_MAX = 300  # 5 minutes
        message_cooldown = random.uniform(MESSAGE_COOLDOWN_MIN, MESSAGE_COOLDOWN_MAX)

        for i, href in enumerate(hrefs):
            if rate_limited:
                print(f"\n  --- Listing {i+1}/{len(hrefs)} SKIPPED (rate limited) ---")
                continue
            print(f"\n  --- Listing {i+1}/{len(hrefs)} ---")
            print(f"  [browser] Navigating to: {href[:100]}")
            try:
                t0 = time.time()
                await page.goto(href, wait_until="domcontentloaded")
                await human_delay(1, 2)
                print(f"  [browser] Page loaded in {time.time() - t0:.1f}s")

                t0 = time.time()
                listing_data = await extract_listing_data(page)
                listing_data["listing_url"] = href
                safe_print(f"  [extractor] Extracted in {time.time() - t0:.1f}s:")
                safe_print(f"    title: {listing_data.get('title')}")
                safe_print(f"    price: ${listing_data.get('price')}")
                safe_print(f"    description: {listing_data.get('description', '')[:120]}...")

                # Extract and analyze listing images
                image_paths = await extract_listing_images(page)
                image_descriptions = describe_listing_images(image_paths)
                cleanup_image_files(image_paths)

                # Score it (with image descriptions)
                score_result = score_listing(listing_data, intent, model=model, image_descriptions=image_descriptions)
                listing_data["score"] = score_result["score"]
                listing_data["score_reasoning"] = score_result["reasoning"]
                listing_data["status"] = "found"

                if not score_result["pass"]:
                    listing_data["status"] = "skipped"
                    save_listing(db, listing_data)
                    skipped += 1
                    continue

                # Step 5: Message if requested
                if should_message and intent["message_intent"]:
                    # Enforce cooldown since last message (time spent searching/scoring counts toward it)
                    if last_message_time is not None:
                        elapsed = time.time() - last_message_time
                        remaining = message_cooldown - elapsed
                        if remaining > 0:
                            print(f"  [throttle] {elapsed:.0f}s since last message, waiting {remaining:.0f}s more (cooldown: {message_cooldown:.0f}s)...")
                            await asyncio.sleep(remaining)
                        else:
                            print(f"  [throttle] {elapsed:.0f}s since last message — cooldown satisfied")
                        # Pick a new random cooldown for next time
                        message_cooldown = random.uniform(MESSAGE_COOLDOWN_MIN, MESSAGE_COOLDOWN_MAX)

                    msg = compose_message(listing_data, intent["message_intent"], model=model)

                    print(f"  [browser] Sending message...")
                    t0 = time.time()
                    result = await send_marketplace_message(page, msg)
                    print(f"  [browser] Send attempt took {time.time() - t0:.1f}s — {result.upper()}")

                    if result == "sent":
                        listing_data["status"] = "messaged"
                        lid = save_listing(db, listing_data)
                        save_message(db, lid, msg)
                        messages_sent += 1
                        last_message_time = time.time()
                    elif result == "rate_limited":
                        listing_data["status"] = "rate_limited"
                        save_listing(db, listing_data)
                        rate_limited = True
                        print(f"\n  *** STOPPING — Facebook messaging limit reached after {messages_sent} messages ***")
                        print(f"  *** Remaining {len(hrefs) - i - 1} listings will be skipped ***")
                    else:
                        listing_data["status"] = "message_failed"
                        save_listing(db, listing_data)
                else:
                    save_listing(db, listing_data)

                results.append(listing_data)

            except Exception as e:
                print(f"  [ERROR] {type(e).__name__}: {e}")
                errors += 1
                continue

        # Step 6: Summary
        total_time = time.time() - run_start
        messaged = [r for r in results if r.get("status") == "messaged"]
        msg_failed = [r for r in results if r.get("status") == "message_failed"]
        rate_limited_count = [r for r in results if r.get("status") == "rate_limited"]

        print(f"\n{'='*60}")
        print(f"[{timestamp()}] AGENT RUN COMPLETE — {total_time:.1f}s total")
        print(f"{'='*60}")
        print(f"  Listings found:    {len(hrefs)}")
        print(f"  Passed scoring:    {len(results)}")
        print(f"  Skipped (low score): {skipped}")
        print(f"  Errors:            {errors}")
        if should_message:
            print(f"  Messages sent:     {len(messaged)}")
            print(f"  Messages failed:   {len(msg_failed)}")
            if rate_limited:
                print(f"  Rate limited:      YES (hit after {messages_sent} messages)")
        print(f"{'='*60}")

        for r in results:
            title = r.get('title', '?')
            price = r.get('price', '?')
            score = r.get('score', '?')
            status = r.get('status', '?')
            safe_print(f"  [{status:>14}] {title} -- ${price} (score: {score})")

        print(f"{'='*60}\n")

        # Save session
        save_session(db, user_prompt, json.dumps(intent),
                     f"Found {len(results)} listings, sent {len(messaged)} messages, {skipped} skipped, {errors} errors in {total_time:.1f}s")

    finally:
        await context.close()
        await pw.stop()
