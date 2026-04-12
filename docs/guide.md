# OpenClaw — Facebook Marketplace Agent

## Project Goal

Build a **fully autonomous agent** that interacts with Facebook Marketplace via natural language prompts. You tell it what to do in plain English — it goes and does it.

**Example prompt:**
> "Go search for 15 wireless keyboards under $50 in Portland, then message those sellers asking if they can sell today"

The agent parses your intent, drives the browser, finds listings, filters them, and messages sellers — all from a single command. Think Claude Code, but for Facebook Marketplace.

---

## Interaction Model

This works like a CLI chat — you type a prompt, the agent executes autonomously:

```
you:   "find 10 PS5 controllers under $40 within 20 miles, message sellers asking for availability"
agent: Searching Marketplace for "PS5 controller" ... found 23 results
       Filtering: under $40, within 20 miles ... 12 match
       Scoring top 10 by relevance ...
       Messaging 10 sellers: "Hi, is this still available? I can pick up today."
       Done. Sent 10 messages. Results saved to listings.db
```

The agent should:
- **Parse natural language** into structured actions (product, quantity, price cap, location, message intent)
- **Execute the full pipeline** without stopping for approval at each step
- **Report back** with a summary of what it did
- **Handle errors gracefully** — if a listing is gone or a message fails, skip it and keep going

---

## Core Capabilities

1. **Search** — Parse product name, price filters, location from your prompt. Navigate Marketplace, apply filters, scroll/paginate to collect the requested number of results.
2. **Interpret** — Score and rank listings (underpriced, within distance, likely scam, good condition, matches what you asked for). Filter out junk automatically.
3. **Account access** — Reuse your logged-in browser session (persistent local Chromium profile). You log in once, the agent reuses it.
4. **Messaging** — Compose contextually appropriate messages based on your prompt intent and send them autonomously. No approval gate — you already told it what to do.

---

## Tech Stack

| Layer | Tool | Role |
|---|---|---|
| Browser automation | **Playwright** (Python) | Drive a real Chromium session — navigate, click, fill, extract DOM |
| Reasoning / LLM | **Local model** (LLaMA, Mistral, DeepSeek, etc.) | Parse prompts, score listings, generate messages, handle edge cases |
| Orchestrator | **Python** CLI app | Agent loop: parse prompt → plan steps → execute → report |
| Storage | **SQLite** | Track listings, messages sent, seller replies, session history |
| Interface | **Terminal CLI** | Chat-style prompt input, streaming status output |

### Key architecture principle

> **Browser automation handles clicking and DOM extraction.
> The local model handles intent parsing, judgment, and writing.**

Extract structured data from the DOM first, then feed it to the model. Don't rely on vision for page understanding when selectors work.

---

## Agent Loop

```
1. You type a natural language prompt
2. LLM parses it into a structured plan:
   - product: "wireless keyboard"
   - max_price: 50
   - location: "Portland"
   - quantity: 15
   - action: "message sellers"
   - message_intent: "ask if they can sell today"
3. Browser executes the search
4. Extractor pulls structured data from each listing
5. LLM scores/filters listings against the parsed criteria
6. LLM generates a message tailored to each listing
7. Browser sends messages to qualifying sellers
8. Agent reports back: what it found, what it sent, what failed
9. Everything is logged to SQLite
```

---

## Tool API

The agent has these tools available in its loop:

```
parse_prompt(text)                   -> structured intent (product, filters, action, message_intent)
search_marketplace(query, filters)   -> list of listing URLs
open_listing(url)                    -> navigates to listing page
extract_listing()                    -> structured data (title, price, location, condition, seller, description)
score_listing(criteria)              -> pass/fail + reasoning
compose_message(listing, intent)     -> message text tailored to the listing
send_message(seller, message)        -> sends via browser, returns success/fail
log_action(action, details)          -> writes to SQLite
```

---

## Data Model

Each listing record:

| Field | Purpose |
|---|---|
| `listing_url` | Unique identifier |
| `title` | Product title |
| `price` | Listed price |
| `seller` | Seller name / profile link |
| `location` | Where the item is |
| `condition` | New / used / etc. |
| `description` | Seller's listing description |
| `timestamp_found` | When the agent first found it |
| `score` | Relevance score from LLM |
| `score_reasoning` | Why it passed/failed |
| `message_sent` | The actual message text sent |
| `message_timestamp` | When it was sent |
| `seller_reply` | Reply text (if any) |
| `seller_reply_timestamp` | When they replied |
| `status` | `found` / `messaged` / `replied` / `completed` / `dead` |

---

## Implementation Phases

### Phase 1 — Search and extract

- Accept a natural language prompt
- Parse it into structured search criteria
- Drive Marketplace search via Playwright
- Extract and store listing data
- Display results in terminal

### Phase 2 — Autonomous messaging

- Generate contextual messages from prompt intent
- Send messages to qualifying sellers automatically
- Log all outbound messages
- Report summary back to user

### Phase 3 — Conversation tracking

- Monitor for seller replies (poll inbox or watch for notifications)
- Surface replies in the CLI
- Allow follow-up prompts like "reply to everyone who responded saying I can pick up at 5pm"
- Track full conversation state per seller

### Phase 4 — Multi-goal and scheduling

- Run multiple buying goals concurrently
- Schedule recurring searches ("check for new PS5 controllers every 2 hours")
- Priority queue for high-value finds
- Notification system (terminal, desktop notification, etc.)

---

## Prompt Examples

```
"search for 15 wireless keyboards under $50 in Portland, message sellers asking if available today"

"find cheap mountain bikes under $200 within 10 miles, skip anything that looks like a scam"

"look for iPhone 14 Pro cases, message the 5 cheapest sellers asking for bulk pricing"

"reply to everyone who responded to my keyboard search — tell them I can pick up tomorrow at noon"

"show me everything you found yesterday for PS5 controllers"
```

---

## Important Nuances

### Facebook platform realities
- Marketplace UI changes frequently — selectors will break and need maintenance
- Rapid automated activity can trigger account restrictions
- The agent should pace itself with human-like delays between actions
- Use a persistent local browser profile (your real login session)

### Smart pacing
- Random delays between actions (not uniform — that looks bot-like)
- Don't message 50 sellers in 2 minutes — spread it out
- If something triggers a CAPTCHA or verification, stop and alert the user

### Error handling
- Listing removed? Skip it, note it, keep going
- Message failed to send? Retry once, then skip and log
- Search returned fewer results than requested? Report what you found
- Session expired? Alert the user to re-login

### What this is NOT
- Not a scraper — it acts on specific prompts, not bulk data collection
- Not stealth — no anti-detection tricks, just a real browser with your real account
- Not unattended 24/7 — you initiate every session with a prompt

---

## Project Structure

```
openclaw-facebook-marketplace/
  docs/
    guide.md                # this file
    chatgpt-plan.md         # original brainstorm
  src/
    main.py                 # CLI entry point — accepts prompts
    agent.py                # agent loop: parse → plan → execute → report
    prompt_parser.py        # LLM-based natural language → structured intent
    browser.py              # Playwright browser automation
    extractor.py            # DOM → structured listing data
    scorer.py               # LLM-based listing scoring / filtering
    messenger.py            # message composition + sending
    storage.py              # SQLite persistence layer
    reply_tracker.py        # monitor and surface seller replies
  config/
    settings.yaml           # pacing, model config, browser profile path
  data/
    listings.db             # SQLite database
```
