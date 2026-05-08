from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _count(db, sql, params=None):
    try:
        return db.execute(text(sql), params or {}).scalar() or 0
    except Exception:
        return 0


@router.get("/summary")
def dashboard_summary(business_id: int = Query(...), db: Session = Depends(get_db)):
    b = {"b": business_id}
    return {
        "fields":          _count(db, "SELECT COUNT(*) FROM Field WHERE BusinessID=:b", b),
        "animals":         _count(db, "SELECT COUNT(*) FROM Animals WHERE BusinessID=:b", b),
        "pending_orders":  _count(db, "SELECT COUNT(*) FROM MarketplaceOrderItems WHERE SellerBusinessID=:b AND SellerStatus IN ('pending','confirmed','processing')", b),
        "upcoming_events": _count(db, "SELECT COUNT(*) FROM Event WHERE BusinessID=:b AND EventStartYear >= YEAR(GETDATE())", b),
        "blog_posts":      _count(db, "SELECT COUNT(*) FROM blog WHERE BusinessID=:b AND IsPublished=1", b),
        "products":        _count(db, "SELECT COUNT(*) FROM SFProducts WHERE BusinessID=:b AND Publishproduct=1", b),
        "services":        _count(db, "SELECT COUNT(*) FROM Services WHERE BusinessID=:b", b),
        "produce":         _count(db, "SELECT COUNT(*) FROM Produce WHERE BusinessID=:b AND IsActive=1", b),
    }
