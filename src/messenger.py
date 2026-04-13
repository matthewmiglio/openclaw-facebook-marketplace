"""Compose short, human-sounding buyer messages for Facebook Marketplace listings.

Uses a local Ollama model with strict style rules (no greetings, no sign-offs,
1-2 sentences max) so the output reads like a real chat message.
"""

import time
import ollama


def safe_print(text: str):
    """Print text, replacing non-ASCII chars to avoid Windows console encoding errors."""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", errors="replace").decode("ascii"))


SYSTEM_PROMPT = """Write a Facebook Marketplace message from a buyer to a seller.

Rules:
- 1-2 sentences MAX. Super short.
- Sound like a normal person texting, not writing an email.
- NO greetings like "Hope this finds you well" or "Hello there"
- NO sign-offs like "Best regards", "Thanks!", "Looking forward to hearing from you"
- NO placeholders like [Your Name] — never sign the message
- NO emojis
- Just get to the point like a real person would in a chat message

Good examples:
- "hey is this still available? can you do $30?"
- "interested in this, is it unlocked?"
- "still have this? id grab it today if so"

Bad examples (DO NOT write like this):
- "Hi there! I hope this message finds you well. I noticed your listing..."
- "Hello, I'm interested in purchasing... Best regards, [Your Name]"

Write ONLY the message text, nothing else.
"""


def compose_message(listing: dict, message_intent: str, model: str = "mistral") -> str:
    """Generate a short, casual buyer message for a listing via Ollama.

    Args:
        listing: Extracted listing data (needs at least 'title' and 'price').
        message_intent: What the buyer wants to communicate (e.g. "ask if available").
        model: Ollama model name.

    Returns:
        The final cleaned-up message string ready to send.
    """
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

    # Strip any placeholder sign-offs the model might sneak in
    import re
    msg = re.sub(r'\n*\s*(Best|Regards|Thanks|Cheers|Sincerely|Looking forward)[,!]?\s*\n*\s*\[?Your Name\]?\s*$', '', msg, flags=re.IGNORECASE).strip()
    msg = re.sub(r'\[Your Name\]', '', msg).strip()
    msg = re.sub(r'\n{2,}', '\n', msg).strip()

    safe_print(f"  [messenger] Final message: \"{msg}\"")
    return msg
