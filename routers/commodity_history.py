# routers/commodity_history.py
# Time-series storage for live commodity prices submitted via /api/market-alerts/check.
# Exposes a trend endpoint for Market Intelligence sparklines and Saige analysis tools.

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db, engine
from typing import Optional
from datetime import datetime, timedelta
from collections import defaultdict

router = APIRouter(prefix="/api/commodity-prices", tags=["commodity_history"])

with engine.begin() as _conn:
    _conn.execute(text("""
        IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME='CommodityPriceHistory')
        BEGIN
            CREATE TABLE CommodityPriceHistory (
                HistoryID   INT IDENTITY(1,1) PRIMARY KEY,
                Commodity   VARCHAR(80)   NOT NULL,
                PriceUSD    DECIMAL(12,4) NOT NULL,
                FetchedAt   DATETIME      NOT NULL DEFAULT GETDATE()
            )
            CREATE INDEX IX_CommodityHistory_Commodity
                ON CommodityPriceHistory (Commodity, FetchedAt DESC)
        END
    """))


@router.get("/history")
def get_price_history(
    commodity: Optional[str] = None,
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
):
    """Returns price data points per commodity over the last N days with trend stats.
    No auth required — prices are aggregate market data, not user-specific."""
    since = datetime.utcnow() - timedelta(days=days)

    if commodity:
        rows = db.execute(text("""
            SELECT Commodity, PriceUSD, FetchedAt
            FROM CommodityPriceHistory
            WHERE Commodity = :c AND FetchedAt >= :since
            ORDER BY FetchedAt ASC
        """), {"c": commodity, "since": since}).mappings().all()
    else:
        rows = db.execute(text("""
            SELECT Commodity, PriceUSD, FetchedAt
            FROM CommodityPriceHistory
            WHERE FetchedAt >= :since
            ORDER BY Commodity, FetchedAt ASC
        """), {"since": since}).mappings().all()

    by_commodity: dict = defaultdict(list)
    for r in rows:
        ts = r["FetchedAt"]
        by_commodity[r["Commodity"]].append({
            "price": float(r["PriceUSD"]),
            "at": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
        })

    result = {}
    for comm, pts in by_commodity.items():
        prices = [p["price"] for p in pts]
        first, last = prices[0], prices[-1]
        pct = round((last - first) / first * 100, 2) if first else None
        result[comm] = {
            "points": pts,
            "latest": last,
            "avg_7d":  round(sum(prices[-7:]) / len(prices[-7:]), 4) if prices else None,
            "avg_30d": round(sum(prices) / len(prices), 4) if prices else None,
            "pct_change": pct,
            "trend": "rising" if pct and pct > 2 else ("falling" if pct and pct < -2 else "stable"),
        }
    return result
