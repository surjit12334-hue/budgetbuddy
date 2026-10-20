# Devpost Submission — BudgetBuddy

> Draft for the Fetch.ai / ASI:One hackathon. Copy-paste into Devpost and
> adjust to your voice.

---

## Title

**BudgetBuddy — a multi-agent personal-finance coach for ASI:One**

---

## Elevator pitch (1–2 sentences)

BudgetBuddy turns your bank statement into a conversation. Paste whatever your
bank exports — CSV, semicolons, `£` signs, messy dates — and a team of six
cooperating agents analyses it, finds forgotten subscriptions, plans your
savings goal, splits bills, and takes payment, all inside ASI:One.

---

## Inspiration

Budgeting apps assume you'll do the work: manually categorise spending, keep a
dashboard up to date, and never feed it odd data. Most people open their
banking app, feel vaguely bad, and close it.

We wanted the opposite: **paste anything, get a straight answer.** And we
wanted to build it the way the brief asks — as a genuine multi-agent system,
where each agent does one job and failures are isolated.

---

## What it does

Talk to BudgetBuddy in plain English:

- **Paste your transactions** — CSV or free text. It auto-detects delimiters
  (`,` `;` `\t` `|`), handles 9 date formats, recognises `$ € £ ₹ ¥`,
  debit/credit column pairs, and parenthesised negatives.
- **"How am I doing?"** — income, expenses, savings rate, fixed-vs-variable,
  needs-vs-wants, and deterministic insights.
- **"What subscriptions do I have?"** — finds recurring charges and flags the
  ones you've forgotten, with monthly and annual totals.
- **"I want to save $3000 by August"** — exact monthly/weekly/daily targets,
  plus concrete cut scenarios if you're short.
- **"Split this $90 dinner with Alice and Bob"** — even or uneven splits, with
  settlement minimisation so the fewest possible transfers settle everyone.
- **"How do I unlock Pro?"** — a payment request lifecycle (testnet-ready).

Everything works **without an LLM**: if Gemini is unavailable, the coach falls
back to deterministic, rule-based insights. The user never sees an error.

---

## How we built it

Two clean halves:

**The brain (`core/`)** — pure Python, fully testable offline. An intent router
(orchestrator), a hardened parser, a categoriser with an LLM fallback for
unknown merchants, an analyser, a coach, goal math, a bill splitter, a payment
lifecycle, and card builders.

**The agents (`agents/`)** — six Fetch.ai uAgents in one Bureau:

| Agent | Job |
|-------|-----|
| **host** | Serves `/submit`, detects intent, routes, composes replies |
| **ingest** | CSV / free-text → normalised transactions |
| **analyst** | Totals, savings rate, recurring detection, insights |
| **coach** | LLM-backed advice with a deterministic fallback |
| **goal** | Savings-goal what-if math |
| **splitter** | Bill splitting + settlement minimisation |

The host calls sub-agents with a **15-second timeout**. If one is dead or slow,
the host runs the same logic in-process — so the user always gets an answer.

### Privacy by design

Only **aggregate** figures (totals, category sums) are ever sent to an LLM.
Raw transaction lines never leave the machine. Sessions are stored in SQLite
and purged after 24 hours.

### The $0 stack

uAgents · Gemini free tier (optional) · Ollama (optional fallback) · SQLite ·
frankfurter.app · ngrok free · your laptop. Nothing needs a credit card.

---

## Challenges we ran into

- **Hostile real-world data.** Bank exports are ugly. We fuzzed the parser with
  1000+ random inputs and found a genuine crash — malformed CSV quoting blew up
  `csv.reader`. Fixed with a safe fallback that splits naively instead.
- **LLM call storms.** A 500-row paste with unknown merchants fired one LLM
  call *per transaction*. We capped it at 10 per paste.
- **Slow provider, impatient users.** A stalled Gemini call initially took
  141 seconds to fall back. We retuned it to give up in ~12 seconds and answer
  deterministically — a chat response must arrive in seconds, not minutes.
- **Reserved endpoints.** uAgents reserves `/submit` for envelope routing and
  silently rejects REST handlers on it. We worked around it by registering the
  handler before the agent's init flag is set.

---

## Accomplishments we're proud of

- **Hardening that found real bugs.** 45 adversarial cases + fuzz + outage
  drills, all green *after* fixing what they exposed.
- **Graceful degradation everywhere.** Kill the LLM, kill a sub-agent — the
  user still gets a useful answer. Both are covered by tests.
- **Reproducibility.** A stranger can clone the repo and run the full demo in
  under five minutes, with or without an API key.

---

## What we learned

- Multi-agent systems are only as robust as their failure paths. The
  interesting engineering is in the timeout and the fallback, not the happy path.
- Deterministic fallbacks aren't a downgrade — they're the product's backbone.
  The LLM is polish on top.
- Real data is adversarial by default.

---

## What's next

- Verified Interactive Cards once the schema is confirmed against official docs
- Live Payment Protocol on testnet → real Pro unlock
- Multi-currency FX conversion for mixed-currency statements
- Shared household budgets across sessions

---

## Built with

`uagents` · `python` · `sqlite` · `gemini-api` · `ollama` · `ngrok` · `rest`

---

## Links

- **GitHub:** https://github.com/surjit12334-hue/budgetbuddy
- **Agent Profile:** *(fill in after Phase 5)*
- **ASI:One Shared Chat:** *(fill in after Phase 7.3)*
- **Demo video:** *(fill in after Phase 7.2)*
