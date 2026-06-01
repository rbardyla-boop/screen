"""Unit tests for vault_brief — the proactive Morning Brief (Second Brain 2.0).

These tests cover the deterministic core (no env, no filesystem, no network):
staleness ranking from .loop-state.json data, next-action extraction, brief and
notification rendering, Notifier delivery routing, and systemd unit generation.
"""
import os
import sys
from datetime import date

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vault_brief import (  # noqa: E402
    Loop,
    Notifier,
    diversify_by_source,
    extract_next_action,
    fingerprint,
    is_signal_loop,
    rank_stale_loops,
    render_brief,
    render_notification,
    render_systemd_units,
)


# --- helpers ---------------------------------------------------------------

GAP_A = "[[Memory/Open-Loops.md]] — TODO: finish the API keys thing"
GAP_B = "[[Memory/Active Projects/essay.md]] — never finished the late-institutions section"
GAP_C = "[[Memory/Skills/foo/SKILL.md]] — SKILL DEBT: not used in 44 days (use it or kill it)"
GAP_D = "[[Memory/Notes/deploy.md]] — need to actually test the Screenpipe summary end-to-end"


def _state(today: date, ages: dict[str, int]) -> dict[str, str]:
    """Build a {fingerprint: first_seen_iso} loop-state for the given gaps/ages."""
    from datetime import timedelta
    return {
        fingerprint(gap): (today - timedelta(days=age)).isoformat()
        for gap, age in ages.items()
    }


# --- ranking ---------------------------------------------------------------

def test_rank_orders_by_staleness_oldest_first():
    today = date(2026, 6, 1)
    gaps = [GAP_A, GAP_B, GAP_D]
    state = _state(today, {GAP_A: 2, GAP_B: 30, GAP_D: 9})

    ranked = rank_stale_loops(gaps, state, today, top_n=3)

    assert [loop.gap for loop in ranked] == [GAP_B, GAP_D, GAP_A]
    assert ranked[0].age_days == 30
    assert ranked[-1].age_days == 2


def test_rank_respects_top_n():
    today = date(2026, 6, 1)
    gaps = [GAP_A, GAP_B, GAP_C, GAP_D]
    state = _state(today, {GAP_A: 1, GAP_B: 2, GAP_C: 3, GAP_D: 4})

    ranked = rank_stale_loops(gaps, state, today, top_n=3)

    assert len(ranked) == 3
    assert ranked[0].gap == GAP_D  # oldest


def test_rank_defaults_unknown_loop_to_zero_age():
    today = date(2026, 6, 1)
    # GAP_A has no entry in state -> treated as first seen today (age 0)
    ranked = rank_stale_loops([GAP_A], {}, today, top_n=3)

    assert len(ranked) == 1
    assert ranked[0].age_days == 0


def test_rank_is_deterministic_on_age_ties():
    today = date(2026, 6, 1)
    gaps = [GAP_D, GAP_A]  # input order should not decide ties
    state = _state(today, {GAP_A: 5, GAP_D: 5})

    first = rank_stale_loops(gaps, state, today, top_n=2)
    second = rank_stale_loops(list(reversed(gaps)), state, today, top_n=2)

    assert [loop.gap for loop in first] == [loop.gap for loop in second]


def test_rank_parses_source_and_text():
    today = date(2026, 6, 1)
    ranked = rank_stale_loops([GAP_A], _state(today, {GAP_A: 1}), today)

    assert ranked[0].source == "[[Memory/Open-Loops.md]]"
    assert ranked[0].text == "TODO: finish the API keys thing"


def test_rank_handles_gap_without_separator():
    today = date(2026, 6, 1)
    weird = "[[Memory/x.md]] no em-dash separator here"
    ranked = rank_stale_loops([weird], {}, today)

    # Must not crash; whole string becomes the text, source falls back to ""
    assert ranked[0].text  # non-empty
    assert isinstance(ranked[0], Loop)


# --- signal filtering (drop headings / scaffolding) ------------------------

def test_is_signal_loop_drops_markdown_headings():
    assert not is_signal_loop("[[Memory/x.md]] — ## How to Capture New Open Loops")
    assert not is_signal_loop("[[Memory/x.md]] — ### CURRENT OPEN LOOPS (raw capture)")


def test_is_signal_loop_drops_scaffolding_phrases():
    assert not is_signal_loop("[[Memory/Open-Loops.md]] — Throw unfinished thoughts here")
    assert not is_signal_loop("[[Memory/Open-Loops.md]] — Format examples")


def test_is_signal_loop_drops_too_short():
    assert not is_signal_loop("[[Memory/x.md]] — todo")


def test_is_signal_loop_keeps_real_loops():
    assert is_signal_loop(GAP_A)  # TODO: finish the API keys thing
    assert is_signal_loop(GAP_B)  # never finished the late-institutions section
    assert is_signal_loop(GAP_C)  # SKILL DEBT
    assert is_signal_loop("[[Memory/foo.md]] — (note titled as open work)")


# --- source diversification ------------------------------------------------

def test_diversify_spreads_across_sources():
    today = date(2026, 6, 1)
    g1 = "[[Memory/a.md]] — TODO: alpha"
    g2 = "[[Memory/a.md]] — TODO: beta"
    g3 = "[[Memory/a.md]] — TODO: gamma"
    g4 = "[[Memory/b.md]] — TODO: delta"
    state = _state(today, {g1: 10, g2: 9, g3: 8, g4: 5})
    ranked = rank_stale_loops([g1, g2, g3, g4], state, today, top_n=4)

    top = diversify_by_source(ranked, per_source=1, top_n=2)

    assert [loop.source for loop in top] == ["[[Memory/a.md]]", "[[Memory/b.md]]"]


def test_diversify_backfills_when_sources_scarce():
    today = date(2026, 6, 1)
    g1 = "[[Memory/a.md]] — TODO: alpha"
    g2 = "[[Memory/a.md]] — TODO: beta"
    state = _state(today, {g1: 10, g2: 9})
    ranked = rank_stale_loops([g1, g2], state, today, top_n=2)

    top = diversify_by_source(ranked, per_source=1, top_n=3)

    # Only two loops exist (same source); backfill returns both, stalest first.
    assert [loop.gap for loop in top] == [g1, g2]


# --- next action -----------------------------------------------------------

def test_next_action_for_skill_debt():
    action = extract_next_action("SKILL DEBT: not used in 44 days (use it or kill it)")
    assert "use it" in action.lower() or "delete" in action.lower()


def test_next_action_for_todo_strips_marker():
    action = extract_next_action("TODO: finish the API keys thing")
    assert "TODO" not in action
    assert "api keys" in action.lower()


def test_next_action_default_forces_decision():
    action = extract_next_action("some vague hanging thread")
    assert action  # never empty
    assert any(word in action.lower() for word in ("kill", "advance", "decide", "next step"))


# --- rendering -------------------------------------------------------------

def test_render_brief_puts_stalest_first_and_includes_ages():
    today = date(2026, 6, 1)
    gaps = [GAP_A, GAP_B, GAP_D]
    state = _state(today, {GAP_A: 2, GAP_B: 30, GAP_D: 9})
    ranked = rank_stale_loops(gaps, state, today, top_n=3)

    out = render_brief(ranked, today)

    assert "2026-06-01" in out
    # stalest (GAP_B, 30d) appears before the freshest (GAP_A, 2d)
    assert out.index("late-institutions") < out.index("API keys")
    assert "30" in out  # age surfaced
    # one next-action marker per loop
    assert out.count("▶") == 3


def test_render_brief_handles_empty():
    out = render_brief([], date(2026, 6, 1))
    assert "no" in out.lower()  # e.g. "No stale open loops"


def test_render_notification_is_short_and_counts():
    today = date(2026, 6, 1)
    ranked = rank_stale_loops([GAP_A, GAP_B], _state(today, {GAP_A: 5, GAP_B: 20}), today)

    title, body = render_notification(ranked)

    assert "2" in title or "2" in body  # count surfaced
    assert len(title) <= 80
    assert len(body) <= 300


# --- Notifier routing (delivery side effects, via fakes) -------------------

def test_notifier_calls_desktop_when_enabled_and_available():
    calls = []
    notifier = Notifier(
        desktop=True,
        ntfy_topic=None,
        which=lambda name: "/usr/bin/notify-send",
        runner=lambda args, **kw: calls.append(args),
        poster=lambda *a, **k: calls.append(("post", a, k)),
    )
    notifier.notify("title", "body")

    assert any(isinstance(c, list) and "notify-send" in c[0] for c in calls)


def test_notifier_skips_desktop_when_binary_missing():
    calls = []
    notifier = Notifier(
        desktop=True,
        ntfy_topic=None,
        which=lambda name: None,  # notify-send not installed
        runner=lambda args, **kw: calls.append(args),
        poster=lambda *a, **k: calls.append("post"),
    )
    notifier.notify("title", "body")

    assert calls == []  # nothing attempted, no crash


def test_notifier_posts_to_ntfy_when_topic_set():
    posted = {}
    notifier = Notifier(
        desktop=False,
        ntfy_topic="my-secret-topic",
        ntfy_url="https://ntfy.sh",
        which=lambda name: None,
        runner=lambda args, **kw: None,
        poster=lambda url, **kw: posted.update({"url": url, "kw": kw}),
    )
    notifier.notify("title", "body")

    assert posted["url"].endswith("/my-secret-topic")


def test_notifier_does_nothing_when_all_channels_off():
    calls = []
    notifier = Notifier(
        desktop=False,
        ntfy_topic=None,
        which=lambda name: "/usr/bin/notify-send",
        runner=lambda args, **kw: calls.append(args),
        poster=lambda *a, **k: calls.append("post"),
    )
    notifier.notify("title", "body")

    assert calls == []


# --- systemd unit generation ----------------------------------------------

def test_render_systemd_units_valid_shape():
    service, timer = render_systemd_units(
        exec_command="/usr/bin/bash /home/u/repo/run-brief.sh",
        hour=7,
        minute=30,
    )

    assert "[Service]" in service
    assert "ExecStart=/usr/bin/bash /home/u/repo/run-brief.sh" in service
    assert "[Timer]" in timer
    assert "OnCalendar=*-*-* 07:30:00" in timer
    assert "[Install]" in timer
