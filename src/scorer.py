import json
import time
import ollama

SYSTEM_PROMPT = """You are a strict listing evaluator for a Facebook Marketplace buying agent.
Given a listing and the buyer's criteria, score the listing from 0 to 100 and decide if it's worth contacting.

Return ONLY valid JSON:
{
  "score": number 0-100,
  "pass": true/false,
  "reasoning": "brief explanation"
}

HARD RULES — these always result in pass: false:
- If a max price is set and the listing price EXCEEDS it, FAIL. No exceptions.
- If the listing price is $0 or says "trade only" or "free", FAIL — these are not real sales.
- If the title/description clearly does not match the product the buyer wants, FAIL.
- If the buyer specified exclusions, and the listing matches an exclusion, FAIL.
- If image descriptions are provided and they show a DIFFERENT product than what the title claims, FAIL. For example, if the title says "iPhone 14" but the images show phone cases, FAIL.

Scoring guidelines (only for listings that pass the hard rules):
- Well under budget = higher score
- Exact product match = higher score
- Good condition = higher score
- Images match the title/description = higher score
- Signs of scam (too good to be true, stock photos, vague description) = lower score or FAIL
- Images show something different than described = lower score or FAIL
"""


def score_listing(listing: dict, criteria: dict, model: str = "mistral", image_descriptions: list[str] = None) -> dict:
    title = listing.get('title', 'unknown')
    price = listing.get('price', 'unknown')
    product = criteria.get('product')
    max_price = criteria.get('max_price', 'any')
    exclusions = criteria.get('exclusions')

    image_section = "No images available"
    if image_descriptions:
        image_lines = [f"  Image {i+1}: {desc}" for i, desc in enumerate(image_descriptions)]
        image_section = "\n".join(image_lines)

    prompt = f"""Buyer wants: {product}
Max price: ${max_price}
Condition preference: {criteria.get('condition', 'any')}
Exclusions: {exclusions or 'none'}

Listing:
Title: {title}
Price: ${price}
Description: {listing.get('description', 'none')}
Location: {listing.get('location', 'unknown')}
Condition: {listing.get('condition', 'unknown')}

What the listing images show:
{image_section}
"""

    safe_title = title.encode("ascii", errors="replace").decode("ascii")
    print(f"  [scorer] Evaluating: \"{safe_title}\" @ ${price} against criteria: {product} <=${max_price}")
    if exclusions:
        print(f"  [scorer] Exclusions: {exclusions}")
    t0 = time.time()

    response = ollama.chat(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        format="json",
    )

    elapsed = time.time() - t0
    raw = response["message"]["content"]
    tokens = response.get("eval_count", "?")
    safe_raw = raw.encode("ascii", errors="replace").decode("ascii")
    print(f"  [scorer] Model responded in {elapsed:.1f}s ({tokens} tokens)")
    print(f"  [scorer] Raw output: {safe_raw}")

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

    verdict = "PASS" if result["pass"] else "FAIL"
    safe_reasoning = result['reasoning'].encode("ascii", errors="replace").decode("ascii")
    print(f"  [scorer] Verdict: {verdict} (score: {result['score']}) -- {safe_reasoning}")
    return result
