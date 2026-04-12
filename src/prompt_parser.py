import json
import time
import ollama

SYSTEM_PROMPT = """You are a prompt parser for a Facebook Marketplace agent.
Given a user's natural language request, extract a structured JSON intent.

Return ONLY valid JSON with these fields:
{
  "product": "what to search for",
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
{"product": "wireless keyboard", "max_price": 50, "min_price": null, "location": "Portland", "radius_miles": null, "quantity": 15, "action": "search_and_message", "message_intent": "ask if available today", "condition": "any", "exclusions": null}

User: "search for cheap mountain bikes under $200 within 10 miles"
{"product": "mountain bike", "max_price": 200, "min_price": null, "location": null, "radius_miles": 10, "quantity": 10, "action": "search", "message_intent": null, "condition": "any", "exclusions": null}

User: "find 4 Nintendo Switch consoles under $150, skip anything that looks like just accessories"
{"product": "Nintendo Switch console", "max_price": 150, "min_price": null, "location": null, "radius_miles": null, "quantity": 4, "action": "search", "message_intent": null, "condition": "any", "exclusions": "skip listings that are just accessories, cases, or parts — only actual consoles"}
"""


def parse_prompt(user_prompt: str, model: str = "mistral") -> dict:
    print(f"  [parser] Sending to {model}...")
    print(f"  [parser] Prompt: \"{user_prompt}\"")
    t0 = time.time()

    response = ollama.chat(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        format="json",
    )

    elapsed = time.time() - t0
    text = response["message"]["content"]
    tokens = response.get("eval_count", "?")
    print(f"  [parser] Model responded in {elapsed:.1f}s ({tokens} tokens)")
    print(f"  [parser] Raw output: {text}")

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

    # Fix inconsistency: if message_intent is set but action is just "search", upgrade it
    if intent.get("message_intent") and intent["action"] == "search":
        intent["action"] = "search_and_message"
        print(f"  [parser] Fixed action: message_intent was set but action was 'search' -> 'search_and_message'")

    print(f"  [parser] Parsed intent: {json.dumps(intent, indent=2)}")
    return intent
