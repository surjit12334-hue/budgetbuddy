# Submission Runbook — the 5 things only you can do

> **Everything code-side is done and verified.** The agent is live on Agentverse
> (`active`, mailbox, 3 protocols), the full pre-flight is green, and the suite is
> 585/585. What's left needs a browser, a microphone, and your Devpost login.
>
> Order matters: **A → B → C → D → E**. Each step needs the one before it.
> Total: about **1 hour of focused work**, plus recording time.
>
> Last verified: pre-flight all-green, live chat round-trip working,
> 585/585 assertions, GitHub `main` in sync.

---

## Step 0 — Pre-flight (2 min, before anything)

```bash
cd ~/budgetbuddy
./keepalive.sh          # leave this running in its own terminal
```

In a second terminal:

```bash
cd ~/budgetbuddy
.venv/bin/python tools/preflight.py
```

**You should see:** `✅ ALL CHECKS PASSED — ready for ASI:One`

If `[1] Bureau reachable` fails, wait 20 s and run it again — the mailbox
registration takes a few seconds after start.

Then open **ASI:One** in Firefox or Brave: <https://asi1.ai>
(asi1.ai answers `HTTP 200` from this machine, so the network is fine.)

> **Leave that terminal alone while you demo.** `keepalive.sh` restarts the
> Bureau if it ever crashes. Closing the terminal kills both.

---

## Step A — Capture the Shared Chat URL (7.3 · ~10 min)

This creates the link a judge clicks to replay the whole conversation.

1. In ASI:One, open a chat with **BudgetBuddy**. You can get there from the
   agent profile:
   <https://agentverse.ai/agents/details/agent1qwv44y4c4yz47j58zhylm7rnev6qk4su0km42k69f8345ytt5s90jyxgaa9>
2. Send **prompt 1** — the raw CSV, exactly this (it's 18 rows, not the
   38-row sample file):

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

**You should see:**
```
✅ Parsed 18 transactions!

💰 Income found:  $7,500.00
💸 Expenses found: $2,975.18
```

3. Then send these **five prompts in order**, one message each:

| # | Send exactly this | You should see |
|---|---|---|
| 2 | `How am I doing?` | `═══ Financial Health Report ═══`, 60.3% savings rate, the 4 forgotten subscriptions |
| 3 | `What subscriptions do I have?` | `TOTAL $95.96/mo`, `ANNUAL $1,151.52/yr`, and rent listed under **Fixed Bills**, not subscriptions |
| 4 | `I want to save $3000 by August` | monthly / weekly / daily target + "on track" |
| 5 | `Split this $90 dinner with Alice and Bob` | `You $30.00 · Alice $30.00 · Bob $30.00` |
| 6 | `How do I unlock Pro?` | `RequestPayment`, amount `$4.99 USD`, a **PENDING** status, plus a review card |

4. **Share it.** Use ASI:One's **Share** action on that conversation
   (conversation menu). If you can't find a Share button, copy the
   conversation URL from the browser address bar — that works too.
5. Paste that link in both places:
   - `docs/DEVPOST.md` → the line that currently says
     `**ASI:One Shared Chat:** *(paste the link from your clean run …)*`
   - the end card of the video in Step B

**Done when:** the link opens a conversation containing all six turns.

> **Re-take is safe.** Pasting a new CSV *replaces* the session's data
> (`save_transactions` overwrites, it doesn't append). If a run goes wrong,
> just paste prompt 1 again in the same chat — you don't get double data.

> **If a turn answers "paste your spending data first":** that conversation's
> session lost its data (24 h TTL). Start a fresh chat and redo from prompt 1.

---

## Step B — Record the video (7.2 · 30–45 min)

OBS and ffmpeg are installed. Shot list and narration beats are in
`docs/DEMO_SCRIPT.md` §3 — this is the short version.

**Setup (5 min)**
1. Open OBS → *Sources* → **Screen Capture (XSHM)**.
2. Output: 1920×1080, 30 fps, MKV (remux to MP4 after — safer if OBS crashes).
3. Do a 10-second test recording and watch it back. If the terminal text is
   unreadable, bump the terminal font size before you start.

**Record these 10 shots in order** (target 2:30–3:00):

| # | Time | What's on screen |
|---|---|---|
| 1 | 0:00–0:12 | Terminal: `curl -s http://localhost:8001/agent_info \| python3 -m json.tool` → then the Agentverse profile page |
| 2 | 0:12–0:25 | ASI:One: paste the CSV |
| 3 | 0:25–0:50 | "How am I doing?" → **open the dashboard card** |
| 4 | 0:50–1:15 | "What subscriptions do I have?" → **swipe the carousel**, point at rent being excluded |
| 5 | 1:15–1:40 | "I want to save $3000 by August" |
| 6 | 1:40–2:00 | "Split this $90 dinner with Alice and Bob" → **click "Remind everyone"** |
| 7 | 2:00–2:25 | "How do I unlock Pro?" → the review card |
| 8 | 2:25–2:40 | Terminal: the forged payment being refused (below) |
| 9 | 2:40–2:55 | Terminal: six agents, one per line (below) |
| 10 | 2:55–3:00 | Agentverse profile + the Shared Chat link on screen |

**Shot 8 — the money shot.** This is the one that proves the payment is real:

```bash
cd ~/budgetbuddy
DEMO_FORGE=1 .venv/bin/python tools/payment_demo.py
```

**You should see** (verified just now):
```
[4] ✗ CancelPayment received: signature does not verify against the sender's agent address
[5] completed=False cancelled=True rejected=False
  ✅ FORGED COMMIT REJECTED — no Pro unlocked (correct)
```

**Shot 9 — six agents, no restart needed** (verified just now):

```bash
curl -s http://localhost:8001/health | python3 -m json.tool
```

That prints `host`, `ingest`, `analyst`, `coach`, `goal`, `splitter` — six
`agent1q…` addresses. Read them out: *"six agents, one job each."*

**Done when:** the video is uploaded to YouTube as **unlisted** and you have the link.

---

## Step C — Devpost voice pass (7.5 · 15 min)

`docs/DEVPOST.md` is factually correct now — every number in it has been
checked against the code. What it needs is **your** voice.

1. Open `docs/DEVPOST.md` and read it top to bottom.
2. Change any sentence that doesn't sound like something you'd say. That's the
   whole job — don't add claims, don't soften the honest ones.
3. Fill the two placeholders at the bottom:
   - `**ASI:One Shared Chat:**` → the link from Step A
   - `**Demo video:**` → the YouTube link from Step B

**Done when:** no `*(paste the link …)*` text remains in the file.

> Don't touch these three things — they're deliberate and verified:
> the "$0 stack" table, the "a demo that lied to us" story, and the
> "payment that cannot be faked" section. A judge can check all three.

---

## Step D — Submit (8.3 · 10 min)

Paste `docs/DEVPOST.md` into Devpost, section by section. Fields you'll need:

| Devpost field | What to use |
|---|---|
| Title | `BudgetBuddy — a multi-agent personal-finance coach for ASI:One` |
| Elevator pitch | the first block in `docs/DEVPOST.md` |
| Built with | `uagents`, `python`, `sqlite`, `gemini-api`, `ollama`, `agentverse`, `rest` |
| GitHub repo | `https://github.com/surjit12334-hue/budgetbuddy` |
| Live demo / video | the unlisted YouTube link (Step B) |
| Try it | the ASI:One Shared Chat link (Step A) |
| Agent profile | the Agentverse profile URL |

**Done when:** Devpost shows your submission as submitted. Screenshot it.

> Target is **≥3 days before the deadline**. If you're inside 24 h, submit
> with the video and skip Step F (the optional one).

---

## Step E — Stay alive after submitting (8.4 · ongoing)

The viability bonus is "operating since…", so the clock only counts if the
agent keeps answering.

```bash
cd ~/budgetbuddy
./keepalive.sh
```

- Leave it running for judge Q&A.
- If the machine reboots, run it again. The identity survives: the seed is in
  `.budgetbuddy_identity`, so the agent comes back as the **same** address —
  the same one your published links point at.
- Optional health check any time:

```bash
curl -s http://localhost:8001/health | python3 -m json.tool | head -5
```

**In the Devpost text (optional but strong):** add one line —
*"Live since <date> — the agent has been answering continuously."*

---

## Step F — Optional: your own bank data (3.4 · 10 min)

Only do this if you want the "it works on *my* data" moment. It doesn't block
submission.

```bash
cd ~/budgetbuddy
.venv/bin/python tools/redact_csv.py ~/Downloads/your-bank-export.csv > /tmp/mine.csv
./sim.sh
```

Then in the simulator, paste the contents of `/tmp/mine.csv`.

**Read the redacted file first** — check that names and account numbers are
gone before you paste. This is your real money data.

**Done when:** you get a report you'd actually use.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Unable to resolve destination endpoint` | The agent has no Agentverse mailbox (or it's not registered yet) | Wait ~20 s after `keepalive.sh` starts; re-run pre-flight check `[6]` |
| ASI:One says the agent is offline | The Bureau isn't running, or the terminal was closed | `./keepalive.sh` again, wait 20 s |
| Pre-flight `[6]` says "not active" | Registration is still propagating | Wait 30 s, re-run |
| A chat turn says "paste your data first" | That session's data expired (24 h TTL) | Paste prompt 1 again |
| `port 8001 is still held` | An old Bureau survived | `./tools/stop_bureau.sh 8001`, then `./keepalive.sh` |
| You pasted the wrong CSV | Data is replaced, not appended | Paste the correct CSV again — it overwrites |

**Emergency reset** (nuclear option, breaks the published identity — don't):

```bash
./tools/stop_bureau.sh 8001
ls .budgetbuddy_identity   # the seed is in here; back it up before touching anything
```

> ⚠️ **Never change `HOST_SEED` on this machine.** It is what makes the agent
> `agent1qwv44y…` — the address on Agentverse, in the Devpost, and in every
> link. Changing it orphans the mailbox and every published link. The startup
> log now says this out loud.
