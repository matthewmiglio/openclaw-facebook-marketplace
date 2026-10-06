---
name: message-seller
description: Message the seller of a Facebook Marketplace listing, given a listing URL or name. Starts a new chat if we've never contacted them, or sends a follow-up in the existing chat. Use when the user wants to contact, reply to, make an offer to, or follow up with a seller.
argument-hint: <listing url or name> [message text]
---

# Message a seller

Target: $ARGUMENTS

Commands run from the repo root as `PYTHONIOENCODING=utf-8 python src/cli.py <command> 2>/dev/null`, one at a time (the browser profile opens in only one window).

## 1. Find the listing

- **URL given** (`facebook.com/marketplace/item/<id>`): use it.
- **Name given:** run `lookup "<name>"`. It searches the local database: listings from past searches and chats copied by `/read-messages`. One match: use it. Several: show them (title and URL) and ask which. None: ask for the URL, or offer to search with the `marketplace` skill's `search` command.

## 2. Get the context

Run `listing <url>`.
- `sold: true`: tell the user and stop.
- `already_messaged: true`: run `replies <url>` and show the last few messages, so the follow-up fits the conversation (and so you can see whether the seller has answered).

## 3. Agree on the exact text

- If the user gave the message, use it word for word.
- If not, draft one: short, friendly, plain, no em dashes. Make an offer only if the user named a price.
- **Show the final text and wait for an explicit yes before sending.** Any edit means showing it again. Approval covers one message to one seller only.

## 4. Send

Run `message <url> "<text>"`. It picks the route itself: the listing's message box for first contact, or the existing chat for a follow-up.

| Result | Meaning |
|---|---|
| `sent` | Done. Run `replies <url>` and check that the last message is ours. |
| `failed` | Nothing confirmed sent. Read `data/page_dumps/message_failed.html` to see why before retrying. Never resend blindly; it may have gone through. |
| `rate_limited` | Facebook's new-chat limit. Stop and tell the user. Don't retry today. |
| `sold` | The listing sold. |
