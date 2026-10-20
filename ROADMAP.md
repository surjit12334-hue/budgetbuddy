# BudgetBuddy — Build Roadmap

> A multi-agent personal-finance coach on the ASI:One network.
> Built with Fetch.ai **uAgents**, **Gemini** (free tier), and a **$0 stack**.
> This document is the single source of truth for progress. Check boxes as you go.

---

## Phase 0 — Foundation (Day 0–1 · ~1 h)

**Goal:** Environment ready, so code lands on solid ground.

- [x] **0.1** Create GitHub repo `budgetbuddy` (public) — ✅ pushed to https://github.com/surjit12334-hue/budgetbuddy (`main` @ `ed5ae2d`, via SSH)
- [x] **0.2** Install Python 3.10+, create venv, `pip install -r requirements.txt` — ✅ Python 3.14.8 + `.venv`, `import uagents` works (uagents 0.26.1)
- [x] **0.3** Copy `.env.example` → `.env`, invent your `HOST_SEED` — ✅ `.env` exists with generated seed, **not committed** (git-ignored)
- [ ] **0.4** Get free Gemini API key ([aistudio.google.com](https://aistudio.google.com)) — ⏳ **remaining: you** paste key into `.env` (`GEMINI_API_KEY=`); app runs fine without it (graceful degradation)
- [x] **0.5** Read the 6-turn demo script — know where you're heading — ✅ all 6 turns verified via `tests/demo.py`

> **Phase 0 status: environment ready.** 0.2, 0.3, 0.5 done by me. **Two steps remain for you:** 0.1 (push to GitHub) and 0.4 (paste Gemini key). Neither blocks development — Phase 1 and 2 are already built and green.

---

## Phase 1 — The Brain (Days 1–3 · ~2 sessions)

**Goal:** All the logic works in-process, no agents yet. **This is 70% of the value.**

- [x] **1.1** `core/state.py` — SQLite session store, 24 h TTL purge — ✅ sessions save / load / purge
- [x] **1.2** `core/parser.py` — CSV & free-text → normalized transactions (delimiters, headers, 9 date formats, debit/credit columns, parenthesized negatives, currency symbols, ambiguity flags) — ✅ sample CSV parses to 38 clean txns
- [x] **1.3** `core/categorizer.py` — merchant normalization + keyword map + LLM fallback for unknowns — ✅ every sample txn categorized
- [x] **1.4** `core/analyzer.py` — totals, savings rate, fixed-vs-variable, needs-vs-wants, recurring/subscription detection, deterministic insights — ✅ "forgotten subscriptions" insight appears
- [x] **1.5** `core/llm.py` — Gemini → Ollama → None fallback chain, JSON-mode parsing — ✅ no key → chain degrades, no crash
- [x] **1.6** `core/coach.py` — Coach prompts (aggregates only — raw txns never sent) + deterministic fallback — ✅ 3 insights + revised budget come back
- [x] **1.7** `core/goal.py` — savings-goal what-if math — ✅ "$3,000 by August" → exact monthly + cut scenarios
- [x] **1.8** `core/splitter.py` — even/uneven split + settlement minimization — ✅ settlement output correct
- [x] **1.9** `core/payments.py` — payment request lifecycle (mock now, testnet-ready interface) — ✅ pending → paid → Pro unlocked
- [x] **1.10** `core/cards.py` — 7 card builders (disabled by default) — ✅ builders emit valid JSON
- [x] **1.11** `core/orchestrator.py` — intent router + reply composer + DirectBus — ✅ full 6-turn flow works

> **✅ Phase 1 gate PASSED:** `orchestrator.handle(session, text)` produces the complete 6-turn demo conversation. 55/55 smoke tests green.

---

## Phase 2 — The Agents (Days 3–4 · 1 session)

**Goal:** Turn the brain into a real multi-agent ACP system.

- [x] **2.1** `agents/messages.py` — typed message models (`request_id` per call) — ✅ models import cleanly
- [x] **2.2** `agents/subagents.py` — Ingest, Analyst, Coach, Goal, Splitter as separate uAgents — ✅ each agent starts
- [x] **2.3** `agents/host.py` — ACP host (Query/Response), session keying, pending-future pattern — ✅ host answers a Query
- [x] **2.4** `AgentBus` — host→sub-agent calls with 15 s timeout + in-process fallback — ✅ kill a sub-agent → user still gets an answer
- [x] **2.5** Bureau wiring + entrypoint — ✅ all 6 agents run from one command (`python -m agents.run`)
- [x] **2.6** Verify agent-to-agent traffic visible in logs — ✅ log shows `host → bus → ingest → bus → host` hop

> **✅ Phase 2 gate PASSED:** `curl POST /submit` with a Query returns the composed reply (7/7 HTTP tests green); logs prove multi-agent orchestration; fallback path verified (6/6).

---

## Phase 3 — Local Simulator + Hardening (Days 4–5)

**Goal:** Break it on purpose before a judge does.

- [ ] **3.1** `run_local.py` — terminal REPL (`/demo`, `/reset`, paste mode) — *Done when:* you chat with it locally
- [ ] **3.2** Adversarial tests: no headers, semicolons, tabs, £/€/₹, ambiguous dates, empty paste, 500-row file, garbage text — *Done when:* every case → helpful message, never a traceback
- [ ] **3.3** LLM-outage drill (remove key mid-session) — *Done when:* deterministic insights take over silently
- [ ] **3.4** You paste your own real bank CSV (anonymized) — *Done when:* real data produces a report you'd actually use

> **✅ Phase 3 gate:** 6-turn flow passes on sample **and** real data; all failure paths recover gracefully.

---

## Phase 4 — Docs (Days 5–6 · 1 session)

**Goal:** Submission-ready materials.

- [ ] **4.1** `README.md` — problem/users/outcome, ASCII architecture, quickstart, $0 stack table, copy-paste demo script, FAQ with judge-proof answers, roadmap — *Done when:* a stranger could reproduce from README alone
- [ ] **4.2** `docs/REGISTRATION.md` — Agentverse click-by-click, ngrok, ASI:One, Shared Chat URL, testnet faucet — *Done when:* zero ambiguity for you
- [ ] **4.3** Devpost draft: problem, target users, outcome, architecture blurb — *Done when:* ready to paste
- [ ] **4.4** MIT LICENSE — *Done when:* repo complete

---

## Phase 5 — Going Live ⚠️ (Days 6–7)

> **Riskiest phase — do NOT leave for deadline day.**

**Goal:** First real ASI:One ping.

- [ ] **5.1** Push repo to GitHub — *Done when:* public repo live
- [ ] **5.2** Agentverse: create account → create agent → enable chat protocol — *Done when:* Agent Profile URL exists
- [ ] **5.3** Start ngrok → paste public URL as agent endpoint — *Done when:* endpoint saved
- [ ] **5.4** First ASI:One message — troubleshoot (`session_id`, envelopes, timeouts) — *Done when:* agent replies in ASI:One
- [ ] **5.5** Full 6-turn flow in ASI:One, session persistence verified — *Done when:* conversation memory works across turns
- [ ] **5.6** Demo-window uptime plan (laptop awake, ngrok stable, restart script) — *Done when:* survives a 30-min demo

> **✅ Phase 5 gate:** The complete workflow runs inside a real ASI:One conversation. **(Mandatory requirement #1 — unlock everything after this.)**

---

## Phase 6 — Interactive Cards + Payment (Days 7–8)

**Goal:** The bonus points.

- [ ] **6.1** Check official ASI:One Interactive Cards docs → adapt `cards.py` to the real schema — *Done when:* builders match official schema
- [ ] **6.2** `ENABLE_CARDS=true` → test each card live: onboarding form, dashboard, insights carousel, goal, split, checkout — *Done when:* cards render in chat
- [ ] **6.3** Fallback check: cards off → markdown version still tells the whole story — *Done when:* zero single point of failure
- [ ] **6.4** Testnet faucet → real Payment Protocol request → Pro unlock — *Done when:* payment completes in-chat

> **✅ Phase 6 gate:** Judge sees a card-driven flow and one credible payment.

---

## Phase 7 — Demo Assets (Days 8–9)

**Goal:** The two headline deliverables.

- [ ] **7.1** Final demo script — exact 6 prompts, expected replies, "wow moments" flagged — *Done when:* script final
- [ ] **7.2** Record 2–3 min video (shot list + narration beats provided) — *Done when:* video uploaded to YouTube (unlisted)
- [ ] **7.3** Generate ASI:One Shared Chat URL of a clean run — *Done when:* link opens the conversation
- [ ] **7.4** Collect Agentverse Profile URL(s) — *Done when:* links ready
- [ ] **7.5** Polish Devpost text — own it in your voice — *Done when:* text final

---

## Phase 8 — Submission + Buffer (Days 9–10)

**Goal:** Submitted early, sleeping well.

- [ ] **8.1** Dry run: someone (or you, cold) follows the README from zero — *Done when:* reproduces the demo
- [ ] **8.2** Fix the top 3 friction points that surfaced — *Done when:* smooth
- [ ] **8.3** Submit on Devpost — target **≥3 days before deadline** — *Done when:* submission confirmed
- [ ] **8.4** Post-submit: keep agent alive for judge Q&A; note "operating since…" for the viability bonus — *Done when:* agent still replying

> **✅ Phase 8 gate:** Submitted. Agent is live. You slept.

---

## Quick Reference

| Phase | Theme | Days | Key Deliverable |
|-------|-------|------|-----------------|
| 0 | Foundation | 0–1 | Working dev environment |
| 1 | The Brain | 1–3 | All logic in-process |
| 2 | The Agents | 3–4 | Multi-agent ACP system |
| 3 | Hardening | 4–5 | Break-it testing |
| 4 | Docs | 5–6 | README + registration guide |
| 5 | Going Live | 6–7 | Real ASI:One conversation |
| 6 | Cards + Payment | 7–8 | Interactive cards + testnet payment |
| 7 | Demo Assets | 8–9 | Video + Shared Chat URL |
| 8 | Submission | 9–10 | Devpost submission |

**Legend:** 👤 = human does it · 🤝 = human + AI collaborate
