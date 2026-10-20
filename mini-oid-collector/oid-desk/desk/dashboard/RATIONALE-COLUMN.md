# Rationale column (required)

Jeffrey asked that **both desks** keep a **Rationale** column on the live blotter explaining why the trade was taken.

## Field
- Ticket key: **`rationale`** (string, 1–2 sentences)
- Optional alias: `thesis` (rebuild falls back to it)
- Also falls back to a `Thesis:` line inside `softCatalystDetail[]` if `rationale` is empty — still set `rationale` explicitly on elevate

## Who fills it
- **Rose** and **Hal** on every paper elevate / paper seed
- Do not leave blank; do not rely on journal prose alone

## Dashboard
- `rebuild.py` renders **Rationale** on Open seats and Recently closed tables
- Do not drop this column when redesigning the ticker UI

## OID elevate contract (2026-09-18)
On every new Rose `PAPER_CANDIDATE`, set ticket field `rationale` (1–2 sentences: why this exact contract now). Do not rely only on softCatalystDetail Thesis: line — rebuild falls back, but explicit `rationale` is required for both desks.
