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
- [x] **0.4** Get free Gemini API key ([aistudio.google.com](https://aistudio.google.com)) — ✅ key in `.env`; verified working (`gemini-3.8-flash`); model updated since `gemini-2.0-flash` was retired. Google free tier currently intermittent (503/timeouts) → deterministic fallback covers it.
- [x] **0.5** Read the 6-turn demo script — know where you're heading — ✅ all 6 turns verified via `tests/demo.py`

> **✅ Phase 0 COMPLETE.** Repo live at https://github.com/surjit12334-hue/budgetbuddy, environment ready, `.env` configured with a working Gemini key. Note: `gemini-2.0-flash` was retired by Google — switched to `gemini-3.8-flash`; the free tier is intermittently slow, and the LLM chain degrades to deterministic insights in ~12 s.

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

- [x] **3.1** `run_local.py` — terminal REPL (`/demo`, `/reset`, paste mode) — ✅ REPL works (`sim.sh`), all 6 demo turns run
- [x] **3.2** Adversarial tests: no headers, semicolons, tabs, £/€/₹, ambiguous dates, empty paste, 500-row file, garbage text — ✅ 93/93 cases graceful, never a traceback (also 1000 fuzz inputs, and fixed a real `csv.reader` crash). Extended with **section G: the demo CSV under hostile transformations** — `samples/sample_bank.csv` mangled the way a real bank export gets mangled (CRLF, BOM, `;`/`|`/tab delimiters, no header, reordered columns, extra Balance column, EU decimal commas, `Dr/Cr` suffixes, debit/credit columns, truncated row, blank/garbage amount, null byte, redacted copy): the same 38 transactions, the same $3,524.72 total and the same money story (subscriptions $95.96 / bills $1,392.40) every time. That section exposed **three real parser bugs**, now fixed in `core/parser.py`: `Dr/Cr` suffixes lost their sign (`1200.00 DR` read as **+1200 income**), EU separators were mangled (`12,50` → **1250**, `1.234,56` → **1.23456**), and pipe-delimited exports fell through to the free-text parser with garbage merchant names.
- [x] **3.3** LLM-outage drill (remove key mid-session) — ✅ 14/14 tests; deterministic insights take over silently, no error leaks
- [x] **3.3b** Bug fix from the demo run: rent was reported as a subscription — ✅ recurring charges are now split into **subscriptions** ($95.96/mo — Netflix, Spotify, Adobe, Planet Fitness), **fixed bills** (rent, utilities — $1,392.40/mo) and **habitual** (a repeated coffee; neither); `tests/test_subscriptions.py` 35/35
- [ ] **3.4** You paste your own real bank CSV (anonymized) — ⏳ **your step**: use `tools/redact_csv.py` to anonymize, then `./sim.sh` and paste. *Done when:* real data produces a report you'd actually use

> **Phase 3 gate: code-side PASSED** — 6-turn flow passes on sample data; all failure paths recover gracefully (93/93 adversarial, 14/14 outage). Awaiting 3.4 (your real CSV) to fully close.

---

## Phase 4 — Docs (Days 5–6 · 1 session)

**Goal:** Submission-ready materials.

- [x] **4.1** `README.md` — problem/users/outcome, ASCII architecture, quickstart, $0 stack table, copy-paste demo script, FAQ with judge-proof answers, roadmap — ✅ verified from a **fresh clone**: docs present, demo runs, tests green
- [x] **4.2** `docs/REGISTRATION.md` — Agentverse click-by-click, ngrok, ASI:One, Shared Chat URL, testnet faucet — ✅ step-by-step with troubleshooting table + uptime plan
- [x] **4.3** Devpost draft: problem, target users, outcome, architecture blurb — ✅ `docs/DEVPOST.md` ready to paste
- [x] **4.4** MIT LICENSE — ✅ `LICENSE` added

> **✅ Phase 4 gate PASSED:** a stranger can clone the repo and reproduce the full demo in under 5 minutes, with or without an API key. All docs committed (`f1c3d93`).

---

## Phase 5 — Going Live ⚠️ (Days 6–7)

> **Riskiest phase — do NOT leave for deadline day.**

**Goal:** First real ASI:One ping.

- [x] **5.1** Push repo to GitHub — ✅ public repo live: `github.com/surjit12334-hue/budgetbuddy`
- [x] **5.2** Agentverse: create account → create agent → enable chat protocol — ✅ account + agent registered (`active`, `type: mailbox`, 2 protocols); mailbox created via the Local Agent Inspector; chat manifest published (`host_agent.include(_chat_proto, publish_manifest=True)` → `Manifest published successfully: AgentChatProtocol`). *Note: "public/private" is a code flag, not a dashboard dropdown — see `docs/REGISTRATION.md`.*
- [x] **5.3** Reachable from Agentverse — ✅ **mailbox** (not ngrok): agent self-registers `status: active`, `type: mailbox`; verified via Almanac lookup
- [x] **5.4** First ASI:One message — ✅ **PASSED**: real ASI:One conversation returned a full money breakdown built from the sample data, naming the user. Confirms the whole chain: ASI:One → mailbox → host `route()` → AgentBus → sub-agents → reply.
- [x] **5.5** Full flow + session persistence — ✅ locally verified (preflight [4]+[5], `test_chat.py` [4]); chat sessions namespaced per sender; confirmed live in ASI:One (analysis + subscriptions in one conversation)
- [x] **5.6** Demo-window uptime plan — ✅ `keepalive.sh` (auto-restart, verified) + mailbox reconnects on its own (no URL to re-paste)

> **✅ Phase 5 status — COMPLETE.** The agent is live on Agentverse and answers
> real ASI:One conversations end-to-end.
>
> **Key correction:** the original plan (custom REST `/submit` + ngrok) **cannot work**.
> uAgents *reserves* `/submit` and rejects it from any non-local client
> (`uagents/asgi.py:304`), so it's unreachable through a tunnel and from ASI:One.
> Rebuilt the external interface on the **Chat Protocol + Agentverse mailbox**:
>
> - `agents/host.py` — host routes through a shared `route()` used by both the
>   chat handler and REST; `Protocol(spec=chat_protocol_spec)` included;
>   `mailbox=True`, `agentverse=True`; acknowledges every message and honours
>   session-end.
> - `tests/test_chat.py` — 17/17: protocol attached, mailbox on, every intent
>   reachable, sessions isolated per sender.
> - Agent confirmed **active on Agentverse**: `type: mailbox`, 2 protocols,
>   chat manifest published.
>
> No ngrok, no public URL, no firewall change.

> **✅ Phase 5 gate: PASSED.** A real ASI:One conversation returned a full
> money breakdown built from pasted data, proving the complete chain:
> ASI:One → Agentverse mailbox → host `route()` → AgentBus → sub-agents → reply.
> **(Mandatory requirement #1 — everything after this is unlocked.)**

---

## Phase 6 — Interactive Cards + Payment (Days 7–8)

**Goal:** The bonus points.

- [x] **6.1** Check official ASI:One Interactive Cards docs → adapt `cards.py` to the real schema — *Done when:* builders match official schema
      Rewritten against <https://innovationlab.fetch.ai/resources/docs/interactive-cards/asi-interactive-cards>.
      The old builders used an invented envelope (`{"type","version","data"}`) that ASI:One
      would have silently dropped. Now: real wire keys (`card_protocol_version: "1"`,
      `requires_card_interaction`, `card_kind`, `card_payload`), payload at the **top
      level** (not wrapped in `data`), real kinds (`carousel`/`detail`/`form`/`review`/`custom`),
      real `form` fields (`kind`, not `type`), real element-tree primitives, CTA `selection`
      blocks, 64 KB + 8-level-depth limits enforced locally.
      Guarded by `tests/test_cards.py` — **198/198**.
- [x] **6.2** `ENABLE_CARDS=true` → test each card live: onboarding form, dashboard, insights carousel, goal, split, checkout — *Done when:* cards render in chat
      Cards were previously built but **never called** — dead code. Now wired into the chat
      handler: dashboard (custom), insights carousel, subscriptions carousel, goal (custom),
      split (custom), checkout (review). Added an `INSIGHTS` intent so advice-seeking language
      reaches the carousel while status questions still get the dashboard. Card clicks
      round-trip as selections (`_parse_card_selection` → `_selection_to_instruction`).
      Guarded by `tests/test_cards_live.py` — **51/51**, driving the real `_handle_chat`.
      *Live-confirmed over the real transport* with `tools/card_demo.py` (a real buyer agent
      talking to the running Bureau): **6/6** card-bearing turns delivered a card —
      dashboard `custom`, insights `carousel`, subscriptions `carousel`, goal `custom`,
      split `custom`, checkout `review` — each carrying the real wire keys
      (`card_protocol_version: "1"`, `card_kind`, `card_payload`). The split card was found
      to be **wired to a builder but never reachable**; `SplitResponse` now carries the
      structured shares and the host renders them.
      *(Only the final on-screen confirmation in the ASI:One UI is left, and that is a
      human pass.)*
- [x] **6.3** Fallback check: cards off → markdown version still tells the whole story — *Done when:* zero single point of failure
      Cards are **additive**: the markdown reply is always sent and a card is an extra
      `MetadataContent` block. Off → `as_metadata()` returns `{}` and zero cards are emitted,
      with identical text. A rejected payload also degrades to text, and building a card is
      wrapped so a card bug can never cost the user their answer.
      Guarded by `tests/test_cards_live.py` section [8].
      *Live-confirmed over the real transport*: the same six turns were replayed with
      `ENABLE_CARDS=false` (`tools/card_demo.py`, `CARD_DEMO_EXPECT_CARDS=0`) —
      **zero** cards came back and the markdown was **byte-identical** on 6 of 7 turns
      (the 7th differs only in the randomly generated payment request id / reference).
      No single point of failure.
- [x] **6.4** Testnet faucet → real Payment Protocol request → Pro unlock — *Done when:* payment completes in-chat
      BudgetBuddy is the **seller** in the official Agent Payment Protocol
      (`Protocol(spec=payment_protocol_spec, role="seller")`): it sends `RequestPayment`,
      handles `CommitPayment` / `RejectPayment`, and answers with `CompletePayment` /
      `CancelPayment`. The rails are pluggable via `PAYMENT_RAIL` — `stripe` (real card),
      `fet_direct` (on-chain MultiversX), and `bb_commit` (the credential-free default, where
      the buyer signs the seller's per-request challenge with its uAgents identity key and
      the seller verifies it with `Identity.verify_digest` against the sender's `agent1q…`
      address). **Verification can fail in every rail** — a failed check is answered with
      `CancelPayment`, never with an unlock.
      *Proven live against the running Bureau* (`tools/payment_demo.py`, a real buyer agent
      speaking the real protocol over the real transport):
      - happy path → `RequestPayment` → `CommitPayment` → **verified** → `CompletePayment` →
        "✅ Payment confirmed — Pro unlocked!" and `pro=true` persisted in the session store
      - forged signature (signed by a key that is **not** the sender's address) →
        `CancelPayment: signature does not verify against the sender's agent address`,
        session row created, `pro` **absent**
      - buyer declines → `RejectPayment`, session row created, `pro` **absent**
      Guarded by `tests/test_payments.py` — **69/69** (forged signature, wrong
      amount/currency/rail/reference, replay, expired request and double-pay all rejected).
      *Note:* the on-chain `fet_direct` rail still needs a funded testnet wallet; the legacy
      Cosmos Fetch.ai endpoints this wallet is addressed on are decommissioned, so the
      `fetch1…` address cannot be funded from this sandbox. `bb_commit` needs no credentials.

> **✅ Phase 6 gate:** Judge sees a card-driven flow and one credible payment.

---

## Phase 7 — Demo Assets (Days 8–9)

**Goal:** The two headline deliverables.

- [x] **7.1** Final demo script — exact 6 prompts, expected replies, "wow moments" flagged — 🤝 *Done when:* script final
      `docs/DEMO_SCRIPT.md` — the six prompts, the **actual replies captured from a live
      Bureau** (not written by hand), six flagged wow moments, a pre-flight check, a
      troubleshooting table, a 10-shot video list with narration beats, and the narration
      rules ("say *this is real* once per segment, and show the evidence the moment you
      say it"). The README's short demo section now points at it.
- [ ] **7.2** Record 2–3 min video (shot list + narration beats provided) — 👤 **your step**
      *Done when:* video uploaded to YouTube (unlisted)
      The shot list and narration beats are ready in `docs/DEMO_SCRIPT.md` §3 — 10 shots,
      timed, with the line to say for each. The most important shot is #8: the forged
      payment being refused.
- [ ] **7.3** Generate ASI:One Shared Chat URL of a clean run — 👤 **your step**
      *Done when:* link opens the conversation
      How to produce it: `docs/DEMO_SCRIPT.md` §4 — run the six prompts in ASI:One, then
      use ASI:One's **Share** action on that conversation.
- [x] **7.4** Collect Agentverse Profile URL(s) — 🤝 *Done when:* links ready
      <https://agentverse.ai/agents/details/agent1qwv44y4c4yz47j58zhylm7rnev6qk4su0km42k69f8345ytt5s90jyxgaa9>
      Verified live: the page returns **200**, and the Almanac record shows
      `"status": "active"`, `"type": "mailbox"`, endpoint
      `https://agentverse.ai/v2/agents/mailbox/submit`, **3 protocols**.
      *(👤 Worth opening the page once yourself — the profile body is client-side
      rendered, so the description can't be verified from a plain `curl`.)*
- [ ] **7.5** Polish Devpost text — own it in your voice — 🤝 *Done when:* text final
      `docs/DEVPOST.md` is updated to match what is actually built (real payment protocol,
      real cards, the mailbox-not-tunnel story, the honest $0 stack) and to include the
      new challenges and accomplishments. The **voice** pass is yours: re-read it as if
      you wrote it, and change the words that don't sound like you.
      Only two placeholders are left: the Shared Chat URL and the video link.

---

## Phase 8 — Submission + Buffer (Days 9–10)

**Goal:** Submitted early, sleeping well.

- [x] **8.1** Dry run: someone (or you, cold) follows the README from zero — *Done when:* reproduces the demo
      ✅ **Done — and it caught real bugs.** A fresh `git clone` was run end-to-end:
      clone (22 s) → venv + pip (35 s) → `cp .env.example .env` → `./sim.sh` `/demo` →
      the whole test suite → `./run.sh` → `POST /submit` → `tools/payment_demo.py` →
      `tools/send_chat.py`. The demo itself ran perfectly on the sample data (6/6 turns,
      518/518 assertions) — **but the published clone was not what we thought it was.**
      Five findings:
      1. **GitHub was 4 commits behind.** The published tree hard-coded the agent seed,
         so *every clone shared the demo agent's identity* — a judge following the README
         would have hijacked the demo agent's Agentverse mailbox and broken the live
         demo for everyone. Root cause fixed by `agents/identity.py` (per-machine seed) —
         **but it was unpushed.**
      2. **The payment demo proved nothing on a clone** — it imported the host module,
         spawned a phantom host agent, and reported "PAYMENT COMPLETED" while actually
         talking to the *live* agent over the mailbox.
      3. **`tools/send_chat.py` hung forever** on a clone (mailbox-enabled probe whose
         mailbox a human must create in the Inspector) — no output, no timeout, had to
         be killed by hand.
      4. **The published identity hung on one git-ignored `.env` line.** Losing `.env`
         silently changed the agent's address, orphaning the mailbox and every link
         pointing at it. The identity file now records the *seed*, so the identity is
         recoverable. Proven: with `.env` deleted, the agent still resolves to
         `agent1qwv44y…`.
      5. **Three different stale test counts** across the README (518) and the Devpost
         draft (568) — now one number, kept in step with the suite.
- [x] **8.2** Fix the top 3 friction points that surfaced — *Done when:* smooth
      ✅ Findings 1–3 were one root cause (the unpushed identity fix) — pushed as
      `233ea01`. Finding 4 fixed in `agents/identity.py` + `tests/test_identity.py` (5 new
      checks). Finding 5 fixed in the README + Devpost. Also: the README now lists every
      test file and points at `./run_tests.sh`, and `HOST_SEED` is documented as **optional**
      so nobody pins a shared identity by hand.
      **Re-verified against the real GitHub** after the push: a fresh
      `git clone https://github.com/surjit12334-hue/budgetbuddy` → unedited `.env` →
      **own identity `agent1q25ul73…`, not the demo's `agent1qwv44y…`** (no hijack) →
      simulator parses 38 transactions → **585/585 assertions green**. The demo agent
      stayed `active`/mailbox/3 protocols on Agentverse throughout.
- [ ] **8.3** Submit on Devpost — target **≥3 days before deadline** — *Done when:* submission confirmed
      Still open — needs the two links from 7.2 / 7.3.
- [ ] **8.4** Post-submit: keep agent alive for judge Q&A; note "operating since…" for the viability bonus — *Done when:* agent still replying

> **Phase 8 gate — still open:** Submitted. Agent is live. You slept.

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
