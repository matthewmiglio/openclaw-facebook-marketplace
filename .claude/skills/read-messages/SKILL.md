---
name: read-messages
description: Copy the user's recent Facebook Marketplace chats from Messenger into the local database (data/listings.db) and summarize them. Use when the user asks to check, read, sync, or catch up on their Marketplace messages or seller replies.
argument-hint: [max chats, default 50]
---

# Read Marketplace messages

Run from the repo root (it drives the browser, so nothing else may be using it):

```
PYTHONIOENCODING=utf-8 python src/cli.py sync-messages --limit ${ARGUMENTS:-50} 2>/dev/null
```

It opens Messenger's Marketplace folder, opens each chat (newest first), scrolls to load its full history, and saves it to the local database. Running it again only adds messages it hasn't seen.

It returns `{"chats": [{title, listing_url, messages, new, last}]}`. A chat that failed to load comes back as `{url, error}`; mention it, and rerun once if there are any.

## Report back

Lead with the chats that need the user: **the seller wrote last** (`last` doesn't start with `You:`), newest first. For each, give the item, the seller, and what they said. Then list the chats waiting on the seller in one line each. Mention how many new messages were saved.

## The database

`data/listings.db`:
- `conversations(thread_id, title, listing_url, last_synced)`: title is "Seller · Listing title".
- `chat_messages(thread_id, sent_time, sender, text, first_seen)`: `sender` is "You" for the user's messages. `sent_time` is as Messenger shows it ("4:01 PM", "Mon 4:01 PM", "Oct 3, 2026, 4:01 PM"); `first_seen` is when the sync first saved it.

Use it to answer follow-up questions (what did Noor say, which sellers haven't replied) without opening the browser again.

## Notes

- The "Enter your PIN to restore your chats" box was dismissed in this browser (the user chose "Don't restore messages"). A small "Chat history is missing" banner stays in the chat list; it blocks nothing. If the full box comes back, the sync works around it.
- The sync only sees chats in Messenger's Marketplace folder in this browser. Chats started on another device before this browser was set up may be missing until the user enters their PIN here themselves.
- If the sync returns no chats, read `data/page_dumps/messenger_marketplace.html` to see what the page looked like and fix `list_marketplace_threads` in `src/browser.py`.
