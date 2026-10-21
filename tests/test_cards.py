#!/usr/bin/env python3
"""Phase 6 — ASI:One interactive-card schema conformance.

The builders in core/cards.py were rewritten against the official schema:

    https://innovationlab.fetch.ai/resources/docs/interactive-cards/asi-interactive-cards

These tests enforce the parts of that spec that fail SILENTLY if you get
them wrong — ASI:One just drops the card and shows plain text, so a
schema mistake is invisible unless you assert on it.

Rules under test:
  * metadata keys and value types (dict[str, str])
  * card_protocol_version == "1" (omitting it drops the card)
  * card_payload is the payload itself, NOT wrapped in {"data": {...}}
  * card_kind is one of carousel/detail/form/review/custom
  * payload <= 64 KB
  * custom trees nest no deeper than 8 levels
  * form fields use the real "kind" key (not "type") and select needs options
  * CTAs carry a "selection" block the agent will receive back

Run:  .venv/bin/python tests/test_cards.py
"""

import asyncio
import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

asyncio.set_event_loop(asyncio.new_event_loop())

# Cards must be ON for the builders to emit metadata.
os.environ["ENABLE_CARDS"] = "true"

from core.cards import CardBuilder, VALID_KINDS, MAX_PAYLOAD_BYTES  # noqa: E402
from core.analyzer import Analyzer  # noqa: E402
from core.categorizer import Categorizer  # noqa: E402
from core.parser import parse_any  # noqa: E402

PASSED = 0
FAILED = 0
SAMPLE = pathlib.Path(__file__).resolve().parent.parent / "samples" / "sample_bank.csv"


def check(label: str, cond: bool, detail: str = "") -> None:
    global PASSED, FAILED
    if cond:
        PASSED += 1
        print(f"  ✅ {label}")
    else:
        FAILED += 1
        print(f"  ❌ {label}  {detail}")


def depth(node, level=1):
    """Max nesting depth of an element tree (root counts as level 1).

    ``list`` items are containers too: their ``children`` sit one level
    below the list, which is exactly the nesting ASI:One measures.
    """
    if not isinstance(node, dict):
        return level
    kids = list(node.get("children") or [])
    if node.get("type") == "list":
        for item in node.get("items") or []:
            kids.extend(item.get("children") or [])
    if not kids:
        return level
    return max(depth(k, level + 1) for k in kids)


def test_metadata(cards: CardBuilder, kind: str, payload: dict, label: str) -> None:
    """Assert ASI:One would accept this metadata block."""
    meta = cards.as_metadata(kind, payload)

    check(f"{label}: version is \"1\"", meta.get("card_protocol_version") == "1")
    check(f"{label}: requires_card_interaction set",
          meta.get("requires_card_interaction") in ("true", "false"))
    check(f"{label}: kind valid", meta.get("card_kind") in VALID_KINDS)
    check(f"{label}: all values are strings",
          all(isinstance(v, str) for v in meta.values()),
          f"got {[type(v).__name__ for v in meta.values()]}")

    raw = meta.get("card_payload", "")
    check(f"{label}: payload is a JSON string", isinstance(raw, str))
    try:
        decoded = json.loads(raw)
        ok = True
    except ValueError as e:
        ok = False
        decoded = None
        check(f"{label}: payload parses", False, str(e))
    if ok:
        check(f"{label}: payload parses", True)
        check(f"{label}: payload NOT wrapped in 'data'",
              "data" not in decoded or kind == "custom",
              "found top-level 'data' key — ASI:One expects the payload at top level")
        check(f"{label}: payload under 64 KB",
              len(raw.encode()) <= MAX_PAYLOAD_BYTES)
        if kind == "custom":
            check(f"{label}: custom root present", "root" in decoded)
            check(f"{label}: nesting <= 8 levels", depth(decoded.get("root", {})) <= 8,
                  f"depth {depth(decoded.get('root', {}))}")


def main() -> int:
    print("=" * 60)
    print("  PHASE 6 — ASI:ONE INTERACTIVE CARD SCHEMA")
    print("=" * 60)

    cards = CardBuilder()
    check("cards enabled via ENABLE_CARDS", cards.enabled is True)

    txns = parse_any(SAMPLE.read_text())
    Categorizer().categorize_all(txns)
    analysis = Analyzer().analyze(txns)

    shares = [
        {"name": "You", "amount": 30.0},
        {"name": "Alice", "amount": 30.0},
        {"name": "Bob", "amount": 30.0},
    ]

    # ── 1. each builder produces valid metadata ───────────────────────
    print("\n[1] Wire envelope conformance")
    test_metadata(cards, "form", cards.build_onboarding_form(), "onboarding")
    test_metadata(cards, "custom", cards.build_dashboard(analysis), "dashboard")
    test_metadata(cards, "carousel", cards.build_insights_carousel(analysis.insights), "insights")
    test_metadata(cards, "custom", cards.build_goal_card(
        {"target_amount": 3000, "deadline": "Aug 2027", "monthly_target": 500, "on_track": True}
    ), "goal")
    test_metadata(cards, "custom", cards.build_split_card("Dinner", 90, shares), "split")
    test_metadata(cards, "review", cards.build_checkout_card("req_1", 4.99, "Pro lifetime"), "checkout")
    test_metadata(cards, "carousel", cards.build_subscriptions_card(analysis), "subscriptions")

    # ── 2. form uses the real field schema ────────────────────────────
    print("\n[2] Form field schema (kind, not type)")
    form = cards.build_onboarding_form()
    check("has a title", bool(form.get("title")))
    check("has fields", len(form.get("fields", [])) > 0)
    check("has submit_cta", "submit_cta" in form)
    check("submit_cta has selection", "selection" in form["submit_cta"])
    valid_kinds = {"text", "number", "email", "select", "checkbox"}
    for f in form["fields"]:
        check(f"field {f['name']!r} uses 'kind'", "kind" in f, f"keys: {list(f)}")
        check(f"field {f['name']!r} kind valid", f.get("kind") in valid_kinds)
        check(f"field {f['name']!r} has label", bool(f.get("label")))
        if f.get("kind") == "select":
            check(f"select {f['name']!r} has options", bool(f.get("options")))

    # ── 3. carousel items are well formed ─────────────────────────────
    print("\n[3] Carousel item schema")
    carousel = cards.build_subscriptions_card(analysis)
    check("has title", bool(carousel.get("title")))
    check("has items", len(carousel.get("items", [])) > 0)
    for it in carousel["items"]:
        check(f"item {it.get('id')!r} has id", "id" in it)
        check(f"item {it.get('id')!r} has title", "title" in it)
        check(f"item {it.get('id')!r} has primary_cta", "primary_cta" in it)
        check(f"item {it.get('id')!r} cta has selection",
              "selection" in it.get("primary_cta", {}))

    # Subscriptions card must only contain discretionary subs (rent bug).
    names = " ".join(it["title"].lower() for it in carousel["items"])
    check("subscriptions card excludes rent", "rent" not in names, f"got {names}")

    # ── 4. review card has both CTAs ──────────────────────────────────
    print("\n[4] Review card schema")
    review = cards.build_checkout_card("req_1", 4.99, "Pro lifetime")
    check("has summary_rows", len(review.get("summary_rows", [])) > 0)
    check("summary rows are label/value",
          all("label" in r and "value" in r for r in review["summary_rows"]))
    check("has approve_cta", "approve_cta" in review)
    check("has reject_cta", "reject_cta" in review)
    check("approve_cta has selection", "selection" in review["approve_cta"])
    check("reject_cta has selection", "selection" in review["reject_cta"])
    check("approve carries request_id",
          review["approve_cta"]["selection"].get("request_id") == "req_1")

    # ── 5. custom element-tree primitives are valid ───────────────────
    print("\n[5] Custom element-tree primitives")
    primitives = {
        "section", "group", "divider", "text", "heading",
        "image", "badge", "button", "input", "list", "choice_grid",
    }

    def collect_types(node, found):
        if isinstance(node, dict):
            if "type" in node:
                found.add(node["type"])
            for k in ("children", "items"):
                for c in node.get(k, []) or []:
                    collect_types(c, found)
            if "root" in node:
                collect_types(node["root"], found)
        return found

    for label, payload in (
        ("dashboard", cards.build_dashboard(analysis)),
        ("goal", cards.build_goal_card(
            {"target_amount": 3000, "deadline": "Aug", "monthly_target": 500, "on_track": True})),
        ("split", cards.build_split_card("Dinner", 90, shares)),
    ):
        types = collect_types(payload, set())
        unknown = types - primitives
        check(f"{label}: only real primitives", not unknown, f"unknown: {unknown}")

    # Per-primitive required keys, straight from the spec.  A missing
    # 'direction' or 'value' rejects the entire card, not just the node.
    def validate_tree(node, label, path="root"):
        if not isinstance(node, dict) or "type" not in node:
            return
        t = node["type"]
        if t == "text":
            check(f"{label}: {path} text has value", "value" in node)
            check(f"{label}: {path} text style valid",
                  node.get("style") in (None, "body", "muted", "emphasis"),
                  f"style={node.get('style')!r}")
        elif t == "heading":
            check(f"{label}: {path} heading has value", "value" in node)
            check(f"{label}: {path} heading level 1-3",
                  node.get("level", 2) in (1, 2, 3))
        elif t == "group":
            check(f"{label}: {path} group has direction",
                  node.get("direction") in ("row", "column"),
                  f"direction={node.get('direction')!r}")
        elif t == "button":
            check(f"{label}: {path} button has label", "label" in node)
            check(f"{label}: {path} button has action.selection",
                  "selection" in node.get("action", {}))
        elif t == "list":
            check(f"{label}: {path} list has items",
                  isinstance(node.get("items"), list))
            for i, it in enumerate(node.get("items", [])):
                check(f"{label}: {path} item {i} has children",
                      isinstance(it.get("children"), list))
                for c in it.get("children", []):
                    validate_tree(c, label, f"{path}.item{i}")
                if "action" in it:
                    check(f"{label}: {path} item {i} action has selection",
                          "selection" in it["action"])
        elif t == "badge":
            check(f"{label}: {path} badge has label", "label" in node)
            check(f"{label}: {path} badge variant valid",
                  node.get("variant") in (None, "info", "success", "warning"))
        elif t == "section":
            check(f"{label}: {path} section has children",
                  isinstance(node.get("children"), list))
        if t in ("section", "group"):
            for c in node.get("children", []):
                validate_tree(c, label, f"{path}>")

    for label, payload in (
        ("dashboard", cards.build_dashboard(analysis)),
        ("goal", cards.build_goal_card(
            {"target_amount": 3000, "deadline": "Aug", "monthly_target": 500, "on_track": True})),
        ("split", cards.build_split_card("Dinner", 90, shares)),
    ):
        validate_tree(payload.get("root"), label)

    # ── 6. disabled means no card, fallback intact ────────────────────
    print("\n[6] Cards disabled → empty metadata (markdown fallback)")
    off = CardBuilder()
    off.enabled = False
    check("as_metadata returns {} when disabled",
          off.as_metadata("form", {"title": "x"}) == {})

    # ── 7. bad input is rejected loudly, not silently ─────────────────
    print("\n[7] Validation")
    try:
        cards.as_metadata("nonsense", {"a": 1})
        check("unknown card_kind raises", False, "no error raised")
    except ValueError:
        check("unknown card_kind raises", True)

    big = {"title": "x" * (MAX_PAYLOAD_BYTES + 10)}
    try:
        cards.as_metadata("carousel", big)
        check("oversized payload raises", False, "no error raised")
    except ValueError:
        check("oversized payload raises", True)

    meta = cards.as_metadata("carousel", {"title": "t"}, drawer_width_px=9999)
    check("drawer width clamped to 800",
          meta.get("preferred_drawer_width_px") == "800")

    print("\n" + "=" * 60)
    print(f"RESULTS: {PASSED} passed, {FAILED} failed")
    print("=" * 60)
    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
