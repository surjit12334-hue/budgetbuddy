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
- **"How do I unlock Pro?"** — a **real payment request**: Fetch.ai's Agent
  Payment Protocol, with BudgetBuddy as the seller. It sends `RequestPayment`,
  accepts `CommitPayment` or `RejectPayment`, and answers with
  `CompletePayment` or `CancelPayment`. The rails are pluggable — a signed
  proof-of-commitment rail (no credentials), Stripe, or on-chain FET on
  MultiversX — and **a failed verification is answered with a cancellation,
  never with an unlock**.

Every answer also arrives as an **interactive card** in the ASI:One drawer:
a dashboard, an insights carousel, a subscriptions carousel, a savings-goal
card, a clickable split card, and a checkout review. The cards are strictly
additive — the markdown reply is always sent as well, so if a card fails to
render the user has still lost nothing. (Proven: with cards switched off, the
markdown comes back byte-identical.)

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

### It dials out — it doesn't need a public URL

BudgetBuddy is a **mailbox agent** on Agentverse. It has no inbound tunnel, no
ngrok, no public hostname — it registers with the Almanac, publishes its
protocol manifests, and receives messages through the Agentverse mailbox
endpoint. One `curl` to the Almanac confirms it:

```json
{ "status": "active", "type": "mailbox",
  "endpoints": [{ "url": "https://agentverse.ai/v2/agents/mailbox/submit" }] }
```

Three protocols are published: the Chat Protocol, the Agent Payment Protocol
(seller role), and the internal orchestrator protocol.

### The $0 stack

uAgents · Gemini free tier (optional) · Ollama (optional fallback) · SQLite ·
frankfurter.app · Agentverse mailbox · your laptop. Nothing needs a credit
card, and nothing needs a hosted server.

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
- **The cards were dead code.** They were schema-valid, unit-tested, and
  never once rendered. A card builder existed for the bill split and there was
  no branch that could ever reach it — the split response only carried
  rendered markdown, so the card layer had nothing to render. We made the
  agent protocol carry the structured shares, and then proved every card type
  over the real network with a live buyer agent, not in a unit test.
- **A silent config bug.** `source .env` assigns unconditionally, so it
  clobbered an explicitly exported variable — and `ENABLE_CARDS=true` never
  reached the running Bureau. We wrote a loader that only fills in what isn't
  already set, which is the rule `python-dotenv` uses.
- **A demo that lied to us.** The payment demo imported the host module to
  get its address, which instantiated a *phantom host agent* inside the demo
  process. uAgents then reported "Message dispatched locally" and the message
  was never delivered — the demo would have passed while proving nothing. The
  address is now pinned as a constant and a test asserts it still matches the
  host's seed.
- **Two pydantics.** uAgents' `Model` is a pydantic **v1** `BaseModel`. Using
  pydantic v2's `Field` produced a `FieldInfo` that v1 could not serialise,
  and two test files died on it. The fix was one import.

---

## Accomplishments we're proud of

- **A payment that cannot be faked.** The seller verifies the buyer's commit
  against the buyer's own `agent1q…` identity, so a signature made with
  someone else's key is refused. We demo it both ways on camera: the happy
  path unlocks Pro, the forged path gets a `CancelPayment` and no Pro. A
  forged signature, a wrong amount, a wrong reference, a replayed commit and
  a double-pay are all rejected.
- **Hardening that found real bugs.** 568 assertions across 11 test files —
  93 adversarial cases (the demo CSV mangled every way a real bank export
  gets mangled), fuzz, outage drills, 198 card-schema checks, 71
  payment-conformance checks — all green *after* fixing what they exposed.
  The demo-CSV suite alone caught three parser bugs: `Dr/Cr` suffixes losing
  their sign (`1200.00 DR` was read as **+1200 income**), European decimal
  commas being mangled (`12,50` → **1250**), and pipe-delimited exports
  producing garbage merchant names.
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
- A payment flow is only worth building if you can show it **refusing**. The
  forgery test is the demo; the happy path is just the receipt.

---

## What's next

- Funding the on-chain rail so `fet_direct` can settle real FET on the
  MultiversX devnet
- Multi-currency FX conversion for mixed-currency statements
- Shared household budgets across sessions
- Per-card interaction state, so a dashboard can filter rather than just
  display

---

## Built with

`uagents` · `python` · `sqlite` · `gemini-api` · `ollama` · `agentverse` · `rest`

---

## Links

- **GitHub:** https://github.com/surjit12334-hue/budgetbuddy
- **Agent Profile:** https://agentverse.ai/agents/details/agent1qwv44y4c4yz47j58zhylm7rnev6qk4su0km42k69f8345ytt5s90jyxgaa9
- **ASI:One Shared Chat:** *(paste the link from your clean run — see `docs/DEMO_SCRIPT.md` §4)*
- **Demo video:** *(unlisted YouTube link — see `docs/DEMO_SCRIPT.md` §3 for the shot list)*
