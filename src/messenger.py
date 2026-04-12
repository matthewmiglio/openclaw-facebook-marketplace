import time
import ollama


def safe_print(text: str):
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", errors="replace").decode("ascii"))


SYSTEM_PROMPT = """You are writing a short Facebook Marketplace message to a seller on behalf of a buyer.
Keep it casual, friendly, and brief (1-3 sentences max).
Do NOT sound robotic or like a template. Sound like a real person.
Do NOT use emojis.

You will be given:
- The listing title and price
- What the buyer wants to communicate

Write ONLY the message text, nothing else.
"""


def compose_message(listing: dict, message_intent: str, model: str = "mistral") -> str:
    title = listing.get('title', 'item')
    price = listing.get('price', '?')

    prompt = f"""Listing: {title} - ${price}
Buyer wants to say: {message_intent}
"""

    safe_print(f"  [messenger] Composing message for \"{title}\" -- intent: {message_intent}")
    t0 = time.time()

    response = ollama.chat(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    )

    elapsed = time.time() - t0
    raw = response["message"]["content"]
    tokens = response.get("eval_count", "?")
    safe_print(f"  [messenger] Model responded in {elapsed:.1f}s ({tokens} tokens)")
    safe_print(f"  [messenger] Raw output: {raw}")

    msg = raw.strip().strip('"')
    safe_print(f"  [messenger] Final message: \"{msg}\"")
    return msg
