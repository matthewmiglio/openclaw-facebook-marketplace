"""Listing quality scorer that decides which Marketplace results are worth pursuing.

Sends listing data (title, price, description, image descriptions) plus the
buyer's criteria to a local Ollama model, which returns a 0-100 score and a
pass/fail verdict. Hard price and scam rules are enforced in code after the
model responds.
"""

import json
import threading
import time
import ollama
import colors as c

SYSTEM_PROMPT = """You are a strict listing evaluator for a Facebook Marketplace buying agent.
Given a listing and the buyer's criteria, score the listing from 0 to 100 and decide if it's worth contacting.

Return ONLY valid JSON:
{
  "score": number 0-100,
  "pass": true/false,
  "reasoning": "brief explanation"
}

HARD RULES — these always result in pass: false:
- PRICE CHECK: The buyer's max price is their BUDGET LIMIT. The listing price is what the seller is asking. If the listing price is HIGHER than the buyer's max price, FAIL. If the listing price is LOWER, that is GOOD (under budget). Do not confuse these two numbers.
- If the listing price is $0 or says "trade only" or "free", FAIL — these are not real sales.
- PRODUCT MATCH (BE STRICT): The listing must be the SPECIFIC product the buyer wants, not just the same general category. A generic "smart glasses" listing is NOT the same as "Even Realities G2 smart glasses". A "GPU" is NOT the same as "RTX 4090". The brand and model must match. If the listing title and description do not mention the specific brand/model the buyer wants, FAIL. Vague or generic listings that COULD be the right product but don't say so = FAIL.
- If the buyer specified exclusions, and the listing matches an exclusion, FAIL.
- If image descriptions are provided and they show a DIFFERENT product than what the title claims, FAIL. For example, if the title says "iPhone 14" but the images show phone cases, FAIL.

Scoring guidelines (only for listings that pass the hard rules):
- Exact brand + model match in title = higher score
- Well under budget = higher score
- Good condition = higher score
- Images match the title/description = higher score
- Signs of scam (too good to be true, stock photos, vague description) = lower score or FAIL
- Images show something different than described = lower score or FAIL
"""


def score_listing(listing: dict, criteria: dict, model: str = "mistral", image_descriptions: list[str] = None) -> dict:
    """Score a listing against the buyer's criteria and return a pass/fail verdict.

    Args:
        listing: Extracted listing data (title, price, description, etc.).
        criteria: Parsed intent dict from the prompt parser.
        model: Ollama model name for evaluation.
        image_descriptions: Optional text descriptions of listing photos from the vision module.

    Returns:
        Dict with 'score' (0-100), 'pass' (bool), and 'reasoning' (str).
        Hard price rules are enforced in code after the model responds.
    """
    title = listing.get('title', 'unknown')
    price = listing.get('price', 'unknown')
    product = criteria.get('product')
    max_price = criteria.get('max_price', 'any')
    exclusions = criteria.get('exclusions')

    image_section = "No images available"
    if image_descriptions:
        image_lines = [f"  Image {i+1}: {desc}" for i, desc in enumerate(image_descriptions)]
        image_section = "\n".join(image_lines)

    prompt = f"""BUYER CRITERIA:
Product wanted: {product}
Buyer's max budget: ${max_price} (listings priced BELOW this are acceptable)
Condition preference: {criteria.get('condition', 'any')}
Exclusions: {exclusions or 'none'}

LISTING BEING EVALUATED:
Title: {title}
Seller's asking price: ${price}
Description: {listing.get('description', 'none')}
Location: {listing.get('location', 'unknown')}
Condition: {listing.get('condition', 'unknown')}

What the listing images show:
{image_section}
"""

    safe_title = title.encode("ascii", errors="replace").decode("ascii")
    c.scorer(f"Evaluating: \"{safe_title}\" @ ${price} against criteria: {product} <=${max_price}")
    if exclusions:
        c.scorer(f"Exclusions: {exclusions}")
    t0 = time.time()

    result_holder = {}

    def _call_scorer():
        result_holder["response"] = ollama.chat(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            format="json",
        )

    thread = threading.Thread(target=_call_scorer)
    thread.start()
    while thread.is_alive():
        elapsed = int(time.time() - t0)
        print(f"  {c.ORANGE}[scorer]{c.RESET} Evaluating {elapsed}s...", end="\r")
        thread.join(timeout=1)

    response = result_holder["response"]
    elapsed = time.time() - t0
    raw = response["message"]["content"]
    tokens = response.get("eval_count", "?")
    safe_raw = raw.encode("ascii", errors="replace").decode("ascii")
    print(f"  {c.ORANGE}[scorer]{c.RESET} Model responded in {elapsed:.1f}s ({tokens} tokens)" + " " * 20)

    result = json.loads(raw)
    result.setdefault("score", 50)
    result.setdefault("pass", True)
    result.setdefault("reasoning", "")

    # Hard override: if price exceeds max, force fail regardless of what the model said
    if max_price and max_price != 'any' and price is not None:
        try:
            if float(price) > float(max_price):
                result["pass"] = False
                result["reasoning"] = f"Price ${price} exceeds max ${max_price}. " + result["reasoning"]
        except (ValueError, TypeError):
            pass
        try:
            if float(price) == 0:
                result["pass"] = False
                result["reasoning"] = f"Price is $0 (trade/free). " + result["reasoning"]
        except (ValueError, TypeError):
            pass

    # Hard override: brand/model keywords must appear in listing
    # These are set by the parser LLM — it knows which words actually matter per product
    brand_keywords = [kw.lower() for kw in criteria.get("brand_keywords", [])]
    if brand_keywords and title:
        listing_text = f"{title} {listing.get('description', '')}".lower()
        matched = [kw for kw in brand_keywords if kw in listing_text]
        if len(matched) == 0:
            result["pass"] = False
            result["score"] = 0
            result["reasoning"] = f"Product mismatch: none of {brand_keywords} found in listing. " + result["reasoning"]

    verdict = "PASS" if result["pass"] else "FAIL"
    safe_reasoning = result['reasoning'].encode("ascii", errors="replace").decode("ascii")
    c.scorer(f"Verdict: {verdict} (score: {result['score']}) -- {safe_reasoning}")
    return result
