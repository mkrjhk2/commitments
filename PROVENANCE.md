# Source, licence, and what is ours

## Lineage (ideas)

This tool has no upstream code. Its **mechanism** was assembled from two sources, both credited:

1. **Intent-before-effect** — write the intent down *before* performing a side effect, and treat an
   ambiguous effect as "stop, do not replay". Taken from
   [`The-Vibe-Company/companion`](https://github.com/The-Vibe-Company/companion) (MIT), whose
   executor records dispatch intent before contacting the daemon and refuses to blindly re-apply an
   ambiguous effect.
2. **Open-first memory** — the framing that a companion needs a ledger of *what it still owes*
   rather than only a searchable record of *what happened*; and that only the owner's own words may
   cancel a promise. That framing is the owner's (2026-10-19 conversation), not upstream's.

Nothing from that project's code was copied. It is a TypeScript/PostgreSQL/Bun product; this is a
~250-line Python file plus a 70-line plugin.

## Licence

MIT, © 2026 天音 Amane. See `LICENSE`.

Dependencies: **none** beyond the Python standard library. It does not call any model, does not
open a network socket, and does not read anything outside `$HERMES_HOME`.

## What is ours

| part | note |
|---|---|
| `commitments.py` | event-sourced JSONL ledger, `fold`/`open_items`/`overdue`/`render`, CLI with `add`/`open`/`list`/`overdue`/`close`/`drop`/`render` |
| `plugin/` | Hermes `pre_llm_call` hook; injects once per session; silent when nothing is owed or when the ledger is unreadable |
| `tests/` | 15 stdlib tests, including the two refusals (`close` without evidence, `drop` without the owner's words), torn-line tolerance, ordering, render cap, and plugin once-per-session behaviour |

## Deliberate omissions

- No task/project data in the repository: the ledger lives at `$HERMES_HOME/memories/commitments.jsonl`
  on each host and is never shared between hosts.
- No identity, no persona, no conversation content — the record shape holds a promise and the
  owner's quote, nothing else.
- No sync, no server, no accounts: two instances on two machines keep two independent ledgers by
  design.
