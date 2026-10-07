---
name: marketplace
description: Search Facebook Marketplace, read listings (details and photos), message sellers, and read their replies, using the user's logged-in browser. Use when the user wants to find items, check or compare listings, contact sellers, send follow-ups, or see what sellers said.
---

# Facebook Marketplace

`src/cli.py` drives a real Chromium browser with the user's saved Facebook login, hidden (headless) for every command except `message`. Set `MP_HEADED=1` to show the window. Each command opens the browser, does one thing, closes it, and prints one JSON result on stdout (progress logs go to stderr, so add `2>/dev/null` to keep output clean).

Run from the repo root with `PYTHONIOENCODING=utf-8 python src/cli.py ...`.

| Command | Does | Returns |
|---|---|---|
| `check-login` | Checks the saved Facebook session | `{"logged_in": true}` or `{"error": "not_logged_in"}` |
| `search "<query>" [--max-price N] [--min-price N] [--count 20]` | Runs a Marketplace search | `[{url, price, title, location}]` |
| `listing <url> [--images 5]` | Opens one listing | `{title, price, location, condition, description, sold, already_messaged, image_paths}` |
| `message <url> "<text>"` | Messages the seller. First contact uses the listing's message box; if a chat already exists, it sends a follow-up there | `{"result": "sent" \| "failed" \| "rate_limited" \| "sold"}` |
| `replies <url>` | Reads the chat with that listing's seller | `{"messages": [{time, sender, text}]}` (empty if never messaged) |
| `sync-messages [--limit 50]` | Copies recent Marketplace chats from Messenger into the local database | `{"chats": [{title, listing_url, messages, new, last}]}` |
| `lookup "<name>"` | Finds listings and chats by title in the local database (no browser) | `[{title, url, source}]` |

Every command returns `{"error": "not_logged_in"}` if the session has expired. Tell the user to run `python src/main.py login`, log in, and close the window.

To message a seller, use `/message-seller`; to catch up on chats, use `/read-messages`.

## Rules

- **Never send a message the user hasn't approved word for word.** Draft it, show it, wait for a yes. A yes to one message doesn't cover the next.
- **One command at a time.** The browser profile can only be open in one window, so a second command started while one runs will fail. Never run them in parallel.
- **Look at the photos.** `listing` saves screenshots to `image_paths`; open them with the Read tool to check that the photos match the title (empty boxes, wrong model, a different card in the picture).
- **Judge listings yourself.** Facebook search is loose: many results are nearby models or unrelated parts. Check the model name, capacity and price against what the user asked for.
- **Search results are hidden above `--max-price`.** For near-misses, search again with a higher limit.
- **Mind the rate limit.** Facebook limits how many new sellers you can message. Space out first-contact messages by a few minutes and stop on `rate_limited`.
- **`listing` prices can be placeholders** like $6,000 or $1. Treat those as "ask the seller".

## When something breaks

Facebook changes its page markup. Every command saves the page it saw to `data/page_dumps/` (`search.html`, `listing.html`, `message_<result>.html`, `conversation.html`, `login_failed.html`); the first line of each is the page URL. When a command returns empty or wrong data, read the matching dump, find the element's current markup, and fix the selector in `src/browser.py`.
