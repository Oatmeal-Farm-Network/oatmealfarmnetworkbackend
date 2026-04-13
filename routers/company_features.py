from fastapi import APIRouter, Depends, Query
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db

router = APIRouter(prefix="/api/company", tags=["company"])


@router.get("/features")
def get_features(
    business_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    """Return feature flags for a business based on its subscription package.

    Logic:
    - If business_id is given:
        1. Check whether the business has a SubscriptionTier set.
        2. If SubscriptionTier is set → return only the features from that package
           (empty list if the package has no features assigned yet).
        3. If SubscriptionTier is NULL/empty → fall back to site-wide flags,
           so unsubscribed businesses still see all features.
    - No business_id → return all site-wide CompanySiteManagement rows (admin use).
    """
    if business_id is not None:
        # Check whether the business has a subscription assigned
        tier_row = db.execute(
            text("SELECT SubscriptionTier FROM Business WHERE BusinessID = :bid"),
            {"bid": business_id},
        ).fetchone()

        has_subscription = tier_row and tier_row[0] and str(tier_row[0]).strip()

        if has_subscription:
            # Return only features from the assigned package
            rows = db.execute(
                text(
                    """
                    SELECT csm.FeatureKey, csm.FeatureName, csm.IsEnabled,
                           csm.MonthlyPrice, csm.YearlyPrice, csm.SortOrder
                    FROM Business b
                    JOIN SubscriptionPackage sp ON sp.PackageName = b.SubscriptionTier
                    JOIN SubscriptionPackageFeature spf ON spf.PackageID = sp.PackageID
                    JOIN CompanySiteManagement csm ON csm.FeatureID = spf.FeatureID
                    WHERE b.BusinessID = :bid
                      AND sp.IsActive = 1
                    ORDER BY csm.SortOrder
                    """
                ),
                {"bid": business_id},
            ).fetchall()

            return [
                {
                    "feature_key":   r[0],
                    "feature_name":  r[1],
                    "is_enabled":    True,   # included in package → always on
                    "monthly_price": float(r[3]),
                    "yearly_price":  float(r[4]),
                    "sort_order":    r[5],
                }
                for r in rows
            ]
        # Business exists but has no subscription → fall through to site-wide flags

    # Site-wide fallback: all CompanySiteManagement rows
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
