# Going Live — Agentverse + ASI:One Registration

> **Phase 5 companion guide.** Follow this click-by-click to get BudgetBuddy
> answering inside a real ASI:One conversation.
>
> ⚠️ This is the riskiest phase — do **not** leave it for deadline day.

---

## How the connection works (read this first)

BudgetBuddy uses the **Agentverse mailbox**, not a public tunnel.

The host agent **dials out** to Agentverse and keeps that connection open.
Agentverse then relays ASI:One messages to it. This means:

- ✅ **No ngrok.** No public URL, no port forwarding, no URL rotation.
- ✅ **No firewall changes.** It's an outbound connection.
- ✅ **Stable for the demo window.** The connection re-establishes itself.

> **Why not a tunnel?** uAgents *reserves* `/submit` and rejects it from any
> non-local client (`uagents/asgi.py`), so a custom REST route can never be
> reached through a tunnel or from ASI:One. The mailbox + Chat Protocol is the
> mechanism uAgents is designed around — and it satisfies the Phase 5 gate.

---

## Prerequisites

- [ ] Repo pushed to GitHub (done: `github.com/surjit12334-hue/budgetbuddy`)
- [ ] Python venv set up (`.venv`)
- [ ] An internet connection (the mailbox needs to reach `agentverse.ai`)

You do **not** need ngrok, a domain, or a public IP.

---

## Step 1 — Start the Bureau

In a dedicated terminal (keep it open):

```bash
cd budgetbuddy
./keepalive.sh
```

Look for these two lines — they are the proof the mailbox connected:

```
INFO:  [ host]: Starting mailbox client for https://agentverse.ai
INFO:  [host]: Agent registration status updated to active
```

You'll also see the six agent addresses. **Copy the host agent address** —
you need it in Step 4:

```
Host agent address:  agent1qwv44y4c4yz47j58zhylm7rnev6qk4su0km42k69f8345ytt5s90jyxgaa9
```

> If you see `Agent mailbox not found: create one using the agent inspector`,
> that's expected on the very first run — Step 4 fixes it. It is **not** an
> error, and you won't need to restart anything after creating the mailbox.

---

## Step 2 — Verify locally (do not skip)

In a second terminal:

```bash
cd budgetbuddy
.venv/bin/python tools/preflight.py
```

You must see **`ALL CHECKS PASSED — ready for ASI:One`**. This exercises the
Bureau, all 6 agents, the full 6-turn flow, and session persistence.

If something fails, fix it here — before touching Agentverse.

---

## Step 3 — Confirm the agent is registered

Ask the Almanac (the public agent registry) about your host address:

```bash
curl -s https://agentverse.ai/v1/almanac/agents/agent1qwv44y4c4yz47j58zhylm7rnev6qk4su0km42k69f8345ytt5s90jyxgaa9
```

**Expected** — note `"status":"active"`, `"type":"mailbox"`, and two protocols:

```json
{
  "status": "active",
  "type": "mailbox",
  "address": "agent1qwv44y4c4yz47j58zhylm7rnev6qk4su0km42k69f8345ytt5s90jyxgaa9",
  "endpoints": [{"url": "https://agentverse.ai/v2/agents/mailbox/submit"}],
  "protocols": ["30a801ed...", "b5165e61..."]
}
```

If `status` is not `active`, wait a few seconds and retry — registration
happens shortly after startup.

---

## Step 4 — Agentverse account + create the mailbox

This is the part that needs **you** — it cannot be automated.

1. Go to **https://agentverse.ai** and sign in (create a free account if needed).
2. In the sidebar click **Agents** → **My Agents**.
3. Find your agent. Because it self-registered, it may already appear; if not,
   click **+ Create Agent** → **Blank Agent** and paste the **host agent
   address** from Step 1.
4. Fill in / confirm:
   - **Name:** `BudgetBuddy`
   - **Description:** *A multi-agent personal-finance coach. Paste your bank data, get analysis, set savings goals, split bills, and unlock Pro — all in chat.*
   - **Visibility:** **Public** (a judge must be able to see it)
5. Open the agent's page and go to the **Agent Inspector** / **Mailbox** tab.
6. Click **Create Mailbox**.

> ✅ **Done when:** the mailbox exists. The Bureau terminal will stop logging
> `Agent mailbox not found` — **within seconds, no restart needed**.

7. Copy the **Agent Profile URL**:
   ```
   https://agentverse.ai/agents/details/agent1qwv44y4c4yz47j58zhylm7rnev6qk4su0km42k69f8345ytt5s90jyxgaa9
   ```
   **Save this** — it's deliverable 7.4.

---

## Step 5 — Confirm the chat protocol is enabled

On the agent's page:

1. Open the **Protocols** (or **Chat**) tab.
2. You should see the chat protocol listed (digest starting `30a801ed…`).
3. Enable **Chat Protocol** if it isn't already.
4. Save.

BudgetBuddy registers the protocol automatically at startup, so it normally
just appears here.

---

## Step 6 — First ASI:One message

1. Go to **https://asi1.ai** (ASI:One).
2. Find your agent — search **BudgetBuddy**, or open your Agent Profile URL.
3. Start a chat and send:

   ```
   Help
   ```

**Expected:** the BudgetBuddy help menu. ✅ **Phase 5 gate reached.**

### If it doesn't reply — troubleshoot

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| No reply | Bureau not running | Re-check the `./keepalive.sh` terminal |
| No reply | Mailbox not created | Redo Step 4.6 |
| `mailbox not found` still logging | Mailbox not created yet | Redo Step 4.6 |
| Works locally, not ASI:One | Chat protocol not enabled | Redo Step 5 |
| No reply, no logs at all | Request never arrived | Re-check Step 3 (`status: active`) |
| Intermittent drop | Transient network | Send again; mailbox reconnects |
| Memory lost between turns | `session_id` collapse | Check host logs — each chat sender gets `asi1-<address>`, so look for a changing value |

Watch the Bureau terminal — every chat message logs here:

```
[chat] ← asi1  session=asi1-agent1...  text='Help'
[host] intent: help
[chat] → asi1  461 chars
```

- **`[chat] ←` appears** → ASI:One reached you. Any issue is downstream.
- **`[chat] ←` does not appear** → the message never arrived (mailbox/Agentverse side).

---

## Step 7 — Full 6-turn demo, verify persistence

Run the whole flow in ASI:One:

1. Paste the 38-row sample CSV (`samples/sample_bank.csv`)
2. `How am I doing?`
3. `What subscriptions do I have?`
4. `I want to save $3000 by August`
5. `Split this $90 dinner with Alice and Bob`
6. `How do I unlock Pro?`

**Persistence check:** turn 2 must "remember" turn 1's data. If it says
*"I don't have any transactions yet"*, the chat sender address isn't stable
across turns — check host logs for a changing `asi1-…` session value.

---

## Step 8 — Demo-window uptime plan

A 30-minute demo needs the agent alive the whole time.

- [ ] **Disable sleep** on your laptop (Screen Locking / Power settings)
- [ ] Keep the Bureau terminal open, running `./keepalive.sh` (auto-restarts on crash)
- [ ] Confirm **internet stays up** — the mailbox needs it (no tunnel to babysit)
- [ ] Do a **cold dry run**: close everything, follow this guide from Step 1, confirm it works — then you can trust it live

> Unlike a tunnel, there is **no URL to re-paste** if something restarts.
> The mailbox reconnects on its own — that's why this approach is safer
> for a live demo.

---

## Step 9 — Testnet faucet (for Payment, Phase 6)

When you reach the payment step:

1. Go to the Fetch.ai **testnet faucet** (linked from the ASI:One / Agentverse docs).
2. Enter your agent's wallet address. It's printed at startup:
   ```
   WARNING:  [ host]: To enable contract registration, send funds to wallet address: fetch1...
   ```
3. Request testnet tokens (usually `TESTFET`).
4. Use them for the Payment Protocol request in Phase 6.

---

## Deliverables checklist

Collect these for the submission (Phase 7):

- [ ] **Agent Profile URL** — `https://agentverse.ai/agents/details/...`
- [ ] **ASI:One Shared Chat URL** — from a clean run (share button in ASI:One)
- [ ] **Demo video** — 2–3 min (Phase 7.2)
- [ ] **"Operating since" note** — keep the agent alive after submitting, for the viability bonus

---

## Reference — Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `HOST_SEED` | *(required)* | Unique seed phrase → deterministic agent address |
| `HOST_PORT` | `8001` | Port the Bureau serves on |
| `HOST_ENDPOINT` | `http://localhost:8001` | Local endpoint |
| `ENABLE_MAILBOX` | `true` | Connect the host to the Agentverse mailbox |
| `ENABLE_AGENTVERSE` | `true` | Register the agent on Agentverse / Almanac |
| `GEMINI_API_KEY` | *(empty)* | Optional LLM; app works without it |
| `GEMINI_MODEL` | `gemini-3.8-flash` | Model name |
| `ENABLE_CARDS` | `false` | Interactive cards (Phase 6) |
| `SESSION_TTL_HOURS` | `24` | Session/data purge window |
| `AGENT_TIMEOUT_SECONDS` | `15` | Sub-agent timeout before fallback |

---

## Reference — Local REST endpoint (testing only)

`POST /submit` still works **on localhost** for curl and the test suite:

```bash
curl -X POST http://localhost:8001/submit \
  -H "Content-Type: application/json" \
  -d '{"session_id":"demo","text":"Help"}'
```

⚠️ **This only works from `localhost`.** uAgents reserves `/submit` and
rejects external clients, which is exactly why the Chat Protocol + mailbox is
used for ASI:One.
