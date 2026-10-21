# BudgetBuddy — Final Demo Script

> The exact run to film, to demo live, and to paste into Devpost.
> Every reply below was **captured from a real run against the live
> Bureau** (`tools/card_demo.py`), not written by hand.
>
> Numbers that depend on today's date (the savings plan) will differ —
> everything else is deterministic.

---

## 0. Pre-flight (60 seconds before you start)

The agent must be **live and reachable from ASI:One**. Check:

```bash
cd budgetbuddy
./tools/stop_bureau.sh 8001          # clean slate, no duplicate Bureaus
setsid ./keepalive.sh > /tmp/ka.log 2>&1 < /dev/null &
sleep 20
curl -s http://localhost:8001/agent_info | head -c 200
```

You want to see: the host address, **3 protocols** (chat, payment, internal)
and the endpoint `https://agentverse.ai/v2/agents/mailbox/submit`.

Then confirm the agent is live on Agentverse:

```bash
curl -s -H "User-Agent: bb/1.0" \
  https://agentverse.ai/v1/almanac/agents/agent1qwv44y4c4yz47j58zhylm7rnev6qk4su0km42k69f8345ytt5s90jyxgaa9
```

You want: `"status": "active"`, `"type": "mailbox"`, 3 protocols.

**Cards must be ON** — `ENABLE_CARDS=true` in `.env` (it is by default now).
`grep ENABLE_CARDS .env` should print `ENABLE_CARDS=true`.

> Keep `keepalive.sh` running for the whole demo window. It takes an
> exclusive lock, so a second copy will refuse to start rather than
> fight the first one for port 8001.

---

## 1. The six prompts

Paste these into ASI:One, in order, as a chat with BudgetBuddy.

### Prompt 1 — the data (paste the ugly stuff)

```
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

**Expected**

```
✅ Parsed 18 transactions!

💰 Income found:   $7,500.00
💸 Expenses found: $2,975.18

Ask me "how am I doing?" for a full analysis, or "what subscriptions do I have?" to see recurring charges.
```

> 🎬 **Wow moment 1 — "paste the ugly stuff".** No import screen, no column
> mapping, no "choose a date format". You paste a raw bank export and it
> works. Say out loud: *"this is a real bank export. I didn't clean it up."*

---

### Prompt 2 — the dashboard

```
How am I doing?
```

**Expected** (abridged)

```
═══ Financial Health Report ═══

💰 Income:    $  7,500.00
💸 Expenses:  $  2,975.18
📈 Net:       $  4,524.82
📊 Savings:         60.3%

── Spending by Category ──
  rent            $  2,400.00
  utilities       $    140.50
  ...

── Insights ──
  🎉 Great savings rate: 60.3%! Keep it up!
  📊 Your biggest expense: 'rent' at $2,400.00 (81% of spending).
  🔁 Found 4 recurring subscription(s): Planet Fitness, Adobe, Netflix, Spotify. Total: $95.96/mo.
  ⚠️  You have 4 forgotten subscriptions! Consider cancelling ones you don't use.
```

…**plus a card drawer opens** with the same numbers laid out as a
dashboard (`card_kind: custom`).

> 🎬 **Wow moment 2 — the card.** The answer is *both*: readable markdown in
> the chat stream **and** a dashboard drawer. Open the drawer, then say:
> *"the text is the fallback — if the card didn't render, you'd still get
> all of it."* That is a real property, tested (`tests/test_cards_live.py`).

---

### Prompt 3 — the subscriptions

```
What subscriptions do I have?
```

**Expected**

```
═══ Recurring Subscriptions ═══

  Planet Fitness         $   49.99/mo
  Adobe                  $   19.99/mo
  Netflix                $   15.99/mo
  Spotify                $    9.99/mo

  TOTAL                  $   95.96/mo
  ANNUAL                 $1,151.52/yr

💡 You have 4 subscription(s). Review which ones you actually use!

── Fixed Bills (not subscriptions) ──

  Rent Payment           $1,200.00/mo

  TOTAL                  $1,200.00/mo

💡 These are recurring obligations, not subscriptions.
```

…plus a **carousel** card you can swipe through.

> 🎬 **Wow moment 3 — it knows the difference.** Rent is $1,200/mo and
> *recurring*, but it is **not** a subscription. A dumb regex would list it.
> BudgetBuddy separates *subscriptions* (discretionary) from *bills* (fixed
> obligations) from *habitual* spend. Point at the "$95.96/mo vs $1,200/mo"
> line — that is the insight, and it is the one people pay for.

---

### Prompt 4 — the goal

```
I want to save $3000 by August
```

**Expected** (the dates depend on today)

```
═══ Savings Goal Plan ═══

🎯 Target: $3,000.00 by August 2027
📅 Time remaining: 10 months

💰 Monthly savings needed: $300.00
📅 Weekly: $69.23
📆 Daily:   $9.86

✅ You're on track! Monthly surplus: $4,224.82
```

…plus a **custom** goal card.

> 🎬 **Wow moment 4 — it checks your plan against your life.** "$300/month"
> is the easy answer. The wow is *"you're on track — your surplus is $4,224."*
> It connected the goal to the numbers from prompt 2. It **remembered**.

---

### Prompt 5 — the split

```
Split this $90 dinner with Alice and Bob
```

**Expected**

```
═══ Split: Split this $90 dinner with Alice and Bob ═══

💵 Total: $90.00
👥 Split 3 ways:

  You             $   30.00
  Alice           $   30.00
  Bob             $   30.00

💡 Each person owes $30.00
```

…plus a **custom** split card with a "Remind everyone" button and a
per-person settle action.

> 🎬 **Wow moment 5 — the card is clickable.** Hit "Remind everyone" in the
> drawer. The click comes back to the agent as a selection and it answers.
> Cards are not a screenshot; they are a round-trip.

---

### Prompt 6 — the payment

```
How do I unlock Pro?
```

**Expected**

```
🔓 **Unlock BudgetBuddy Pro**

📦 BudgetBuddy Pro — Lifetime Access
💰 Amount: $4.99 USD (one-time)
🆔 Request ID: `aa20147e`
🔑 Reference: `ea255a42537a4af491ee54ec17c4903c`

Confirm with the payment card below.
I have sent you a payment request — approve it and Pro turns on the moment the payment is verified.
```

…plus a **review** card (approve / decline) with the amount on it. And in
the background the agent has sent a **real `RequestPayment`** — Fetch.ai's
Agent Payment Protocol message — to the buyer.

> 🎬 **Wow moment 6 — the payment is real, and it can fail.** This is the
> Fetch.ai *Agent Payment Protocol*, not a fake button. The seller verifies
> the buyer's commit against the buyer's own `agent1q…` identity. Show the
> counter-example: run `DEMO_FORGE=1 .venv/bin/python tools/payment_demo.py`
> and the seller **refuses**: *"signature does not verify against the
> sender's agent address."* A payment that cannot be faked is worth more
> than a payment that always says yes.

---

## 2. If something goes wrong

| Symptom | Cause | Fix |
|---|---|---|
| "I'm your AI budget coach" but nothing else | The Bureau is not running | `./tools/stop_bureau.sh 8001 && setsid ./keepalive.sh > /tmp/ka.log 2>&1 < /dev/null &` |
| ASI:One replies are slow (10s+) | Mailbox polling is 1s, but the agent may have dropped off Agentverse | Check the Almanac `status` is `active`; restart the keepalive |
| No cards appear | `ENABLE_CARDS=false` | `sed -i 's/^ENABLE_CARDS=.*/ENABLE_CARDS=true/' .env` and restart the keepalive |
| "address already in use" | A second Bureau/keepalive is running | `./tools/stop_bureau.sh 8001` (it also stops the keepalive) |
| The goal plan shows a weird date | The year is inferred from today | Use an explicit month+year: `by December 2027` |
| Gemini 503s / the coach says "offline mode" | Google-side outage | Nothing — deterministic fallback still produces insights (by design) |

---

## 3. Video shot list (2–3 minutes, unlisted on YouTube)

| # | Time | Shot | Narration beat |
|---|---|---|---|
| 1 | 0:00–0:12 | Terminal: `curl .../agent_info`, then the Agentverse profile page | "This is a real agent on Agentverse, with a mailbox — no server, no tunnel, no public URL. It dials out." |
| 2 | 0:12–0:25 | ASI:One chat, paste the raw CSV | "Here's a real bank export. I haven't cleaned it up. Paste it." |
| 3 | 0:25–0:50 | "How am I doing?" — the report, then **open the dashboard card** | "It categorised 18 transactions, found a 60% savings rate, and flagged 4 forgotten subscriptions. And that's just the text — there's a card too, with the same numbers." |
| 4 | 0:50–1:15 | "What subscriptions do I have?" — the list, then **swipe the carousel** | "Here's the part that matters: $95.96 a month in subscriptions — and rent is *not* in that list. It's a bill, not a subscription. A regex would have lumped them together." |
| 5 | 1:15–1:40 | "I want to save $3000 by August" | "It doesn't just divide. It checks the target against the actual surplus and tells me whether I'm on track." |
| 6 | 1:40–2:00 | "Split this $90 dinner with Alice and Bob" — then **click "Remind everyone"** | "The card isn't a picture. I click it, the click comes back to the agent as a message, and it responds." |
| 7 | 2:00–2:25 | "How do I unlock Pro?" — the review card | "And it can actually charge you. This is Fetch.ai's Agent Payment Protocol — a real RequestPayment, sent over the wire, verified against the buyer's agent identity." |
| 8 | 2:25–2:40 | Terminal: `DEMO_FORGE=1 .venv/bin/python tools/payment_demo.py` → CancelPayment | "Now the important half. I forged the signature. It refused: *the signature does not verify against the sender's agent address*. The payment can't be faked." |
| 9 | 2:40–2:55 | Terminal: the agent log showing six agents `active` | "Six agents, one job each, on the Agentverse Almanac. The orchestrator falls back in-process if any of them dies, so it never goes down." |
| 10 | 2:55–3:00 | Agentverse profile + QR/link on screen | "Try it: the link's on the page. It's live right now." |

**Narration rules**
- Say **"this is real"** once per segment where it's true, and show the
  evidence on screen the moment you say it. Don't claim anything you can't
  point at.
- Don't say "AI" when you mean "a rule-based fallback" — the coach works
  without an LLM and that's a **feature**, so frame it that way.
- Don't promise Stripe or on-chain payments. The default rail is a signed
  proof of commitment, and the code says exactly what it is.

---

## 4. ASI:One Shared Chat URL (for Devpost / the video end card)

1. Open ASI:One and start a chat with BudgetBuddy.
2. Run prompts 1–6 in order (a clean, complete run — the judges will
   open the link and scroll it).
3. Use ASI:One's **Share** action on that conversation to produce a
   shareable link.
4. Paste the link into Devpost and at the end of the video.

**Agent profile URL** (already live):
<https://agentverse.ai/agents/details/agent1qwv44y4c4yz47j58zhylm7rnev6qk4su0km42k69f8345ytt5s90jyxgaa9>
