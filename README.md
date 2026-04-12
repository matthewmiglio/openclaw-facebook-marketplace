# OpenClaw — Facebook Marketplace Agent

Autonomous agent that interacts with Facebook Marketplace via natural language prompts. Tell it what to buy, it searches, evaluates, and messages sellers.

```
you: "find 15 wireless keyboards under $50 in Portland, message sellers asking if available today"
agent: Searching... found 23 results → filtered to 15 → scored → messaged 12 sellers
```

## Architecture

```
┌─────────────────────────────────────────────────┐
│                  CLI Prompt                      │
│         "find 10 PS5 controllers..."             │
└──────────────────┬──────────────────────────────┘
                   │
         ┌─────────▼──────────┐
         │   Prompt Parser    │  ← Mistral via Ollama
         │  (NL → structured) │
         └─────────┬──────────┘
                   │
         ┌─────────▼──────────┐
         │   Playwright       │  ← Real Chromium browser
         │  (search, scroll,  │     with your FB session
         │   extract DOM +    │
         │   screenshot imgs) │
         └─────────┬──────────┘
                   │
         ┌─────────▼──────────┐
         │   Vision           │  ← Moondream via Ollama
         │  (identify what's  │     (local vision model)
         │   in the photos)   │
         └─────────┬──────────┘
                   │
         ┌─────────▼──────────┐
         │   Scorer           │  ← Mistral via Ollama
         │  (rank listings,   │     uses text + image
         │   filter junk)     │     descriptions
         └─────────┬──────────┘
                   │
         ┌─────────▼──────────┐
         │   Messenger        │  ← Mistral composes,
         │  (compose + send)  │     Playwright sends
         └─────────┬──────────┘
                   │
         ┌─────────▼──────────┐
         │   SQLite            │  ← Listings, messages,
         │  (persistence)      │     session history
         └────────────────────┘
```

## Stack

| Layer | Tool |
|---|---|
| Text LLM | Ollama + Mistral (local) |
| Vision LLM | Ollama + Moondream (local) |
| Browser | Playwright (Chromium) |
| Orchestrator | Python |
| Storage | SQLite |

## Setup

1. **Install Ollama** — https://ollama.com, then:
   ```
   ollama pull mistral
   ollama pull moondream
   ```

2. **Install Python deps:**
   ```
   pip install playwright ollama
   playwright install chromium
   ```

3. **First run** — log into Facebook:
   ```
   python src/main.py login
   ```
   A browser opens. Log in manually, then close the browser. The session persists for future runs.

## Usage

**Login (one-time setup):**
```
python src/main.py login
```

**Interactive mode:**
```
python src/main.py
```

**One-shot:**
```
python src/main.py "find 10 PS5 controllers under $40, message sellers asking if available"
```

**Example prompts:**
```
"search for 15 wireless keyboards under $50 in Portland"
"find cheap mountain bikes under $200 within 10 miles, message sellers"
"look for iPhone 14 Pro cases, message the 5 cheapest sellers asking for bulk pricing"
```
