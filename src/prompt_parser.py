"""Natural-language prompt parser that converts user requests into structured intents.

Uses Claude (via the claude CLI) to extract fields like product, price range, location,
desired action (search / message / both), and exclusions from free-form text.
"""

import json
import threading
import time
import llm
import colors as c

SYSTEM_PROMPT = """You are a prompt parser for a Facebook Marketplace agent.
Given a user's natural language request, extract a structured JSON intent.

Return ONLY valid JSON with these fields:
{
  "product": "what to search for",
  "brand_keywords": ["list", "of", "words"] — the brand name and model identifiers that MUST appear in a listing for it to be the right product. Only include words that distinguish this specific product from similar ones. Do NOT include generic category words like "glasses", "phone", "controller", "laptop", "console", etc. Include brand names, model numbers, and version identifiers.
  "max_price": number or null,
  "min_price": number or null,
  "location": "city/area or null",
  "radius_miles": number or null,
  "quantity": number (how many listings to find, default 10),
  "action": "search" | "message" | "search_and_message" | "reply" | "status",
  "message_intent": "what to say to sellers (null if action is just search)",
  "condition": "new" | "used" | "any" (default "any"),
  "exclusions": "things to skip/avoid, described in natural language (null if none)"
}

Examples:
User: "find 15 wireless keyboards under $50 in Portland, message sellers asking if available today"
{"product": "wireless keyboard", "brand_keywords": [], "max_price": 50, "min_price": null, "location": "Portland", "radius_miles": null, "quantity": 15, "action": "search_and_message", "message_intent": "ask if available today", "condition": "any", "exclusions": null}

User: "search for cheap mountain bikes under $200 within 10 miles"
{"product": "mountain bike", "brand_keywords": [], "max_price": 200, "min_price": null, "location": null, "radius_miles": 10, "quantity": 10, "action": "search", "message_intent": null, "condition": "any", "exclusions": null}

User: "find 4 Nintendo Switch consoles under $150, skip anything that looks like just accessories"
{"product": "Nintendo Switch console", "brand_keywords": ["nintendo", "switch"], "max_price": 150, "min_price": null, "location": null, "radius_miles": null, "quantity": 4, "action": "search", "message_intent": null, "condition": "any", "exclusions": "skip listings that are just accessories, cases, or parts — only actual consoles"}

User: "find Even Realities G2 smart glasses under $400"
{"product": "Even Realities G2 smart glasses", "brand_keywords": ["even", "realities", "g2"], "max_price": 400, "min_price": null, "location": null, "radius_miles": null, "quantity": 10, "action": "search", "message_intent": null, "condition": "any", "exclusions": null}

User: "find PS5 controllers under $50"
{"product": "PS5 controller", "brand_keywords": ["ps5"], "max_price": 50, "min_price": null, "location": null, "radius_miles": null, "quantity": 10, "action": "search", "message_intent": null, "condition": "any", "exclusions": null}
"""


def parse_prompt(user_prompt: str, model: str = llm.DEFAULT_MODEL) -> dict:
    """Convert a free-form user request into a structured intent dict via Claude.

    Args:
        user_prompt: Raw natural-language request from the user.
        model: Claude model name (see llm.py).

    Returns:
        Dict with keys: product, max_price, min_price, location, radius_miles,
        quantity, action, message_intent, condition, exclusions.
    """
    c.parser(f"Sending to {model}...")
    c.parser(f"Prompt: \"{user_prompt}\"")
    t0 = time.time()

    # Run the model call in a thread so we can print a live timer while waiting
    result_holder = {}

    def _call_model():
        try:
            result_holder["response"] = llm.chat(model, SYSTEM_PROMPT, user_prompt, json_mode=True)
        except Exception as e:
            result_holder["error"] = e

    thread = threading.Thread(target=_call_model)
    thread.start()
    while thread.is_alive():
        elapsed = int(time.time() - t0)
        print(f"  {c.YELLOW}[parser]{c.RESET} Parsing input prompt {elapsed}s...", end="\r")
        thread.join(timeout=1)
    print(f"  {c.YELLOW}[parser]{c.RESET} Parsing input prompt {int(time.time() - t0)}s... done")

    if "error" in result_holder:
        err = result_holder["error"]
        raise RuntimeError(f"LLM call failed ({model}): {err}") from err

    response = result_holder["response"]
    elapsed = time.time() - t0
    text = response["message"]["content"]
    tokens = response.get("eval_count", "?")
    c.parser(f"Model responded in {elapsed:.1f}s ({tokens} tokens)")
    c.parser(f"Raw output: {text}")

    intent = json.loads(text)

    # Apply defaults
    intent.setdefault("quantity", 10)
    intent.setdefault("action", "search")
    intent.setdefault("condition", "any")
    intent.setdefault("max_price", None)
    intent.setdefault("min_price", None)
    intent.setdefault("location", None)
    intent.setdefault("radius_miles", None)
    intent.setdefault("message_intent", None)
    intent.setdefault("exclusions", None)
    intent.setdefault("brand_keywords", [])

    # Fix inconsistency: if message_intent is set but action is just "search", upgrade it
    if intent.get("message_intent") and intent["action"] == "search":
        intent["action"] = "search_and_message"
        c.parser("Fixed action: message_intent was set but action was 'search' -> 'search_and_message'")

    c.parser(f"Parsed intent: {json.dumps(intent, indent=2)}")
    return intent
