"""hermes-commitments plugin — inject the promise ledger at the start of a session.

Hook: ``pre_llm_call`` returns text that Hermes appends to the user message as ephemeral
context. We inject ONCE per session (first turn) so the agent knows what it still owes,
without paying for it on every turn.

Nothing else is touched: no memory files, no SOUL, no network, no model calls. If the
ledger is missing or unreadable the hook stays silent — a broken ledger must never break
a conversation.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_INJECTED: set[str] = set()


def _enabled() -> bool:
    flag = (os.environ.get("HERMES_COMMITMENTS_ENABLED") or "1").strip().lower()
    return flag not in {"0", "false", "no", "off"}


def _max_items() -> int:
    raw = (os.environ.get("HERMES_COMMITMENTS_MAX") or "6").strip()
    try:
        return max(1, int(raw))
    except Exception:
        return 6


def _load_ledger_module():
    """Import commitments.py from HERMES_HOME/scripts, then from a sibling checkout."""
    home = Path(os.environ.get("HERMES_HOME") or (Path.home() / ".hermes"))
    for candidate in (home / "scripts", Path(__file__).resolve().parent.parent):
        if (candidate / "commitments.py").is_file():
            sys.path.insert(0, str(candidate))
            break
    import commitments  # type: ignore

    return commitments


def on_pre_llm_call(session_id=None, turn_id=None, **kwargs):
    try:
        if not _enabled():
            return None
        sid = str(session_id or "?")
        if sid in _INJECTED:
            return None
        mod = _load_ledger_module()
        items = mod.open_items()
        if not items:
            _INJECTED.add(sid)
            return None
        block = mod.render(items, limit=_max_items())
        _INJECTED.add(sid)
        return block or None
    except Exception:
        return None


def register(ctx):
    ctx.register_hook("pre_llm_call", on_pre_llm_call)
