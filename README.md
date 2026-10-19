# hermes-commitments — 承諾帳（promise ledger）for Hermes

Hermes memory answers **「發生過咩」**. This ledger answers **「我仲欠你咩」**.

An agent that says *「我今晚幫你查」* and then loses it in a context compression has not lied —
it has just lost the thread. This is the missing piece: a small, append-only record of promises,
injected at session start so the agent opens every conversation knowing what it still owes.

Design: **open-first, not recall-first.** Memory is searched when something is asked about the
ledger; the ledger is read at the beginning of every session, unasked — a handful of lines, never
a second prompt burden.

## What it does

- `add` a promise the moment it is made, with the owner's own words as the quote
- render only **open** items at session start (capped, soonest-due first, overdue flagged)
- close with **evidence** (`close <id> --evidence …`), never with the agent's own judgement
- drop only with the **owner's own words** (`drop <id> --words「…」`)
- append-only JSONL: a crash or a torn line never hides the rest of the ledger

No network. No LLM calls. Standard library only.

## Install (any Hermes host)

```bash
git clone <this repo> ~/projects/hermes-commitments
cp commitments.py "$HERMES_HOME/scripts/commitments.py"
mkdir -p "$HERMES_HOME/plugins/hermes-commitments"
cp plugin/__init__.py plugin/plugin.yaml "$HERMES_HOME/plugins/hermes-commitments/"
hermes plugins enable hermes-commitments      # takes effect on next session
```

Ledger lives at `$HERMES_HOME/memories/commitments.jsonl` — **per host, never shared**.
Two agents on two machines keep two ledgers; that is intended (they are two individuals, not one
account).

## Use

```bash
python "$HERMES_HOME/scripts/commitments.py" add --quote "今晚做 REA" --promise "插機後由眼鏡 APK 入手" --due 2026-10-19
python "$HERMES_HOME/scripts/commitments.py" open          # what is still owed
python "$HERMES_HOME/scripts/commitments.py" overdue
python "$HERMES_HOME/scripts/commitments.py" close 261019-1c72 --evidence "reports/verify-20261019-1704/"
python "$HERMES_HOME/scripts/commitments.py" drop 261019-03fc --words "唔使做住"
```

Plugin injection happens once per session (first turn) and stays silent when nothing is owed.

Env switches: `HERMES_COMMITMENTS_ENABLED=0` (off), `HERMES_COMMITMENTS_MAX=6` (lines shown).

## Record shape

One JSON object per line; the latest event per `id` wins:

```json
{"id":"261019-1c72","said_at":"2026-10-19T09:12:00+00:00","quoted":"we will do tonight",
 "promise":"插機後做 REA：由 Rokid 眼鏡 APK／firmware 入手","due":"2026-10-19",
 "owner":"user","status":"open"}
{"id":"261019-1c72","status":"done","closed_at":"...","evidence":"reports/verify-..."}
```

## Rules the code enforces

1. `close` without `--evidence` → refused. A promise is not done because the agent says so.
2. `drop` without `--words` → refused. Only the owner can cancel.
3. Rendering never hides an item silently: it either lists it or reports how many are omitted.
4. A malformed line is skipped, never fatal.

## Tests

```bash
python tests/test_commitments.py     # 15 tests, stdlib unittest
```

## What this is not

It is not a task tracker, a todo app, or a second memory. It records **commitments to a person**,
nothing about work in progress — that belongs in the project's own notes. Keeping the two separate
is what keeps this file short enough to read every session.

MIT. Written by 天音 Amane.
