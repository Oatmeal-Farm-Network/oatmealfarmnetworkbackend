from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy.orm import Session
from app.routers import auth
from app.database import get_db, SessionLocal
import os
from app import models
from dotenv import load_dotenv

from app.routers import businesses
from app.routers import precision_ag
from app.routers import precision_ag_features
from app.routers import field_maturity
from app.routers import climate_forecast
from app.routers import field_assessment_report
from app.routers import crop_monitor_proxy
from app.routers import plant_knowledgebase
from app.routers import crop_summary
from app.routers import ingredient_knowledgebase
from app.routers import livestock
from app.routers import produce
from app.routers import processed_food
from app.routers import services
from app.routers import ranches
from app.routers import meat
from app.routers import forgot_password
from app.routers import weather
from app.routers import notes
from app.routers import crop_rotation
from app.routers import website_builder
from app.routers import website_ai
from app.routers import scraper_knowledge
from app.routers import sfproducts
from app.routers import events
from app.routers import event_fiber_arts
from app.routers import event_fleece
from app.routers import event_spinoff
from app.routers import event_halter
from app.routers import event_auction
from app.routers import event_vendor_fair
from app.routers import event_dining
from app.routers import event_farm_tour
from app.routers import event_simple
from app.routers import event_conference
from app.routers import event_competition
from app.routers import event_checkin
from app.routers import event_broadcast
from app.routers import my_registrations
from app.routers import event_analytics
from app.routers import event_features
from app.routers import company_features
from app.routers import dashboard as dashboard_router
from app.routers import associations
from app.routers import blog
from app.routers import accounting
from app.routers import animals
from app.routers import herd_health
from app.routers import platform_settings
from app.routers import platform_subscriptions
from app.routers import platform_services
from app.routers import event_registration_cart
from app.routers import event_meals
from app.routers import event_exports
from app.routers import event_mailing_list
from app.routers import event_promo_codes
from app.routers import event_waitlist
from app.routers import event_testimonials
from app.routers import event_sponsorship
from app.routers import event_leads
from app.routers import event_floor_plan
from app.routers import event_booth_services
from app.routers import event_coi
from app.routers import food_aggregator
from app.routers import esg_reports
from app.routers import stripe_payments
from app.routers import news
from app.routers import thaiyme
from app.routers import market_alerts
from app.routers import commodity_history
from app.routers import provenance
from app.routers import field_health_alerts

from app.routers.marketplace import marketplace_router
from app.services.marketplace_stripe import stripe_router
from app.routers.equipment_marketplace import equipment_router
from app.routers.food_wanted import food_wanted_router
from app.routers import notifications
from app.routers import mill
from app.routers import job_board
from app.routers import csa
from app.routers import land_leasing
from app.routers import certifications
from app.routers import supplier_directory
from app.routers import grants
from app.routers import education
from app.routers import csa_advanced
from app.routers import meetings
from app.routers import recipes_batches
from app.routers import cold_chain
from app.routers import farmer_settlement
from app.routers import supply_chain
from app.routers import supply_chain_events
from app.routers import supply_chain_ai
from app.routers import hr
from app.routers import farm_inputs
from app.routers import crop_budgets
from app.routers import harvest_lots
from app.routers import farm_infrastructure
from app.routers import farm_kpi
from app.routers import nursery
from app.routers import outgrower
from app.routers import procurement
from app.routers import work_orders
from app.routers import packhouse_qc
from app.routers import plant_tagging
from app.routers import export_compliance
from app.routers import supplier_scorecard
from app.routers import esci
from app.routers import picker_performance
from app.routers import iot_greenhouse
from app.routers import perishable_trace
from app.routers import chilling_hours
from app.routers import grain_bin
from app.routers import scale_tickets
from app.routers import harvest_bins
from app.routers import ca_storage
from app.routers import spray_applications
from app.routers import scouting
from app.routers import irrigation
from app.routers import equipment_maintenance
from app.routers import soil_tests
from app.routers import cash_flow
from app.routers import field_activity
from app.routers import yield_records
from app.routers import reports
from app.routers import field_health
from app.routers import nutrients
from app.routers import farm_pl
from app.routers import document_vault
from app.routers import crop_planning
from app.routers import seed_varieties
from app.routers import farm_safety
from app.routers import buyer_crm
from app.routers import compliance_audit
from app.routers import harvest_scheduling
from app.routers import price_list
from app.routers import farm_stand
from app.routers import delivery_routes
from app.routers import agro_consultations
from app.routers import rbac

load_dotenv()

from fastapi import Request
from fastapi.responses import JSONResponse

ALLOWED_ORIGINS = [
    "http://localhost:5173", "http://localhost:5174", "http://localhost:5175", "http://localhost:5176", "http://localhost:5177", "http://localhost:3000",
    "https://oatmealfarmnetwork-802455386518.us-central1.run.app",
    "https://oatmealfarmnewtorkbackend-802455386518.us-central1.run.app",
    "https://crop-detection-dcecevhvh5ard2ah.eastus-01.azurewebsites.net",
    "https://www.oatmealfarmnetwork.com", "https://oatmealfarmnetwork.com",
    "https://lkm-802455386518.us-central1.run.app",
    "https://lkm-mt7mh6zhoa-uc.a.run.app",
    "https://lkm-frontend-802455386518.us-central1.run.app",
    "https://lkm-frontend-mt7mh6zhoa-uc.a.run.app",
    "https://www.lkmcpa.com", "https://lkmcpa.com",
]

def _is_allowed_origin(origin: str) -> bool:
    """Return True if origin is in the static list or matches a registered custom domain in the DB."""
    if not origin:
        return False
    if origin in ALLOWED_ORIGINS:
        return True
    if origin.startswith("https://"):
        try:
            from sqlalchemy import text as sa_text
            clean = origin.replace("https://", "").replace("http://", "").rstrip("/")
            alt = clean[4:] if clean.startswith("www.") else f"www.{clean}"
            with SessionLocal() as db:
                row = db.execute(
                    sa_text("SELECT TOP 1 1 FROM BusinessWebsite WHERE CanonicalURL LIKE :pat OR CanonicalURL LIKE :alt"),
                    {"pat": f"%{clean}%", "alt": f"%{alt}%"}
                ).first()
                return row is not None
        except Exception:
            pass
    return False

class DynamicCORSMiddleware(BaseHTTPMiddleware):
    """Replaces the static CORSMiddleware so registered custom domains are allowed automatically."""
    CORS_HEADERS = {
        "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization, Accept, x-people-id",
        "Access-Control-Max-Age": "86400",
    }

    async def dispatch(self, request: Request, call_next):
        origin = request.headers.get("origin", "")
        allowed = _is_allowed_origin(origin)

        if request.method == "OPTIONS":
            resp = Response(status_code=204)
            if allowed:
                resp.headers["Access-Control-Allow-Origin"] = origin
                resp.headers["Access-Control-Allow-Credentials"] = "true"
                for k, v in self.CORS_HEADERS.items():
                    resp.headers[k] = v
            return resp

        response = await call_next(request)
        if allowed:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
        return response

app = FastAPI()

@app.on_event("startup")
async def _startup_migrations():
    """Idempotent one-time data fixups — run in a thread so they never block startup."""
    import asyncio
    from sqlalchemy import text as _t

    def _run():
        try:
            with SessionLocal() as _db:
                _db.execute(_t(
                    "UPDATE speciescategory SET SpeciesCategory = 'Herdsire' "
                    "WHERE SpeciesCategory = 'Stud' AND SpeciesID = 2"
                ))
                _db.commit()
        except Exception:
            pass
        try:
            with SessionLocal() as _db:
                _db.execute(_t(
                    "IF NOT EXISTS (SELECT 1 FROM sys.columns "
                    "WHERE object_id = OBJECT_ID('BusinessWebsite') AND name = 'FooterJSON') "
                    "ALTER TABLE BusinessWebsite ADD FooterJSON NVARCHAR(MAX) NULL"
                ))
                _db.commit()
        except Exception:
            pass
        try:
            with SessionLocal() as _db:
                _db.execute(_t(
                    "IF NOT EXISTS (SELECT 1 FROM sys.columns "
                    "WHERE object_id = OBJECT_ID('People') AND name = 'LKMAccessLevel') "
                    "ALTER TABLE People ADD LKMAccessLevel INT NULL DEFAULT 0"
                ))
                _db.commit()
        except Exception:
            pass
        # Ensure BusinessServiceAccess table exists (may be created by Node.js admin; replicate here)
        try:
            with SessionLocal() as _db:
                _db.execute(_t(
                    "IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'BusinessServiceAccess') "
                    "CREATE TABLE BusinessServiceAccess ("
                    "  AccessID INT IDENTITY PRIMARY KEY,"
                    "  BusinessID INT NOT NULL,"
                    "  CategoryID INT NOT NULL,"
                    "  IsEnabled BIT NOT NULL DEFAULT 1,"
                    "  TierOverride NVARCHAR(50) NULL,"
                    "  CustomPrice DECIMAL(10,2) NULL,"
                    "  PriceNote NVARCHAR(500) NULL,"
                    "  UpdatedAt DATETIME2 DEFAULT GETDATE(),"
                    "  CONSTRAINT UQ_BizServiceCategory UNIQUE (BusinessID, CategoryID)"
                    ")"
                ))
                _db.commit()
        except Exception:
            pass
        # Add FeatureKey column to FeatureCategory (links admin catalog to OFN feature flags)
        try:
            with SessionLocal() as _db:
                _db.execute(_t(
                    "IF NOT EXISTS (SELECT 1 FROM sys.columns "
                    "WHERE object_id = OBJECT_ID('FeatureCategory') AND name = 'FeatureKey') "
                    "ALTER TABLE FeatureCategory ADD FeatureKey NVARCHAR(100) NULL"
                ))
                _db.commit()
        except Exception:
            pass
        # Populate FeatureKey on existing FeatureCategory rows by CategoryName → OFN key mapping
        _FEATURE_KEY_MAP = {
            'Precision Ag':                  'precision_ag',
            'Livestock & Herd Health':       'livestock',
            'Farm 2 Table — Seller':    'farm_2_table',
            'Farm 2 Table — Buyer':     'farm_2_table',
            'Livestock Marketplace':         'livestock',
            'Products & Storefront':         'products',
            'Equipment Marketplace':         'equipment',
            'Food Wanted Board':             'food_wanted',
            'Services Directory':            'services',
            'CSA':                           'csa_management',
            'Events':                        'events',
            'Job Board':                     'job_board',
            'Land Leasing':                  'land_leasing',
            'Certifications Tracker':        'certifications',
            'Supplier Directory':            'supplier_directory',
            'Grants & Programs':             'grants_programs',
            'Education Center':              'education_center',
            'Commodity Prices':              'commodity_prices',
            'Forums & Community':            'forums',
            'Blog':                          'blog',
            'Website Builder (Lavendir AI)': 'my_website',
            'Accounting':                    'accounting',
            'Testimonials & Social Proof':   'testimonials',
            'Properties Management':         'properties',
            'Cold Chain & Logistics':        'cold_chain',
            'Farmer Settlement & Pay':       'farmer_settlement',
            'Chef Dashboard':                'chef_dashboard',
            'Pairsley AI (Restaurants)':     'pairsley',
            'Rosemarie AI (Artisans)':       'rosemarie',
            'Restaurant Sourcing':           'restaurant_sourcing',
        }
        try:
            with SessionLocal() as _db:
                try:
                    rows = _db.execute(_t(
                        "SELECT CategoryID, CategoryName FROM FeatureCategory WHERE FeatureKey IS NULL"
                    )).fetchall()
                except Exception:
                    rows = []
                for row in rows:
                    fk = _FEATURE_KEY_MAP.get(row[1])
                    if fk:
                        _db.execute(
                            _t("UPDATE FeatureCategory SET FeatureKey = :fk WHERE CategoryID = :cid"),
                            {"fk": fk, "cid": row[0]},
                        )
                _db.commit()
        except Exception:
            pass

        # Idempotently seed CompanySiteManagement with all DEFAULT_FEATURES (IsEnabled=1)
        try:
            from app.routers.company_features import DEFAULT_FEATURES as _DF
            with SessionLocal() as _db:
                existing_keys = {r[0] for r in _db.execute(_t("SELECT FeatureKey FROM CompanySiteManagement")).fetchall()}
                for _key, _name, _monthly, _yearly, _sort in _DF:
                    if _key not in existing_keys:
                        _db.execute(
                            _t("INSERT INTO CompanySiteManagement (FeatureKey, FeatureName, IsEnabled, MonthlyPrice, YearlyPrice, SortOrder) "
                               "VALUES (:k, :n, 1, :m, :y, :s)"),
                            {"k": _key, "n": _name, "m": _monthly, "y": _yearly, "s": _sort},
                        )
                _db.commit()
        except Exception:
            pass

        # Auto-seed 5 default RBAC roles for every business that has none yet
        try:
            from app.routers.rbac import DEFAULT_ROLES as _DR, _ensure as _rbac_ensure
            with SessionLocal() as _db:
                _rbac_ensure(_db)
                biz_ids = [r[0] for r in _db.execute(_t(
                    "SELECT BusinessID FROM Business "
                    "WHERE BusinessID NOT IN (SELECT DISTINCT BusinessID FROM BusinessRole)"
                )).fetchall()]
                for _bid in biz_ids:
                    for _rname, _rdesc in _DR:
                        _db.execute(_t(
                            "INSERT INTO BusinessRole (BusinessID, RoleName, Description, IsSystem) "
                            "VALUES (:bid, :name, :desc, 1)"
                        ), {"bid": _bid, "name": _rname, "desc": _rdesc})
                if biz_ids:
                    _db.commit()
        except Exception:
            pass

    asyncio.get_event_loop().run_in_executor(None, _run)

    # Seed commodity price history if the table is empty (first deploy / cold start).
    # Runs in background so startup is never blocked.
    def _seed_prices():
        try:
            from app.routers.commodity_history import _fetch_and_store_prices
            from app.database import SessionLocal as _SL
            with _SL() as _db:
                has_data = _db.execute(
                    __import__('sqlalchemy').text(
                        "SELECT TOP 1 1 FROM CommodityPriceHistory WHERE FetchedAt >= DATEADD(hour, -25, GETDATE())"
                    )
                ).scalar()
            if not has_data:
                _fetch_and_store_prices()
        except Exception as _e:
            print(f"[startup] price seed skipped: {_e}")

    asyncio.get_event_loop().run_in_executor(None, _seed_prices)

    # ── Expiry reminder loop ─────────────────────────────────────────
    # Runs once on startup, then every 24 h. Fires notifications for:
    #   • Farm inputs expiring within 14 days
    #   • HR certifications expiring within 60 days
    def _expiry_reminder_loop():
        import time as _time
        while True:
            try:
                from app.routers.notifications import notify_business as _nb
                with SessionLocal() as _db:
                    # Farm inputs expiring in ≤14 days
                    inp_rows = _db.execute(__import__('sqlalchemy').text("""
                        SELECT BusinessID, InputName, ExpiryDate, InputID
                        FROM FarmInput
                        WHERE IsActive = 1
                          AND ExpiryDate IS NOT NULL
                          AND ExpiryDate > CAST(GETDATE() AS DATE)
                          AND ExpiryDate <= DATEADD(day, 14, CAST(GETDATE() AS DATE))
                    """)).fetchall()
                    seen_biz_input: set = set()
                    for r in inp_rows:
                        key = (r.BusinessID, r.InputID)
                        if key in seen_biz_input:
                            continue
                        seen_biz_input.add(key)
                        _nb(
                            _db, r.BusinessID,
                            type="input_expiry_warning",
                            title=f"Input Expiring Soon: {r.InputName}",
                            body=f"Expires {r.ExpiryDate} — use or dispose before it expires.",
                            link_path=f"/farm-inputs?BusinessID={r.BusinessID}",
                            entity_type="FarmInput",
                            entity_id=r.InputID,
                        )
                    if inp_rows:
                        _db.commit()

                    # HR certifications expiring in ≤60 days
                    cert_rows = _db.execute(__import__('sqlalchemy').text("""
                        SELECT c.BusinessID, e.FirstName + ' ' + e.LastName AS EmployeeName,
                               c.CertName, c.ExpiryDate, c.CertID
                        FROM HRCertification c
                        JOIN HREmployee e ON e.EmployeeID = c.EmployeeID
                        WHERE c.ExpiryDate IS NOT NULL
                          AND c.ExpiryDate > CAST(GETDATE() AS DATE)
                          AND c.ExpiryDate <= DATEADD(day, 60, CAST(GETDATE() AS DATE))
                    """)).fetchall()
                    seen_biz_cert: set = set()
                    for r in cert_rows:
                        key = (r.BusinessID, r.CertID)
                        if key in seen_biz_cert:
                            continue
                        seen_biz_cert.add(key)
                        _nb(
                            _db, r.BusinessID,
                            type="hr_cert_expiry_warning",
                            title=f"Certification Expiring: {r.CertName}",
                            body=f"{r.EmployeeName}'s {r.CertName} expires {r.ExpiryDate}.",
                            link_path=f"/hr?BusinessID={r.BusinessID}&tab=employees",
                            entity_type="HRCertification",
                            entity_id=r.CertID,
                        )
                    if cert_rows:
                        _db.commit()
            except Exception as _e:
                print(f"[expiry-reminder] error: {_e}")
            _time.sleep(86400)  # re-check every 24 h

    import threading as _threading
    _t = _threading.Thread(target=_expiry_reminder_loop, daemon=True, name="expiry-reminder")
    _t.start()

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    origin = request.headers.get("origin", "")
    headers = {}
    if _is_allowed_origin(origin):
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Credentials"] = "true"
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {str(exc)}"},
        headers=headers,
    )

app.add_middleware(DynamicCORSMiddleware)

app.include_router(auth.router)
app.include_router(associations.router)
app.include_router(businesses.router)
app.include_router(precision_ag.router)
app.include_router(precision_ag_features.router)
app.include_router(field_maturity.router)
app.include_router(climate_forecast.router)
app.include_router(field_assessment_report.router)
app.include_router(crop_monitor_proxy.router)
app.include_router(plant_knowledgebase.router)
app.include_router(crop_summary.router)
app.include_router(ingredient_knowledgebase.router)
app.include_router(livestock.router)
app.include_router(herd_health.router)
app.include_router(produce.router)
app.include_router(processed_food.router)
app.include_router(services.router)
app.include_router(ranches.router)
app.include_router(meat.router)

app.include_router(marketplace_router, prefix="/api/marketplace")
app.include_router(stripe_router, prefix="/api/marketplace/payments")
app.include_router(equipment_router, prefix="/api/equipment")
app.include_router(food_wanted_router, prefix="/api/food-wanted")
app.include_router(notifications.router)
app.include_router(mill.router)
app.include_router(job_board.router)
app.include_router(csa.router)
app.include_router(land_leasing.router)
app.include_router(certifications.router)
app.include_router(supplier_directory.router)
app.include_router(grants.router)
app.include_router(education.router)
app.include_router(csa_advanced.router)
app.include_router(forgot_password.router)
app.include_router(weather.router)
app.include_router(notes.router)
app.include_router(crop_rotation.router)
app.include_router(website_builder.router)
app.include_router(website_ai.router)
app.include_router(scraper_knowledge.router)
app.include_router(sfproducts.router)
app.include_router(event_features.router)
app.include_router(events.router)
app.include_router(event_fiber_arts.router)
app.include_router(event_fleece.router)
app.include_router(event_spinoff.router)
app.include_router(event_halter.router)
app.include_router(event_auction.router)
app.include_router(event_vendor_fair.router)
app.include_router(event_dining.router)
app.include_router(event_farm_tour.router)
app.include_router(event_simple.router)
app.include_router(event_conference.router)
app.include_router(event_competition.router)
app.include_router(event_checkin.router)
app.include_router(event_broadcast.router)
app.include_router(my_registrations.router)
app.include_router(event_analytics.router)
app.include_router(company_features.router)
app.include_router(dashboard_router.router)
app.include_router(blog.router)
app.include_router(accounting.router)
app.include_router(animals.router)
app.include_router(platform_settings.router)
app.include_router(platform_subscriptions.platform_subscriptions_router)
app.include_router(platform_services.router)
app.include_router(event_registration_cart.router)
app.include_router(event_meals.router)
app.include_router(event_exports.router)
app.include_router(event_mailing_list.router)
app.include_router(event_promo_codes.router)
app.include_router(event_waitlist.router)
app.include_router(event_testimonials.router)
app.include_router(event_sponsorship.router)
app.include_router(event_leads.router)
app.include_router(event_floor_plan.router)
app.include_router(event_booth_services.router)
app.include_router(event_coi.router)
app.include_router(food_aggregator.router)
app.include_router(esg_reports.router)
app.include_router(stripe_payments.router)
app.include_router(news.router)
app.include_router(thaiyme.router)
app.include_router(market_alerts.router)
app.include_router(commodity_history.router)
app.include_router(provenance.router)
app.include_router(field_health_alerts.router)
app.include_router(meetings.router)
app.include_router(recipes_batches.router)
app.include_router(cold_chain.router)
app.include_router(farmer_settlement.router)
app.include_router(supply_chain.router)
app.include_router(supply_chain_events.router)
app.include_router(supply_chain_ai.router)
app.include_router(hr.router)
app.include_router(farm_inputs.router)
app.include_router(crop_budgets.router)
app.include_router(harvest_lots.router)
app.include_router(farm_infrastructure.router)
app.include_router(farm_kpi.router)
app.include_router(nursery.router)
app.include_router(outgrower.router)
app.include_router(procurement.router)
app.include_router(work_orders.router)
app.include_router(packhouse_qc.router)
app.include_router(plant_tagging.router)
app.include_router(export_compliance.router)
app.include_router(supplier_scorecard.router)
app.include_router(esci.router)
app.include_router(picker_performance.router)
app.include_router(iot_greenhouse.router)
app.include_router(perishable_trace.router)
app.include_router(chilling_hours.router)
app.include_router(grain_bin.router)
app.include_router(scale_tickets.router)
app.include_router(harvest_bins.router)
app.include_router(ca_storage.router)
app.include_router(spray_applications.router)
app.include_router(scouting.router)
app.include_router(irrigation.router)
app.include_router(equipment_maintenance.router)
app.include_router(soil_tests.router)
app.include_router(cash_flow.router)
app.include_router(field_activity.router)
app.include_router(yield_records.router)
app.include_router(reports.router)
app.include_router(field_health.router)
app.include_router(nutrients.router)
app.include_router(farm_pl.router)
app.include_router(document_vault.router)
app.include_router(crop_planning.router)
app.include_router(seed_varieties.router)
app.include_router(farm_safety.router)
app.include_router(buyer_crm.router)
app.include_router(compliance_audit.router)
app.include_router(harvest_scheduling.router)
app.include_router(price_list.router)
app.include_router(farm_stand.router)
app.include_router(delivery_routes.router)
app.include_router(agro_consultations.router)
app.include_router(rbac.router)
app.include_router(rbac.AUDIT_ROUTER)


# ── Public testimonials endpoint (used by website blocks) ─────────
@app.get("/api/testimonials")
def get_public_testimonials(BusinessID: int, db: Session = Depends(get_db)):
    from sqlalchemy import text
    rows = db.execute(text("""
        SELECT TestimonialsID, CustomerName AS AuthorName,
               Testimonial AS Content, Rating,
               City, State, Organization, URL AS Website,
               TestimonialDate, PeopleID, Name,
               AnimalID, AnimalName, TestimonialsType
        FROM Testimonials
        WHERE CustID = :bid
        ORDER BY testimonialsOrder, TestimonialsID DESC
    """), {"bid": BusinessID}).fetchall()
    return [dict(r._mapping) for r in rows]


@app.get("/sitemap.xml", response_class=Response)
def dynamic_sitemap(db: Session = Depends(get_db)):
    from sqlalchemy import text
    from datetime import datetime

    BASE = "https://oatmealfarmnetwork.com"
    today = datetime.utcnow().strftime("%Y-%m-%d")

    static_pages = [
        ("/",                              "weekly",  "1.0"),
        ("/about",                         "monthly", "0.8"),
        ("/platform/saige",                "monthly", "0.9"),
        ("/platform/pairsley",             "monthly", "0.9"),
        ("/platform/rosemarie",            "monthly", "0.9"),
        ("/platform/thaiyme",              "monthly", "0.9"),
        ("/platform",                      "monthly", "0.8"),
        ("/app/news",                      "daily",   "0.7"),
        ("/events",                        "daily",   "0.8"),
        ("/blog",                          "weekly",  "0.7"),
        ("/services/directory",            "weekly",  "0.7"),
        ("/marketplaces/livestock",        "weekly",  "0.7"),
        ("/marketplaces/farm-to-table",    "weekly",  "0.7"),
        ("/marketplace/products",          "weekly",  "0.7"),
        ("/marketplaces/food-wanted",      "weekly",  "0.6"),
        ("/marketplaces/equipment",        "weekly",  "0.6"),
        ("/contact-us",                    "yearly",  "0.5"),
        ("/signup",                        "yearly",  "0.6"),
        ("/login",                         "yearly",  "0.5"),
    ]

    def _url(loc, lastmod, changefreq, priority):
        return (
            f"  <url>\n"
            f"    <loc>{loc}</loc>\n"
            f"    <lastmod>{lastmod}</lastmod>\n"
            f"    <changefreq>{changefreq}</changefreq>\n"
            f"    <priority>{priority}</priority>\n"
            f"  </url>"
        )

    urls = [_url(f"{BASE}{path}", today, freq, pri) for path, freq, pri in static_pages]

    # Blog posts
    try:
        rows = db.execute(text(
            "SELECT BlogID, UpdatedAt, PublishedAt FROM blog "
            "WHERE IsPublished = 1 ORDER BY COALESCE(UpdatedAt, PublishedAt) DESC"
        )).fetchall()
        for r in rows:
            dt = r.UpdatedAt or r.PublishedAt
            d = dt.strftime("%Y-%m-%d") if dt else today
            urls.append(_url(f"{BASE}/blog/{r.BlogID}", d, "monthly", "0.6"))
    except Exception:
        pass

    # Events
    try:
        rows = db.execute(text(
            "SELECT EventID, EventStartDate FROM OFNEvents "
            "WHERE IsPublished = 1 AND Deleted = 0 ORDER BY EventStartDate DESC"
        )).fetchall()
        for r in rows:
            d = r.EventStartDate.strftime("%Y-%m-%d") if r.EventStartDate else today
            urls.append(_url(f"{BASE}/events/{r.EventID}", d, "weekly", "0.6"))
    except Exception:
        pass

    # Services
    try:
        rows = db.execute(text(
            "SELECT ServicesID FROM Services WHERE ServiceAvailable = 1"
        )).fetchall()
        for r in rows:
            urls.append(_url(f"{BASE}/services/public/{r.ServicesID}", today, "monthly", "0.5"))
    except Exception:
        pass

    # Products
    try:
        rows = db.execute(text(
            "SELECT ProdID FROM sfproducts WHERE ProdQuantityAvailable > 0"
        )).fetchall()
        for r in rows:
            urls.append(_url(f"{BASE}/marketplace/products/{r.ProdID}", today, "weekly", "0.5"))
    except Exception:
        pass

    # News articles (Firestore)
    try:
        from app.routers.news import _get_db as _news_firestore
        fs = _news_firestore()
        if fs:
            from google.cloud.firestore_v1 import Query as FSQuery
            docs = (
                fs.collection("news_articles")
                .order_by("pubDate", direction=FSQuery.DESCENDING)
                .limit(300)
                .stream()
            )
            for doc in docs:
                data = doc.to_dict() or {}
                pub = data.get("pubDate")
                d = pub.strftime("%Y-%m-%d") if hasattr(pub, "strftime") else today
                urls.append(_url(f"{BASE}/app/news/{doc.id}", d, "never", "0.5"))
    except Exception:
        pass

    sitemap_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(urls)
        + "\n</urlset>"
    )
    return Response(content=sitemap_xml, media_type="application/xml")


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/test-env")
def test_env():
    return {
        "server": os.getenv("DB_SERVER"),
        "database": os.getenv("DB_NAME"),
        "user": os.getenv("DB_USER"),
        "password_set": bool(os.getenv("DB_PASSWORD"))
    }


@app.get("/test-db")
def test_db(db: Session = Depends(get_db)):
    from sqlalchemy import text
    result = db.execute(text("SELECT 1")).fetchone()
    return {"db": "connected", "result": str(result)}


@app.get("/test-people2")
def test_people2():
    from sqlalchemy import text
    db = SessionLocal()
    try:
        result = db.execute(text("SELECT TOP 1 PeopleID FROM People")).fetchone()
        return {"result": str(result)}
    except Exception as e:
        return {"error": str(e)}
    finally:
        db.close()
