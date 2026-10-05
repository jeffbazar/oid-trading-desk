#!/usr/bin/env python3
"""Bootstrap the Customer/Supplier Event Bot paper store. Research only."""

import json
import sqlite3
from pathlib import Path

DB_PATH = Path("/workspace/options-intelligence-desk/supply-chain/supply-chain.db")
BOOTSTRAP_AT = "2026-10-04T14:48:00-07:00"
INVENTORY_DATE = "2026-10-04"
# effective_from is the watchlist inventory date, not a verified listing date.
EFFECTIVE_FROM = INVENTORY_DATE

SCHEMA = """
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE entities (
    entity_id TEXT PRIMARY KEY,
    legal_name TEXT NOT NULL,
    country TEXT,
    cik TEXT,
    lei TEXT,
    listing_status TEXT NOT NULL CHECK (listing_status IN ('public', 'private', 'unknown')),
    notes TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE entity_aliases (
    alias_id TEXT PRIMARY KEY,
    entity_id TEXT NOT NULL REFERENCES entities(entity_id),
    alias TEXT NOT NULL,
    alias_type TEXT NOT NULL CHECK (alias_type IN ('legal', 'brand', 'ticker_label', 'other')),
    UNIQUE (entity_id, alias, alias_type)
);

CREATE TABLE instruments (
    instrument_id TEXT PRIMARY KEY,
    entity_id TEXT NOT NULL REFERENCES entities(entity_id),
    ticker TEXT NOT NULL,
    exchange TEXT NOT NULL,
    currency TEXT,
    share_class TEXT NOT NULL,
    adr_ratio TEXT,
    effective_from TEXT NOT NULL,
    effective_to TEXT,
    UNIQUE (ticker, exchange, share_class)
);

CREATE TABLE sources (
    source_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    url TEXT,
    access_method TEXT,
    coverage TEXT,
    cadence TEXT,
    last_success_at TEXT,
    status TEXT NOT NULL
);

CREATE TABLE claims (
    claim_id TEXT PRIMARY KEY,
    entity_id TEXT REFERENCES entities(entity_id),
    statement TEXT NOT NULL,
    evidence_status TEXT NOT NULL CHECK (evidence_status IN (
        'PRIMARY_DOCUMENT', 'PRIMARY_STATEMENT', 'REPORTED',
        'DISCOVERY_ONLY', 'INFERRED', 'DISPUTED', 'RETRACTED'
    )),
    source_id TEXT REFERENCES sources(source_id),
    locator TEXT,
    excerpt TEXT,
    created_at TEXT NOT NULL,
    CHECK (
        source_id IS NOT NULL
        OR (excerpt IS NOT NULL AND length(trim(excerpt)) > 0)
    )
);

CREATE TABLE relationships (
    relationship_id TEXT PRIMARY KEY,
    from_entity_id TEXT NOT NULL REFERENCES entities(entity_id),
    to_entity_id TEXT NOT NULL REFERENCES entities(entity_id),
    edge_type TEXT NOT NULL CHECK (edge_type IN (
        'SUPPLIES', 'BUYS_FROM', 'COMPETES_WITH', 'PARTNERS_WITH',
        'INVESTS_IN', 'LENDS_TO', 'LEASES_FROM', 'HOSTS_COMPUTE_FOR',
        'BUILDS_PROJECT_FOR', 'PROVIDES_POWER_TO'
    )),
    product_scope TEXT,
    disclosure_category TEXT NOT NULL,
    relationship_certainty TEXT NOT NULL CHECK (relationship_certainty IN (
        'confirmed', 'reported', 'inferred', 'unknown'
    )),
    valid_from TEXT,
    valid_to TEXT,
    last_verified_at TEXT,
    supporting_claim_id TEXT REFERENCES claims(claim_id)
);

CREATE TABLE economic_events (
    event_id TEXT PRIMARY KEY,
    novelty TEXT NOT NULL,
    summary TEXT NOT NULL,
    public_at TEXT,
    received_at TEXT NOT NULL,
    evidence_status TEXT NOT NULL
);

CREATE TABLE impact_assessments (
    assessment_id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL REFERENCES economic_events(event_id),
    entity_id TEXT NOT NULL REFERENCES entities(entity_id),
    direction TEXT NOT NULL CHECK (direction IN ('POSITIVE', 'NEGATIVE', 'MIXED', 'UNCERTAIN')),
    direct_or_inferred TEXT NOT NULL,
    exposure_path TEXT NOT NULL,
    materiality_reason TEXT NOT NULL,
    assessment_version TEXT NOT NULL
);

CREATE TABLE alert_outbox (
    alert_id TEXT PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE,
    event_id TEXT REFERENCES economic_events(event_id),
    recipient TEXT NOT NULL,
    alert_kind TEXT NOT NULL,
    priority TEXT NOT NULL,
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    status TEXT NOT NULL CHECK (status IN ('pending', 'suppressed', 'delivered_paper')),
    created_at TEXT NOT NULL
);

CREATE TABLE source_checkpoints (
    source_id TEXT NOT NULL REFERENCES sources(source_id),
    checkpoint_key TEXT NOT NULL,
    cursor_value TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (source_id, checkpoint_key)
);

CREATE INDEX idx_instruments_entity ON instruments(entity_id);
CREATE INDEX idx_aliases_entity ON entity_aliases(entity_id);
CREATE INDEX idx_claims_entity ON claims(entity_id);
CREATE INDEX idx_claims_source ON claims(source_id);
CREATE INDEX idx_rel_from ON relationships(from_entity_id);
CREATE INDEX idx_rel_to ON relationships(to_entity_id);
CREATE INDEX idx_impact_event ON impact_assessments(event_id);
CREATE INDEX idx_alert_event ON alert_outbox(event_id);
"""

# ticker, legal_name, country, listing_status, notes, exchange, currency, share_class
# country/CIK/LEI left null unless common-knowledge confident. No CIKs or LEIs stored.
# exchange UNVERIFIED = venue not confirmed this pass (keeps the unique key non-null).
ETF_NOTE = "Fund/index product, not an operating company. Issuer not modeled; entity is the ticker product only."
TICKER_ONLY = "ticker-only identity; legal name not verified this pass"

ROWS = [
    # ETFs / index products
    ("SPY", "SPY", "US", "public", ETF_NOTE, "NYSE Arca", "USD", "common"),
    ("QQQ", "QQQ", "US", "public", ETF_NOTE, "NASDAQ", "USD", "common"),
    ("SMH", "SMH", "US", "public", ETF_NOTE, "NASDAQ", "USD", "common"),
    ("EWY", "EWY", "US", "public", ETF_NOTE, "NYSE Arca", "USD", "common"),
    # Operating names. Legal names follow the requested forms where given.
    ("NVDA", "NVIDIA Corporation", "US", "public", None, "NASDAQ", "USD", "common"),
    ("GOOG", "Alphabet Inc.", "US", "public", None, "NASDAQ", "USD", "Class C"),
    ("AMZN", "Amazon.com Inc.", "US", "public", None, "NASDAQ", "USD", "common"),
    ("META", "Meta Platforms", "US", "public", None, "NASDAQ", "USD", "common"),
    ("TSM", "Taiwan Semiconductor Manufacturing Co. ADR", "TW", "public",
     "Single entity for the US ADR line. Taiwan ordinary shares are not a second entity.",
     "NYSE", "USD", "ADR"),
    ("AVGO", "Broadcom", "US", "public", None, "NASDAQ", "USD", "common"),
    ("AMD", "Advanced Micro Devices", "US", "public", None, "NASDAQ", "USD", "common"),
    ("MU", "Micron", "US", "public", None, "NASDAQ", "USD", "common"),
    ("ASML", "ASML Holding", "NL", "public", None, "NASDAQ", "USD", "ADR"),
    ("ORCL", "Oracle", "US", "public", None, "NYSE", "USD", "common"),
    ("INTC", "Intel", "US", "public", None, "NASDAQ", "USD", "common"),
    ("TSLA", "Tesla", "US", "public", None, "NASDAQ", "USD", "common"),
    ("NFLX", "Netflix", "US", "public", None, "NASDAQ", "USD", "common"),
    ("INTU", "Intuit", "US", "public", None, "NASDAQ", "USD", "common"),
    ("ARM", "Arm Holdings plc", "GB", "public", None, "NASDAQ", "USD", "common"),
    ("ADI", "Analog Devices", "US", "public", None, "NASDAQ", "USD", "common"),
    ("STX", "Seagate Technology", None, "public",
     "Legal name confident. Country left null (incorporation domicile not re-verified).",
     "NASDAQ", "USD", "common"),
    ("GLW", "Corning Incorporated", "US", "public", None, "NYSE", "USD", "common"),
    ("MRVL", "Marvell Technology", "US", "public", None, "NASDAQ", "USD", "common"),
    ("LRCX", "Lam Research", "US", "public", None, "NASDAQ", "USD", "common"),
    ("KLAC", "KLA Corporation", "US", "public", None, "NASDAQ", "USD", "common"),
    ("WDC", "Western Digital", "US", "public", None, "NASDAQ", "USD", "common"),
    ("KEYS", "Keysight Technologies", "US", "public", None, "NYSE", "USD", "common"),
    ("BE", "Bloom Energy", "US", "public", None, "NYSE", "USD", "common"),
    ("CRDO", "Credo Technology Group Holding Ltd", None, "public",
     "Legal name confident. Country left null (holding-company domicile not re-verified).",
     "NASDAQ", "USD", "common"),
    ("NBIS", "Nebius Group N.V.", "NL", "public", None, "NASDAQ", "USD", "common"),
    ("SNDK", "SanDisk", "US", "public",
     "Legal name mapped from the ticker and desk universe label. Exchange not re-verified.",
     "UNVERIFIED", "USD", "common"),
    ("LITE", "Lumentum Holdings", "US", "public", None, "NASDAQ", "USD", "common"),
    ("COHR", "Coherent Corp.", "US", "public", None, "NYSE", "USD", "common"),
    ("IREN", "IREN Limited", "AU", "public", "Formerly Iris Energy.", "NASDAQ", "USD", "common"),
    ("SPCX", "Space Exploration Technologies Corp.", "US", "public",
     "Ticker SPCX mapped from desk universe label (SpaceX). Exchange not re-verified. Not a supplier edge.",
     "UNVERIFIED", "USD", "common"),
    ("SKHY", "SKHY", None, "public", TICKER_ONLY, "UNVERIFIED", None, "common"),
    ("MH", "MH", None, "public", TICKER_ONLY, "UNVERIFIED", None, "common"),
]

ETF_TICKERS = {"SPY", "QQQ", "SMH", "EWY"}

SOURCES = [
    (
        "src-robinhood-watchlists",
        "robinhood",
        None,
        "mcp user-robinhood-trading watchlist inventory",
        "Trading-universe tickers taken from the verified Robinhood watchlist inventory dated 2026-10-04. Identity seed only.",
        "on demand",
        INVENTORY_DATE,
        "connected",
    ),
    (
        "src-robinhood-sec-filing-index",
        "robinhood",
        None,
        "mcp user-robinhood-trading get_sec_filing_index; Robinhood tool, not a direct EDGAR client",
        "Connected. No filing backfill was run and none is claimed.",
        "on demand",
        None,
        "connected",
    ),
    (
        "src-flashalpha",
        "flashalpha",
        None,
        "mcp user-flashalpha-api and user-flashalpha-keyed; not called this pass",
        "Account connected. No calls made for this bootstrap.",
        "not polled",
        None,
        "connected_not_called",
    ),
    (
        "src-unusual-whales",
        "unusual-whales",
        None,
        "mcp user-unusual-whales; not called this pass",
        "Account connected. No calls made for this bootstrap.",
        "not polled",
        None,
        "connected_not_called",
    ),
    (
        "src-x",
        "x",
        None,
        "mcp user-X; not called this pass",
        "Account connected. No posts read or sent for this bootstrap.",
        "not polled",
        None,
        "connected_not_called",
    ),
    (
        "src-benzinga",
        "benzinga",
        None,
        None,
        "Gap: not entitled. No subscription is represented.",
        None,
        None,
        "not_entitled",
    ),
    (
        "src-factset",
        "factset",
        None,
        None,
        "Gap: not entitled. No subscription is represented.",
        None,
        None,
        "not_entitled",
    ),
    (
        "src-eia",
        "eia",
        None,
        None,
        "Gap: not entitled. No subscription is represented.",
        None,
        None,
        "not_entitled",
    ),
]

HYP_EVENT_ID = "evt-hypothetical-capex-example-v1"
HYP_SUMMARY = (
    "HYPOTHETICAL paper example only, not a real company and not a market event: "
    "unnamed buyer capex guidance revised from $10B to $12B "
    "(+20% vs own prior guidance). consensus_surprise UNKNOWN. "
    "Supplier impact inferred. Allocation unknown. Not an order and not a trade."
)
HYP_PAYLOAD = {
    "hypothetical": True,
    "capex_prior": "$10B",
    "capex_revised": "$12B",
    "buyer_guidance_vs_own_prior": "+20%",
    "consensus_surprise": "UNKNOWN",
    "supplier_impact": "inferred",
    "allocation": "unknown",
    "not_an_order": True,
    "not_a_trade": True,
    "tied_to_real_company": False,
}


def main() -> None:
    if DB_PATH.exists():
        DB_PATH.unlink()
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(SCHEMA)
        conn.execute("PRAGMA foreign_keys = ON")

        for ticker, legal, country, listing, notes, exchange, currency, share_class in ROWS:
            entity_id = f"ent-{ticker.lower()}"
            conn.execute(
                """INSERT INTO entities
                   (entity_id, legal_name, country, cik, lei, listing_status, notes, created_at)
                   VALUES (?, ?, ?, NULL, NULL, ?, ?, ?)""",
                (entity_id, legal, country, listing, notes, BOOTSTRAP_AT),
            )
            conn.execute(
                """INSERT INTO entity_aliases (alias_id, entity_id, alias, alias_type)
                   VALUES (?, ?, ?, 'ticker_label')""",
                (f"alias-{ticker.lower()}-ticker", entity_id, ticker),
            )
            if ticker == "SPCX":
                conn.execute(
                    """INSERT INTO entity_aliases (alias_id, entity_id, alias, alias_type)
                       VALUES (?, ?, ?, 'brand')""",
                    ("alias-spcx-brand", entity_id, "SpaceX"),
                )
            conn.execute(
                """INSERT INTO instruments
                   (instrument_id, entity_id, ticker, exchange, currency, share_class,
                    adr_ratio, effective_from, effective_to)
                   VALUES (?, ?, ?, ?, ?, ?, NULL, ?, NULL)""",
                (
                    f"inst-{ticker.lower()}",
                    entity_id,
                    ticker,
                    exchange,
                    currency,
                    share_class,
                    EFFECTIVE_FROM,
                ),
            )

        conn.executemany(
            """INSERT INTO sources
               (source_id, provider, url, access_method, coverage, cadence, last_success_at, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            SOURCES,
        )

        conn.execute(
            """INSERT INTO economic_events
               (event_id, novelty, summary, public_at, received_at, evidence_status)
               VALUES (?, ?, ?, NULL, ?, ?)""",
            (
                HYP_EVENT_ID,
                "hypothetical-format-test",
                HYP_SUMMARY,
                BOOTSTRAP_AT,
                "HYPOTHETICAL",
            ),
        )
        conn.execute(
            """INSERT INTO alert_outbox
               (alert_id, idempotency_key, event_id, recipient, alert_kind, priority,
                payload_json, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "alert-hypothetical-capex-example-v1",
                "hypothetical-capex-example-v1",
                HYP_EVENT_ID,
                "desk-paper",
                "capex-guidance-example",
                "none",
                json.dumps(HYP_PAYLOAD),
                "suppressed",
                BOOTSTRAP_AT,
            ),
        )
        conn.commit()

        fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        fk_check = conn.execute("PRAGMA foreign_key_check").fetchall()
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        journal = conn.execute("PRAGMA journal_mode").fetchone()[0]

        print(f"db_path={DB_PATH}")
        print(f"journal_mode={journal}")
        print(f"foreign_keys={fk}")
        print(f"integrity_check={integrity}")
        print(f"foreign_key_check_rows={len(fk_check)}")

        print("TABLE_COUNTS")
        tables = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        for name in tables:
            n = conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
            print(f"  {name}={n}")

        company = conn.execute(
            """SELECT COUNT(*) AS instruments, COUNT(DISTINCT entity_id) AS entities
               FROM instruments
               WHERE ticker NOT IN ('SPY', 'QQQ', 'SMH', 'EWY')"""
        ).fetchone()
        etf = conn.execute(
            """SELECT COUNT(*) AS instruments, COUNT(DISTINCT entity_id) AS entities
               FROM instruments
               WHERE ticker IN ('SPY', 'QQQ', 'SMH', 'EWY')"""
        ).fetchone()
        print(
            f"company_instruments={company['instruments']} company_distinct_entities={company['entities']}"
        )
        print(f"etf_instruments={etf['instruments']} etf_distinct_entities={etf['entities']}")
        print(f"relationships={conn.execute('SELECT COUNT(*) FROM relationships').fetchone()[0]}")
        goog = conn.execute("SELECT COUNT(*) FROM instruments WHERE ticker='GOOG'").fetchone()[0]
        googl = conn.execute("SELECT COUNT(*) FROM instruments WHERE ticker='GOOGL'").fetchone()[0]
        alphabet = conn.execute(
            "SELECT COUNT(*) FROM entities WHERE legal_name LIKE 'Alphabet%'"
        ).fetchone()[0]
        print(f"goog_instruments={goog} alphabet_entities={alphabet} googl_instruments={googl}")
        print(
            "claims="
            + str(conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0])
            + " impact_assessments="
            + str(conn.execute("SELECT COUNT(*) FROM impact_assessments").fetchone()[0])
        )
        banned = ("Microsoft", "Samsung", "Arista", "Eaton", "Schneider", "CoreWeave", "OpenAI", "Anthropic")
        for name in banned:
            n = conn.execute(
                "SELECT COUNT(*) FROM entities WHERE legal_name LIKE ?", (f"%{name}%",)
            ).fetchone()[0]
            if n:
                print(f"UNEXPECTED_ENTITY {name}={n}")
        print("SAMPLE_ENTITIES")
        for row in conn.execute(
            """SELECT entity_id, legal_name, country, listing_status
               FROM entities ORDER BY entity_id LIMIT 5"""
        ):
            print(f"  {row['entity_id']}|{row['legal_name']}|{row['country']}|{row['listing_status']}")
        alert = conn.execute(
            "SELECT idempotency_key, status, recipient, payload_json FROM alert_outbox"
        ).fetchone()
        print(f"alert_key={alert['idempotency_key']} status={alert['status']} recipient={alert['recipient']}")
        print(f"alert_payload={alert['payload_json']}")
        print(f"ticker_only={conn.execute('SELECT COUNT(*) FROM entities WHERE notes=?', (TICKER_ONLY,)).fetchone()[0]}")
        print(f"entity_total={conn.execute('SELECT COUNT(*) FROM entities').fetchone()[0]}")
        print(f"instrument_total={conn.execute('SELECT COUNT(*) FROM instruments').fetchone()[0]}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
