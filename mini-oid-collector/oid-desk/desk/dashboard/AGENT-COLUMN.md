# Agent column (required)

Jeffrey asked that **both desks** keep an **Agent** column on the live blotter.

- Paper desks: exact names **`Rose`** or **`Hal`** (not OID/OT2/full titles).
- External ZH flow watches: **`Leopold`** (third label; does not replace Rose|Hal on paper seats).
- Set `agent` (and preferably `desk`: OID|OT2|ZH) on every ticket / watch row.
- `dashboard/rebuild.py` uses `agent_label(t)` — do not remove the Agent column when redesigning the ticker UI.
- Leopold rows live in `leopoldWatches` (or status `leopold_watch`) and **do not** consume `maxOpenTickets` seats.
