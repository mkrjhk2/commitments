#!/usr/bin/env python3
"""commitments — a promise ledger for a persistent agent.

Hermes memory answers "what happened". A promise ledger answers "what do I still owe him".
It is written when the agent says it will do something, read at the start of every session,
and closed only with evidence or with the owner's own words.

Design rules (deliberate, do not relax):
  * append-only JSONL; the latest event for an id wins, so a crash never loses history
  * open-first: rendering shows ONLY open items, capped, newest-due first
  * a promise is never closed by the agent's own judgement — `close` needs evidence,
    `drop` needs the owner's words
  * no network, no LLM, stdlib only

CLI:
    python commitments.py add --quote "今晚做 REA" --promise "插機後由眼鏡 APK 入手" --due 2026-10-19
    python commitments.py open
    python commitments.py close <id> --evidence "reports/verify-20261019-1704/"
    python commitments.py drop <id> --words "唔使做住"
    python commitments.py render --max 6
    python commitments.py overdue
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

STORE_REL = Path("memories") / "commitments.jsonl"
OPEN_STATUSES = ("open",)
VALID_STATUSES = ("open", "done", "dropped")


def hermes_home() -> Path:
    env = os.environ.get("HERMES_HOME")
    if env:
        return Path(env)
    return Path.home() / "AppData" / "Local" / "hermes" if os.name == "nt" else Path.home() / ".hermes"


def store_path(home: Path | None = None) -> Path:
    return (home or hermes_home()) / STORE_REL


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _new_id(promise: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%y%m%d")
    digest = hashlib.sha1(f"{promise}{_now()}".encode("utf-8")).hexdigest()[:4]
    return f"{stamp}-{digest}"


def append(event: dict, path: Path | None = None) -> None:
    target = path or store_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")


def read_events(path: Path | None = None) -> list[dict]:
    target = path or store_path()
    if not target.is_file():
        return []
    out = []
    for line in target.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue  # a torn line must never hide the rest of the ledger
        if isinstance(rec, dict) and rec.get("id"):
            out.append(rec)
    return out


def fold(events: Iterable[dict]) -> dict[str, dict]:
    """Latest event per id wins; creation fields survive later status events."""
    items: dict[str, dict] = {}
    for ev in events:
        rid = ev["id"]
        if rid not in items:
            items[rid] = dict(ev)
            items[rid].setdefault("status", "open")
        else:
            items[rid].update({k: v for k, v in ev.items() if v is not None})
    return items


def open_items(path: Path | None = None) -> list[dict]:
    items = [i for i in fold(read_events(path)).values() if i.get("status") in OPEN_STATUSES]
    items.sort(key=lambda i: (i.get("due") or "9999-12-31", i.get("said_at") or ""))
    return items


def add(quote: str, promise: str, due: str | None = None, owner: str = "user", path: Path | None = None) -> dict:
    if not promise.strip():
        raise ValueError("promise cannot be empty")
    rec = {
        "id": _new_id(promise),
        "said_at": _now(),
        "quoted": quote.strip(),
        "promise": promise.strip(),
        "due": due or None,
        "owner": owner,
        "status": "open",
    }
    append(rec, path)
    return rec


def transition(item_id: str, status: str, *, evidence: str | None = None, words: str | None = None, path: Path | None = None) -> dict:
    if status not in VALID_STATUSES:
        raise ValueError(f"bad status {status!r}")
    if status == "done" and not (evidence or "").strip():
        raise ValueError("closing a promise needs evidence")
    if status == "dropped" and not (words or "").strip():
        raise ValueError("dropping a promise needs the owner's own words")
    items = fold(read_events(path))
    if item_id not in items:
        raise KeyError(f"no promise {item_id!r}")
    ev = {"id": item_id, "status": status, "closed_at": _now()}
    if evidence:
        ev["evidence"] = evidence.strip()
    if words:
        ev["dropped_words"] = words.strip()
    append(ev, path)
    return {**items[item_id], **ev}


def overdue(items: Iterable[dict], today: date | None = None) -> list[dict]:
    now = today or date.today()
    out = []
    for i in items:
        due = i.get("due")
        if not due:
            continue
        try:
            if date.fromisoformat(due) < now:
                out.append(i)
        except Exception:
            continue
    return out


def render(items: Iterable[dict], limit: int = 6) -> str:
    """Compact block for a session-opening injection. Empty string when nothing is owed."""
    rows = list(items)
    if not rows:
        return ""
    lines = [f"【承諾帳】你仲欠主人 {len(rows)} 件事（只列未結）："]
    for i in rows[:limit]:
        due = i.get("due")
        mark = " ⚠過期" if due and _is_past(due) else ""
        quote = (i.get("quoted") or "").strip()
        tail = f" ←「{quote}」" if quote else ""
        lines.append(f"- [{i['id']}] {i['promise']}{tail}{('（due ' + due + '）') if due else ''}{mark}")
    if len(rows) > limit:
        lines.append(f"（仲有 {len(rows) - limit} 件未列，用 commitments.py open 睇全部）")
    lines.append("要清就 `close <id> --evidence …`（要有證據）或 `drop <id> --words 「主人原話」`。唔准自己當做完。")
    return "\n".join(lines)


def _is_past(due: str, today: date | None = None) -> bool:
    try:
        return date.fromisoformat(due) < (today or date.today())
    except Exception:
        return False


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Promise ledger for a persistent agent.")
    ap.add_argument("--home", help="HERMES_HOME override")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_add = sub.add_parser("add")
    p_add.add_argument("--quote", default="")
    p_add.add_argument("--promise", required=True)
    p_add.add_argument("--due", default=None)
    p_add.add_argument("--owner", default="user", choices=("user", "self"))

    for name in ("open", "list", "overdue"):
        p = sub.add_parser(name)
        if name == "list":
            p.add_argument("--all", action="store_true")

    p_close = sub.add_parser("close")
    p_close.add_argument("id")
    p_close.add_argument("--evidence", required=True)

    p_drop = sub.add_parser("drop")
    p_drop.add_argument("id")
    p_drop.add_argument("--words", required=True)

    p_render = sub.add_parser("render")
    p_render.add_argument("--max", type=int, default=6)

    args = ap.parse_args(argv)
    path = store_path(Path(args.home).expanduser() if args.home else None)

    try:
        if args.cmd == "add":
            rec = add(args.quote, args.promise, args.due, args.owner, path)
            print(f"logged {rec['id']}: {rec['promise']}")
        elif args.cmd == "open":
            items = open_items(path)
            print(render(items, limit=999) or "nothing owed")
        elif args.cmd == "list":
            items = fold(read_events(path))
            rows = list(items.values()) if args.all else [i for i in items.values() if i.get("status") == "open"]
            for i in sorted(rows, key=lambda r: r.get("said_at") or ""):
                print(f"[{i.get('status','?'):7s}] [{i['id']}] {i.get('promise','')}"
                      f"{(' due ' + i['due']) if i.get('due') else ''}"
                      f"{' ev=' + i['evidence'] if i.get('evidence') else ''}")
            if not rows:
                print("(empty)")
        elif args.cmd == "overdue":
            rows = overdue(open_items(path))
            print("\n".join(f"[{i['id']}] {i['promise']} (due {i['due']})" for i in rows) or "nothing overdue")
        elif args.cmd == "close":
            rec = transition(args.id, "done", evidence=args.evidence, path=path)
            print(f"closed {rec['id']}")
        elif args.cmd == "drop":
            rec = transition(args.id, "dropped", words=args.words, path=path)
            print(f"dropped {rec['id']}")
        elif args.cmd == "render":
            print(render(open_items(path), limit=args.max))
    except (ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
