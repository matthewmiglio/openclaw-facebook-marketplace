# OpenClaw: Facebook Marketplace Agent

An agent that works Facebook Marketplace for you. Tell it what to buy, and it searches, checks each listing (photos included), and messages sellers. Every AI step runs on Claude through the Claude Code CLI, on your existing Claude login.

There are two ways to use it:
- **With Claude Code (the `marketplace` skill):** ask Claude in plain English ("find me a used RX 7800 XT under $450 and draft an offer"). Claude runs the searches, reads the listings and photos itself, and sends only the messages you approve. It can also read seller replies and send follow-ups.
- **As a standalone agent (`src/main.py`):** give it one request and it runs the whole pipeline on its own: search, score, and optionally message.

```
you: "find 15 wireless keyboards under $50 in Portland, message sellers asking if available today"
agent: Searching... found 23 results → filtered to 15 → scored → messaged 12 sellers
```

Example listings the agent works through (a GPU search):

<p>
  <img src="docs/images/example-listing-rx6700.png" alt="Marketplace listing for an AMD RX 6700 10GB GPU at $200" width="49%">
  <img src="docs/images/example-listing-rx6600xt.png" alt="Marketplace listing for a PowerColor RX 6600 XT Red Devil at $180" width="49%">
</p>

## Architecture

```
┌─────────────────────────────────────────────────┐
│                  CLI Prompt                      │
│         "find 10 PS5 controllers..."             │
└──────────────────┬──────────────────────────────┘
                   │
         ┌─────────▼──────────┐
         │   Prompt Parser    │  ← Claude
         │  (NL → structured) │
         └─────────┬──────────┘
                   │
         ┌─────────▼──────────┐
         │   Playwright       │  ← Real Chromium browser
         │  (login check,     │     with your FB session
         │   search, scroll,  │
         │   extract DOM +    │
         │   screenshot imgs) │
         └─────────┬──────────┘
                   │
         ┌─────────▼──────────┐
         │   Vision           │  ← Claude
         │  (identify what's  │
         │   in the photos)   │
         └─────────┬──────────┘
                   │
         ┌─────────▼──────────┐
         │   Scorer           │  ← Claude; uses text
         │  (rank listings,   │     + image descriptions
         │   filter junk)     │
         └─────────┬──────────┘
                   │
         ┌─────────▼──────────┐
         │   Messenger        │  ← Claude composes,
         │  (compose + send)  │     Playwright sends
         └─────────┬──────────┘
                   │
         ┌─────────▼──────────┐
         │   SQLite            │  ← Listings, messages,
         │  (persistence)      │     session history
         └────────────────────┘
```

All AI calls go through `src/llm.py`, which runs the `claude` CLI in an isolated mode (no tools, no MCP servers, no project settings).

When you use the skill instead, Claude Code itself does the parsing, judging and writing, and calls `src/cli.py` only for the browser steps.

## Stack

| Layer | Tool |
|---|---|
| AI (text and vision) | Claude via the Claude Code CLI |
| Browser | Playwright (Chromium) |
| Orchestrator | Python, or Claude Code with the `marketplace` skill |
| Storage | SQLite |

## Setup

1. **Install [Claude Code](https://claude.com/claude-code)** and run `claude` once to log in. The standalone agent's AI calls are billed to that account (a fraction of a cent each on Haiku).

2. **Install dependencies** (requires [Poetry](https://python-poetry.org/docs/#installation)):
   ```
   poetry install
   poetry run playwright install chromium
   ```

3. **Log into Facebook:**
   ```
   poetry run python src/main.py login
   ```
   A browser opens. Log in by hand, then close the browser. The session is saved for future runs.

## Usage

### With Claude Code

Open Claude Code in this repo and ask for what you want. The `marketplace` skill (`.claude/skills/marketplace/`) loads automatically. Examples:
```
"find used RX 7800 XT cards under $450 and show me the best three"
"check whether I've already messaged these sellers: <links>"
"send this offer to <link>: Hi! Would you take $400 cash?"
"what did the seller of <link> say?"
```

Two more skills cover the messaging:
- **`/message-seller <url or listing name> [text]`** starts a chat with the seller, or sends a follow-up if you've already talked. Claude shows you the exact text and sends nothing until you say yes.
- **`/read-messages`** copies your recent Marketplace chats from Messenger into the local database (`conversations` and `chat_messages` tables in `data/listings.db`) and tells you which sellers are waiting on a reply.

The skills call these commands, which you can also run yourself. Each prints JSON:
```
python src/cli.py check-login
python src/cli.py search "rx 7800 xt" --max-price 450 --count 20
python src/cli.py listing <url>          # details, sold / already-messaged flags, photo screenshots
python src/cli.py message <url> "<text>" # first message, or a follow-up if you've already talked
python src/cli.py replies <url>          # the conversation with that seller
python src/cli.py sync-messages          # copy recent Marketplace chats into the local database
python src/cli.py lookup "<name>"        # find a listing or chat by title (database only, no browser)
```

Only one command can run at a time, because your Facebook profile can only be open in one browser window.

### Standalone agent

**One-shot:**
```
poetry run python src/main.py "find 10 PS5 controllers under $40, message sellers asking if available"
```

**Interactive mode:**
```
poetry run python src/main.py
```

**Pick a model:** the default is Haiku (fast and cheap). Add `--model=sonnet`, `--model=opus`, or a full model ID for stronger judgment:
```
poetry run python src/main.py --model=sonnet "find 10 PS5 controllers under $40"
```

Every run checks your Facebook login first and stops early if it has expired. It also skips sold listings and sellers you've already messaged.

**Example prompts:**
```
"search for 15 wireless keyboards under $50 in Portland"
"find cheap mountain bikes under $200 within 10 miles, message sellers"
"look for iPhone 14 Pro cases, message the 5 cheapest sellers asking for bulk pricing"
```

### Checks

- **Facebook login:** `poetry run python tests/test_login.py` prints "Logged in." or "NOT logged in".
- **Claude connection:** `poetry run python src/llm.py`.

## When Facebook changes its pages

Every run saves the last page of each kind it saw to `data/page_dumps/` (search results, listing, message attempt, conversation, failed login check). When a step stops working, those files show the page's current markup so the selector in `src/browser.py` can be fixed. The folder is gitignored because it holds your logged-in Facebook pages.
