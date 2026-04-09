from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db

router = APIRouter(prefix="/api/company", tags=["company"])


@router.get("/features")
def get_features(db: Session = Depends(get_db)):
    """Return all rows from CompanySiteManagement ordered by SortOrder."""
    rows = db.execute(
        text(
            "SELECT FeatureKey, FeatureName, IsEnabled, MonthlyPrice, YearlyPrice, SortOrder "
            "FROM CompanySiteManagement ORDER BY SortOrder"
        )
    ).fetchall()
    return [
        {
            "feature_key":   r[0],
            "feature_name":  r[1],
            "is_enabled":    bool(r[2]),
            "monthly_price": float(r[3]),
            "yearly_price":  float(r[4]),
            "sort_order":    r[5],
        }
        for r in rows
    ]
