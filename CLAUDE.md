# OpenClaw Facebook Marketplace

An agent that shops Facebook Marketplace for the user: it searches for products, judges listings, messages sellers, and follows the chats through to a pickup. It works by driving a real Chromium window logged in as the user.

## Lay of the land

**Skills** (`.claude/skills/`) are the main way to use the project. Each one wraps commands in `src/cli.py`:
- `marketplace`: search, read listings and photos, message sellers, read replies. Has the full command table.
- `message-seller`: contact a seller or send a follow-up.
- `read-messages`: copy recent Marketplace chats from Messenger into the local database and summarize them.

**Code** (`src/`):
- `cli.py`: one browser action per command, printing one JSON result on stdout. This is what the skills call.
- `browser.py`: all Playwright automation (login check, search, listing extraction, messaging, Messenger scraping). This is the fragile layer; see below.
- `agent.py` and `main.py`: the older end-to-end pipeline (prompt, search, score, message) with an interactive mode. `python src/main.py login` opens the browser so the user can log in by hand.
- `prompt_parser.py`, `scorer.py`, `vision.py`, `messenger.py`: AI steps (turn a request into search terms, score listings, describe photos, write messages). All AI calls go through `llm.py`, which uses the `claude` CLI.
- `storage.py`: SQLite at `data/listings.db` (listings, messages, sessions).
- `dom_recorder.py`: opens the browser and saves the page HTML every time it changes, for studying page structure by hand.
- `inspect_msg.py`: one-off script for inspecting a listing's message UI.

**Data** (`data/`, all gitignored, all private to the user):
- `browser_profile/`: the saved Facebook login. Only one browser window can use it at a time, so run browser commands one after another, never in parallel.
- `page_dumps/<step>.html`: the HTML of the page from the most recent run of each step (`search.html`, `listing.html`, `message_sent.html`, `messenger_thread.html`, and so on). Each run overwrites the previous one. The first line is a comment with the page URL.
- `listings.db`: the local database.

**Other:** `config/settings.yaml` (pacing and limits), `tests/` (scripts that exercise real browser flows), `docs/guide.md` (user guide). Python runs through Poetry (`poetry run python ...`).

## Desired behaviors

### Everything serves one goal

Every skill exists to help find products and lock in pickups within limits the user sets (price, condition, location, timing, and so on). When choosing what to do next, pick whatever moves a purchase toward a confirmed pickup without breaking those limits. Never agree to a price, commit to a time, or send a message that goes outside them; ask the user first.

### Browser automation breaks; fix it from the saved HTML

The skills sit on browser automation that reads Facebook's pages, and Facebook changes its pages often, so selectors will stop matching. That's expected. It's why every step saves the HTML of the page it was on to `data/page_dumps/`.

When a skill's browser automation fails (an error, an empty result that shouldn't be empty, a "failed" status):
1. **Read the saved HTML from the broken run** in `data/page_dumps/` and compare it with what the code in `src/browser.py` or `src/cli.py` expects.
2. **If the fix is simple** (a changed label, attribute, or selector), make it, rerun the step, and tell the user what changed.
3. **If the fix is not simple** (the page flow changed, the data isn't on the page anymore, or you aren't sure), stop working toward the goal and tell the user what broke and what you found, rather than guessing. Never retry an action that sends a message to a seller until you're sure the last attempt didn't already send.
