# BudgetBuddy 💸

**A multi-agent personal-finance coach you talk to in plain English.**

Paste your bank data. Get a real analysis. Set a savings goal, split a bill, unlock Pro — all inside a chat, powered by a network of cooperating [Fetch.ai uAgents](https://uagents.fetch.ai/) on the ASI:One network.

> Built for the Fetch.ai / ASI:One hackathon. Runs on a **$0 stack** (free Gemini tier + local fallback), and **degrades gracefully** — it never crashes when the network or the LLM goes away.

---

## The Problem

Most budgeting apps are dashboards you have to visit, feed, and maintain. They assume you'll manually categorise spending, and they break the moment your data looks "wrong" (a semicolon-delimited export, a `£` sign, a European date).

**BudgetBuddy inverts that:** you paste whatever your bank gives you, in a chat, and it does the work.

## Who It's For

People who want a straight answer about their money without a spreadsheet — students, freelancers, early-career workers, anyone who opens their banking app, feels vaguely bad, and closes it again.

## The Outcome

A conversation, not a dashboard:

```
👤  [paste 38 rows of bank transactions]
🤖  ✅ Parsed 38 transactions! Income $7,500 · Expenses $3,975

👤  How am I doing?
🤖  Savings rate: 47.0%  ·  Biggest expense: rent ($2,400, 60%)
    ⚠️ 4 forgotten subscriptions — Planet Fitness, Adobe, Netflix, Spotify

👤  What subscriptions do I have?
🤖  $1,493.51/mo  ·  $17,922.12/yr  → review what you actually use

👤  I want to save $3000 by August
🤖  $300.00/mo needed  ·  ✅ You're on track (surplus $3,224.72)

👤  Split this $90 dinner with Alice and Bob
🤖  You $30 · Alice $30 · Bob $30

👤  How do I unlock Pro?
🤖  BudgetBuddy Pro — $4.99 · Request ID: e4f2d232 · Status: PENDING
```

---

## Architecture

The system is split in two halves: a pure-Python **brain** (all the logic, fully testable offline) and a **multi-agent layer** that wraps the brain in real uAgents.

```
                            ASI:One  /  curl
                                  │
                    POST /submit  │  {session_id, text}
                                  ▼
                      ┌───────────────────────┐
                      │      HOST AGENT       │   intent router
                      │  (ACP Query/Response) │   + reply composer
                      └───────────┬───────────┘
                                  │  AgentBus.call(timeout=15s)
          ┌───────────┬───────────┼───────────┬───────────┐
          ▼           ▼           ▼           ▼           ▼
     ┌────────┐  ┌─────────┐ ┌─────────┐ ┌────────┐ ┌──────────┐
     │ INGEST │  │ ANALYST │ │  COACH  │ │  GOAL  │ │ SPLITTER │
     └────────┘  └─────────┘ └─────────┘ └────────┘ └──────────┘
          │           │           │           │           │
          └───────────┴───────────┴───────────┴───────────┘
                                  │
                      ┌───────────▼───────────┐
                      │   core/  (the brain)  │
                      │  parser · categorizer │
                      │  analyzer · llm · …   │
                      │   SQLite session store│
                      └───────────────────────┘
                                  │
                    ⚠️ if a sub-agent is dead or slow:
                    in-process fallback → user still gets an answer
```

**Every agent runs in one process** via a uAgents `Bureau`. The host is reachable over HTTP; sub-agents are separate uAgents with their own addresses, called with a 15-second timeout. If one fails, the host runs the same logic in-process — so a judge never sees a hang.

### The six agents

| Agent | Wraps | Responsibility |
|-------|-------|----------------|
| **host** | `agents/host.py` | REST `/submit`, intent detection, routing, reply composition |
| **ingest** | `core/parser.py` | CSV & free-text → normalised transactions |
| **analyst** | `core/analyzer.py` | Totals, savings rate, recurring detection, insights |
| **coach** | `core/coach.py` | LLM-backed advice, deterministic fallback |
| **goal** | `core/goal.py` | Savings-goal what-if math |
| **splitter** | `core/splitter.py` | Bill splitting + settlement minimisation |

---

## Quickstart

```bash
# 1. Clone
git clone https://github.com/surjit12334-hue/budgetbuddy.git
cd budgetbuddy

# 2. Virtualenv (Python 3.10+)
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 3. Configure (optional — everything works without an LLM key)
cp .env.example .env
#   edit .env: set HOST_SEED to any long unique phrase
#   optionally add GEMINI_API_KEY (free: https://aistudio.google.com/apikey)
```

### Try it locally (no network needed)

```bash
./sim.sh
```
Then type `/demo` for the full 6-turn walkthrough, or `/paste` your own data.

### Run the full multi-agent system

```bash
./run.sh                      # starts all 6 agents on http://localhost:8001

# in another terminal:
curl -X POST http://localhost:8001/submit \
  -H "Content-Type: application/json" \
  -d '{"session_id":"demo","text":"How am I doing?"}'
```

### Going live (ASI:One)

To expose BudgetBuddy to Agentverse / ASI:One, tunnel the Bureau and verify
before you touch the network:

```bash
./keepalive.sh                     # auto-restarts the Bureau if it ever crashes
ngrok http 8001                    # in another terminal — copy the https URL

.venv/bin/python tools/preflight.py https://YOUR-URL.ngrok-free.app
```

`preflight.py` checks the Bureau, all 6 agents, the local round-trip, the full
6-turn flow, session persistence, and the public tunnel — then prints the exact
endpoint URL to paste into Agentverse. Step-by-step instructions:
[`docs/REGISTRATION.md`](docs/REGISTRATION.md).

---

## The $0 Stack

Every dependency is free. Nothing requires a credit card.

| Layer | Choice | Cost | Notes |
|-------|--------|------|-------|
| Agent framework | Fetch.ai **uAgents** | $0 | pip-installable, runs locally |
| LLM | **Gemini** free tier | $0 | optional — deterministic fallback if absent |
| LLM fallback | **Ollama** (local) | $0 | optional, if you run it |
| Storage | **SQLite** | $0 | stdlib, 24 h TTL purge |
| Currency FX | **frankfurter.app** | $0 | free public API |
| Tunnelling | **ngrok** free tier | $0 | for Phase 5 live hosting |
| Hosting | your laptop | $0 | a Bureau process |

**Privacy note:** only *aggregate* figures (totals, category sums) are ever sent to an LLM. Raw transaction lines never leave the machine.

---

## Copy-Paste Demo Script

The exact 6 turns. Paste the whole block into `./sim.sh` after `/paste`:

```csv
Date,Description,Amount
01/02/2024,Employer Payroll Deposit,+3500.00
01/03/2024,Rent Payment - Oakwood Apartments,-1200.00
01/03/2024,Netflix Subscription,-15.99
01/04/2024,Spotify Premium,-9.99
01/05/2024,Adobe Creative Cloud,-19.99
01/05/2024,Whole Foods Market,-125.30
01/06/2024,Starbucks Coffee,-5.45
01/07/2024,Shell Gas Station,-42.00
01/10/2024,Electric Company Bill,-85.50
01/15/2024,Freelance Payment - Design Work,+500.00
01/15/2024,Planet Fitness Gym,-49.99
02/01/2024,Employer Payroll Deposit,+3500.00
02/02/2024,Rent Payment - Oakwood Apartments,-1200.00
02/03/2024,Netflix Subscription,-15.99
02/04/2024,Spotify Premium,-9.99
02/05/2024,Adobe Creative Cloud,-19.99
02/12/2024,T-Mobile Phone Bill,-55.00
02/16/2024,Nike Store,-120.00
```

Then, in order:

| # | Type this | You should see |
|---|-----------|----------------|
| 1 | *(the CSV above)* | `✅ Parsed N transactions!` |
| 2 | `How am I doing?` | Financial health report + insights |
| 3 | `What subscriptions do I have?` | Recurring list with monthly + annual totals |
| 4 | `I want to save $3000 by August` | Monthly/weekly/daily target |
| 5 | `Split this $90 dinner with Alice and Bob` | Even split, 3 ways |
| 6 | `How do I unlock Pro?` | Payment request, status PENDING |

*(The full 38-row sample lives at `samples/sample_bank.csv`.)*

---

## Testing

```bash
.venv/bin/python tests/smoke.py           # 55 assertions — every core module
.venv/bin/python tests/test_adversarial.py # 45 cases — hostile input, fuzz, 500 rows
.venv/bin/python tests/test_outage.py      # 14 cases — LLM outage transparency
.venv/bin/python tests/demo.py             # full 6-turn conversation
```

For the multi-agent layer (Bureau must be running):

```bash
./run.sh &
.venv/bin/python tests/test_phase2.py     # 6-turn flow over HTTP
.venv/bin/python tests/test_fallback.py   # sub-agent-death recovery
```

**Current status:** 55/55 smoke · 45/45 adversarial · 14/14 outage · 6/6 fallback · 7/7 HTTP — all green.

---

## FAQ

**Q: What if I don't have a Gemini API key?**
A: The app works fully without one. `core/llm.py` tries Gemini → Ollama → nothing, and the coach falls back to deterministic, rule-based insights. You lose some phrasing polish, none of the functionality.

**Q: What if the LLM provider goes down mid-conversation?**
A: Nothing visible happens. Calls retry briefly (10 s × 2), then fall back. The user still gets their analysis. This is tested in `tests/test_outage.py`.

**Q: What if a sub-agent crashes?**
A: The `AgentBus` catches the timeout/error and runs the same logic in-process. Tested in `tests/test_fallback.py`.

**Q: My bank export is semicolon-delimited with European dates and `£` signs. Will it work?**
A: Yes. The parser auto-detects `,` `;` `\t` `|`, handles 9 date formats, recognises `$ € £ ₹ ¥`, debit/credit column pairs, and parenthesised negatives `(50.00)`. Ambiguous dates are flagged rather than guessed silently.

**Q: Is my financial data sent anywhere?**
A: Raw transactions never leave your machine. Only aggregate numbers (totals, category sums) go to an LLM if one is configured. Sessions are purged after 24 h (`SESSION_TTL_HOURS`).

**Q: Why multiple agents instead of one script?**
A: Because the brief is an agentic system, and it's genuinely more robust: work is partitioned, each agent has one job, and failures are isolated with a fallback. The brain stays pure Python and independently testable.

**Q: Can I run this without the agents, just the logic?**
A: Yes — `./sim.sh` uses `core/orchestrator.py` directly. Handy for development and for demos when you don't want network complexity.

---

## Project Layout

```
budgetbuddy/
├── core/                  # the brain — pure Python, no network
│   ├── models.py          # Transaction, Goal, SplitBill, PaymentRequest
│   ├── state.py           # SQLite session store, 24h TTL
│   ├── parser.py          # CSV + free-text → transactions
│   ├── categorizer.py     # merchant normalisation + keyword map + LLM
│   ├── analyzer.py        # totals, savings rate, recurring detection
│   ├── llm.py             # Gemini → Ollama → None chain
│   ├── coach.py           # LLM advice + deterministic fallback
│   ├── goal.py            # savings-goal math
│   ├── splitter.py        # split + settlement minimisation
│   ├── payments.py        # payment request lifecycle
│   ├── cards.py           # 7 interactive-card builders
│   └── orchestrator.py    # intent router (used by the simulator)
├── agents/                # the multi-agent layer
│   ├── messages.py        # typed request/response models
│   ├── services.py        # shared singletons
│   ├── subagents.py       # Ingest, Analyst, Coach, Goal, Splitter
│   ├── bus.py             # AgentBus: timeout + in-process fallback
│   ├── host.py            # ACP host, REST /submit
│   └── run.py             # Bureau entrypoint
├── samples/sample_bank.csv
├── tests/                 # smoke, adversarial, outage, phase2, fallback
├── tools/redact_csv.py    # anonymise a real export
├── run_local.py           # the terminal simulator
├── run.sh / sim.sh        # launchers
└── ROADMAP.md             # the build plan + progress
```

---

## Roadmap

See [`ROADMAP.md`](ROADMAP.md) for the full plan. Progress:

| Phase | Theme | Status |
|-------|-------|--------|
| 0 | Foundation | ✅ |
| 1 | The Brain | ✅ |
| 2 | The Agents | ✅ |
| 3 | Hardening | ✅ |
| 4 | Docs | 🔄 |
| 5 | Going Live (ASI:One) | ⬜ |
| 6 | Interactive Cards + Payment | ⬜ |
| 7 | Demo Assets | ⬜ |
| 8 | Submission | ⬜ |

---

## License

MIT — see [LICENSE](LICENSE).
