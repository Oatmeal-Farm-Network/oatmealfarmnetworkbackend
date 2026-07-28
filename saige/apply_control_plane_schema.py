# --- apply_control_plane_schema.py --- (Apply data/sql/schema/saige_supervisor_schema.sql)
"""Run: py -3.13 apply_control_plane_schema.py"""
from __future__ import annotations

import re
import sys

from config import DB_CONFIG
from core.paths import sql_schema_path
from db_control import sql_configured, table_exists


def main() -> int:
    if not sql_configured():
        print("SQL not configured (DB_HOST/USER/DATABASE). Abort.")
        return 1

    path = str(sql_schema_path("saige_supervisor_schema.sql"))
    raw = open(path, encoding="utf-8").read()
    # Split on GO batches
    batches = [b.strip() for b in re.split(r"^\s*GO\s*$", raw, flags=re.I | re.M) if b.strip()]

    import pymssql

    conn = pymssql.connect(
        server=DB_CONFIG["host"],
        port=int(DB_CONFIG.get("port") or 1433),
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"],
        database=DB_CONFIG["database"],
        login_timeout=15,
        timeout=60,
    )
    try:
        cur = conn.cursor()
        for i, batch in enumerate(batches, 1):
            print(f"[schema] batch {i}/{len(batches)} ...")
            cur.execute(batch)
            conn.commit()
        print("[schema] done")
    finally:
        conn.close()

    for t in (
        "SaigeProposals",
        "SaigeProposalEvents",
        "SaigePlans",
        "SaigePlanItems",
        "SaigeMonitoringRuns",
        "SaigeMonitoringFindings",
        "SaigeSessions",
        "SaigeUserPreferences",
    ):
        print(f"  {t}: {'OK' if table_exists(t) else 'MISSING'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
