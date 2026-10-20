# Going Live — Agentverse + ASI:One Registration

> **Phase 5 companion guide.** Follow this click-by-click to get BudgetBuddy
> answering inside a real ASI:One conversation.
>
> ⚠️ This is the riskiest phase — do **not** leave it for deadline day.

---

## Prerequisites

Before you start:

- [ ] Repo pushed to GitHub (done: `github.com/surjit12334-hue/budgetbuddy`)
- [ ] The Bureau runs locally: `./run.sh` prints 6 agent addresses
- [ ] You can hit it: `curl -X POST http://localhost:8001/submit -H "Content-Type: application/json" -d '{"session_id":"x","text":"Help"}'` returns a reply
- [ ] `ngrok` installed ([download](https://ngrok.com/download)) and logged in (`ngrok config add-authtoken YOUR_TOKEN`)

---

## Step 1 — Start the Bureau

In a dedicated terminal (keep it open):

```bash
cd budgetbuddy
./run.sh
```

You'll see six addresses, e.g.:

```
Host agent address:  agent1qwv44y4c4yz47j58zhylm7rnev6qk4su0km42k69f8345ytt5s90jyxgaa9
Ingest agent:        agent1qgusexn46534mpe5vdjumfv6yhaynr6m8w7yfvw5ul5r8qsd7djrz7d9v9u
...
REST endpoint:  POST http://localhost:8001/submit
```

**Copy the host agent address** — you need it in Step 4.

---

## Step 2 — Expose it with ngrok

In a second terminal:

```bash
ngrok http 8001
```

Copy the forwarding URL, e.g.:

```
Forwarding    https://abcd-12-34-56-78.ngrok-free.app -> http://localhost:8001
```

**Keep this terminal open.** The URL changes every time you restart ngrok on the free plan.

Quick check that the tunnel reaches the app:

```bash
curl -X POST https://abcd-12-34-56-78.ngrok-free.app/submit \
  -H "Content-Type: application/json" \
  -d '{"session_id":"t","text":"Help"}'
```

---

## Step 3 — Create the agent on Agentverse

1. Go to **https://agentverse.ai** and sign in (create a free account if needed).
2. In the sidebar click **Agents** → **My Agents**.
3. Click **+ Create Agent** (may appear as **Launch an Agent**).
4. Choose **Blank Agent** (not a template).
5. Fill in:
   - **Name:** `BudgetBuddy`
   - **Description:** *A multi-agent personal-finance coach. Paste your bank data, get analysis, set savings goals, split bills, and unlock Pro — all in chat.*
   - **Visibility:** **Public** (a judge must be able to see it)
6. Click **Create**.

You now have an **Agent Profile URL** like:

```
https://agentverse.ai/agents/details/agent1qwv44y4...
```

**Save this URL** — it's deliverable 7.4.

---

## Step 4 — Connect your agent

Agentverse needs to know where your agent lives.

1. On the agent's page, open the **Deploy** / **Connect** tab.
2. Select **Redirect to an external URL** (or **HTTP endpoint**).
3. Paste your ngrok URL + `/submit`:
   ```
   https://abcd-12-34-56-78.ngrok-free.app/submit
   ```
4. **Agent address:** paste the **host agent address** you copied in Step 1.
5. Click **Save** / **Connect**.

> ⚠️ **Important:** use the **host** agent's address. The host is the one that
> serves `/submit`; the sub-agents are internal to the Bureau.

---

## Step 5 — Enable the chat protocol

So ASI:One can talk to your agent:

1. Open the **Protocols** (or **Chat**) tab on the agent page.
2. Enable **Chat Protocol**.
3. Save.

---

## Step 6 — First ASI:One message

1. Go to **https://asi1.ai** (ASI:One).
2. Find your agent — search **BudgetBuddy**, or use the Agent Profile URL.
3. Start a chat and send:

   ```
   Help
   ```

**Expected:** the BudgetBuddy help menu.

### If it doesn't reply — troubleshoot

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| No reply at all | Bureau not running | Re-check `./run.sh` terminal |
| No reply | ngrok URL wrong/stale | Re-copy the URL from the ngrok terminal |
| 404 / "unable to route" | Wrong agent address | Use the **host** address from Step 1 |
| Works in curl, not ASI:One | Chat protocol not enabled | Redo Step 5 |
| Intermittent timeouts | ngrok free-tier hiccups | Send again; see Step 8 |
| Envelope/session errors | `session_id` mismatch | ASI:One sets this; check host logs |

Watch the Bureau terminal — every request logs here:

```
[host] ← external  session=...  text='Help'
[bus] → ingest  IngestRequest
[ingest] → host  38 txns parsed
[bus] ← ingest  IngestResponse
```

No log line = the request never arrived (ngrok/tunnel issue).
Log line but no reply = look further down the log.

---

## Step 7 — Full 6-turn demo, verify persistence

Run the whole flow in ASI:One:

1. Paste the 38-row sample CSV
2. `How am I doing?`
3. `What subscriptions do I have?`
4. `I want to save $3000 by August`
5. `Split this $90 dinner with Alice and Bob`
6. `How do I unlock Pro?`

**Persistence check:** turn 2 must "remember" turn 1's data. If it says
*"I don't have any transactions yet"*, the `session_id` isn't being kept
stable across turns — check host logs for a changing session value.

---

## Step 8 — Demo-window uptime plan

A 30-minute demo needs the agent alive the whole time.

- [ ] **Disable sleep** on your laptop (Screen Locking / Power settings)
- [ ] Keep **both** terminals open (Bureau + ngrok)
- [ ] If the ngrok URL changes, **re-do Step 4** — this is the #1 cause of mid-demo failure
- [ ] Optional restart script:

```bash
#!/usr/bin/env bash
# restart.sh — bounce the Bureau if it dies
while true; do
  ./run.sh || true
  echo "Bureau exited — restarting in 3s"
  sleep 3
done
```

- [ ] Do a **cold dry run**: close everything, follow this guide from Step 1, confirm it works — then you can trust it live.

---

## Step 9 — Testnet faucet (for Payment, Phase 6)

When you reach the payment step:

1. Go to the Fetch.ai **testnet faucet** (linked from the ASI:One / Agentverse docs).
2. Enter your agent's wallet address (shown in Agentverse under the agent's **Wallet**).
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
| `GEMINI_API_KEY` | *(empty)* | Optional LLM; app works without it |
| `GEMINI_MODEL` | `gemini-3.8-flash` | Model name |
| `ENABLE_CARDS` | `false` | Interactive cards (Phase 6) |
| `SESSION_TTL_HOURS` | `24` | Session/data purge window |
| `AGENT_TIMEOUT_SECONDS` | `15` | Sub-agent timeout before fallback |
