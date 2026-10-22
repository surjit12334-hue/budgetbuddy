"""Where BudgetBuddy's agent identities come from.

A uAgent's address is derived from its seed, so the seed *is* the
identity.  If the seeds are hard-coded in the source, then **every clone
of this repository has the same agent addresses** — two people running
it at the same time fight over the same Agentverse record and the same
mailbox, and a judge's clone can hijack the demo agent's identity.

So the seeds are resolved in this order:

1. ``HOST_SEED`` (and ``<ROLE>_SEED`` for the sub-agents) from the
   environment — explicit always wins.
2. A **per-machine seed** generated once with ``secrets.token_hex`` and
   written to ``.budgetbuddy_identity`` (git-ignored), so the identity
   survives restarts but is never shared between clones.

The file also records the resulting agent addresses, which lets the
demo tools find the Bureau without importing ``agents.host`` — importing
that module would instantiate a *phantom* host agent inside the demo
process, and uAgents would then deliver the buyer's message "locally"
to it instead of to the real Bureau.
"""

import json
import os
import secrets
import urllib.request
from pathlib import Path
from typing import Dict, Optional

ROOT = Path(__file__).resolve().parent.parent

#: Where the per-machine seed and the resolved addresses are kept.
IDENTITY_FILE = ROOT / ".budgetbuddy_identity"


def _load_dotenv() -> None:
    """Load ``.env`` into ``os.environ`` for variables that are not set yet.

    Same rule as ``env.sh``: an already-exported variable wins.  This
    matters because an agent's address is a pure function of its seed —
    if the Bureau and the demo tools resolve *different* seeds, the
    tools talk to an agent that does not exist.  Loading ``.env`` here
    means every process resolves the same seed, whether or not it was
    started through ``run.sh``.
    """
    try:
        text = (ROOT / ".env").read_text(encoding="utf-8")
    except OSError:
        return
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        else:
            value = value.split(" #")[0].strip()
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv()

#: The value ``.env.example`` ships with.  It is a placeholder, not a
#: seed — treating it as one would give every clone the same identity.
PLACEHOLDER_SEED = "replace with a long unique seed phrase for your host agent"

#: The seed the original (pre-2026-10) release used, kept so an
#: existing deployment can keep its address by setting HOST_SEED to it.
LEGACY_HOST_SEED = "budgetbuddy host agent seed v1"


def _clean(value: str) -> str:
    """Strip whitespace and the quotes a shell would have removed."""
    return (value or "").strip().strip('"').strip("'").strip()


def _read() -> Dict:
    try:
        return json.loads(IDENTITY_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write(data: Dict) -> None:
    try:
        IDENTITY_FILE.write_text(
            json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    except OSError:
        # A read-only checkout must not stop the agent from starting.
        pass


def base_seed() -> str:
    """The per-machine seed: generated once, then reused forever.

    This is the fallback for every role that has no explicit seed in
    the environment.
    """
    env = _clean(os.environ.get("HOST_SEED", ""))
    if env and env != PLACEHOLDER_SEED:
        return env

    data = _read()
    seed = data.get("base_seed")
    if seed:
        return seed

    seed = "budgetbuddy " + secrets.token_hex(24)
    data["base_seed"] = seed
    _write(data)
    return seed


def resolve_seed(role: str = "host") -> str:
    """The seed for one agent role.

    ``host`` uses ``HOST_SEED``.  Every other role uses
    ``<ROLE>_SEED`` if it is set, and otherwise a seed derived from the
    per-machine base — so a clone gets its own set of six agents
    without anyone having to configure anything.
    """
    role = (role or "host").lower()
    if role == "host":
        env = _clean(os.environ.get("HOST_SEED", ""))
        if env and env != PLACEHOLDER_SEED:
            return env
        return base_seed()

    env = _clean(os.environ.get(f"{role.upper()}_SEED", ""))
    if env:
        return env
    return f"{base_seed()} {role}"


def record_addresses(addresses: Dict[str, str]) -> None:
    """Remember the agents' addresses so other processes can find them."""
    data = _read()
    known = dict(data.get("addresses") or {})
    known.update({k: v for k, v in addresses.items() if v})
    data["addresses"] = known
    # Persist the seed those addresses came from, not just the addresses.
    # An agent's address is a pure function of its seed, so recording only
    # the address means a machine that loses its `.env` (which is
    # git-ignored) generates a brand-new seed on the next start — silently
    # changing the agent's identity, orphaning its Agentverse mailbox and
    # every link that points at it.  With the seed in the file, the
    # identity is recoverable: `base_seed()` falls back to it.
    try:
        data["base_seed"] = base_seed()
    except Exception:  # pragma: no cover - defensive
        pass
    _write(data)


def derived_address(role: str = "host") -> Optional[str]:
    """The address this role's seed produces right now.

    An agent's address is a pure function of its seed, so this is the
    authoritative answer to "who is the live agent?" — it depends on no
    file and on no other process having imported this module first.
    """
    try:
        from uagents_core.identity import Identity
    except ImportError:  # pragma: no cover - uagents is always installed
        return None
    try:
        return Identity.from_seed(resolve_seed(role), 0).address
    except Exception:  # pragma: no cover - defensive
        return None


def known_address(role: str = "host") -> Optional[str]:
    """The address of the live agent for this role.

    The recorded address wins when it agrees with the seed we resolve
    right now; otherwise the derived address wins.  A file written by a
    process that resolved a *different* seed (for example a test that
    imported the host module without ``.env``) can therefore never
    point the demo tools at an agent that does not exist.
    """
    role = (role or "host").lower()
    recorded = (_read().get("addresses") or {}).get(role)
    derived = derived_address(role)
    if recorded and derived and recorded == derived:
        return recorded
    if derived:
        return derived
    return recorded


def live_bureau_address(role: str = "host", port: Optional[int] = None) -> Optional[str]:
    """Ask the Bureau running on this machine which agent it is.

    This is the only answer that cannot be wrong: the health endpoint is
    served by the process that is actually answering ASI:One.  The demo
    tools use it first, so a Bureau started with an overridden
    ``HOST_SEED`` is still found, and a stale identity file can never
    send the demo to a different agent than the live one.
    """
    if port is None:
        port = int(os.environ.get("HOST_PORT", "8001"))
    try:
        with urllib.request.urlopen(
            f"http://localhost:{port}/health", timeout=5
        ) as resp:
            data = json.loads(resp.read())
    except Exception:
        return None
    address = (data.get("agents") or {}).get(role)
    return address or None


def identity_summary() -> str:
    """A one-line description of the identity in use, for the startup log."""
    data = _read()
    addresses = data.get("addresses") or {}
    host = addresses.get("host")
    if not host:
        return "identity: not yet resolved"
    if base_seed() == LEGACY_HOST_SEED:
        # This is the *published* demo identity: it is registered on
        # Agentverse and printed in the README, the Devpost draft and the
        # demo script.  It is shared on purpose — telling the operator to
        # "make it unique" would orphan the mailbox and break every
        # published link, so say the opposite.
        return f"identity: {host} (published demo identity — keep HOST_SEED as it is)"
    return f"identity: {host} (private to this machine)"
