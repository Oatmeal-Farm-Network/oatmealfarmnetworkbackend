from fastapi import APIRouter, Depends, Query
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db

router = APIRouter(prefix="/api/company", tags=["company"])

# Canonical feature registry — any key used by the frontend must appear here
# so /app/admin/site-management (which reads CompanySiteManagement) can toggle
# it and subscription packages can reference it. Ordering controls display
# order in the admin UI.
DEFAULT_FEATURES = [
    ("precision_ag",         "Precision Ag",              0.0,   0.0,  1),
    ("blog",                 "Blog",                      0.0,   0.0,  2),
    ("farm_2_table",         "Farm 2 Table",              0.0,   0.0,  3),
    ("livestock",            "Livestock",                 0.0,   0.0,  4),
    ("products",             "Products",                  0.0,   0.0,  5),
    ("services",             "Services",                  0.0,   0.0,  6),
    ("events",               "Events",                    0.0,   0.0,  7),
    ("properties",           "Properties",                0.0,   0.0,  8),
    ("associations",         "Associations",              0.0,   0.0,  9),
    ("my_website",           "My Website",               25.0, 200.0, 10),
    ("audio_settings",       "Audio Settings",            0.0,   0.0, 11),
    ("accounting",           "Accounting",                0.0,   0.0, 12),
    ("testimonials",         "Testimonials",              0.0,   0.0, 13),
    ("provenance",           "Sourced-From Cards",        0.0,   0.0, 14),
    ("chef_dashboard",       "Chef Dashboard",            0.0,   0.0, 15),
    ("pairsley",             "Pairsley AI (Restaurants)", 0.0,   0.0, 16),
    ("rosemarie",            "Rosemarie AI (Artisans)",   0.0,   0.0, 17),
    ("restaurant_sourcing",  "Restaurant Sourcing",       0.0,   0.0, 18),
    ("business_directory",   "Business Directory",        0.0,   0.0, 98),
    ("food_system_newsfeed", "Food System Newsfeed",      0.0,   0.0, 99),
]


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


@router.post("/features/register-defaults")
def register_default_features(db: Session = Depends(get_db)):
    """Idempotently insert any missing DEFAULT_FEATURES into CompanySiteManagement.

    Safe to call repeatedly. Existing rows are left untouched — admins may have
    adjusted names, prices, IsEnabled, or SortOrder via /app/admin/site-management.
    Only brand-new feature keys are inserted.
    """
    existing = {
        r[0] for r in db.execute(text("SELECT FeatureKey FROM CompanySiteManagement")).fetchall()
    }
    inserted = []
    for key, name, monthly, yearly, sort_order in DEFAULT_FEATURES:
        if key in existing:
            continue
        db.execute(
            text(
                """
                INSERT INTO CompanySiteManagement
                    (FeatureKey, FeatureName, IsEnabled, MonthlyPrice, YearlyPrice, SortOrder)
                VALUES (:k, :n, 1, :m, :y, :s)
                """
            ),
            {"k": key, "n": name, "m": monthly, "y": yearly, "s": sort_order},
        )
        inserted.append(key)
    db.commit()
    return {"inserted": inserted, "already_present": sorted(existing)}
