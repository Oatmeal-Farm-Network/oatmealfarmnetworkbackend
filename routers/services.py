from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db
import httpx

router = APIRouter()

SENDGRID_API_KEY = "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"
SENDGRID_URL = "https://api.sendgrid.com/v3/mail/send"
FROM_EMAIL = "john@oatmeal-ai.com"
TO_EMAIL = "livestockoftheworld@gmail.com"

def send_email(subject: str, body: str):
    payload = {
        "personalizations": [{"to": [{"email": TO_EMAIL}]}],
        "from": {"email": FROM_EMAIL, "name": "Oatmeal Farm Network"},
        "subject": subject,
        "content": [{"type": "text/html", "value": body}],
    }
    headers = {
        "Authorization": f"Bearer {SENDGRID_API_KEY}",
        "Content-Type": "application/json",
    }
    try:
        httpx.post(SENDGRID_URL, json=payload, headers=headers, timeout=10)
    except Exception as e:
        print(f"SendGrid error: {e}")

# -------------------------
# List services for a business
# -------------------------
@router.get("/api/services")
def list_services(BusinessID: int, db: Session = Depends(get_db)):
    rows = db.execute(text("""
        SELECT ServicesID, ServiceTitle, ServiceAvailable, ServicePrice, ServiceContactForPrice
        FROM Services WHERE BusinessID = :bid ORDER BY ServiceTitle
    """), {"bid": BusinessID}).fetchall()
    return [dict(r._mapping) for r in rows]

# -------------------------
# Get categories
# -------------------------
@router.get("/api/services/categories")
def get_categories(db: Session = Depends(get_db)):
    rows = db.execute(text("""
        SELECT ServiceCategoryID, ServicesCategory
        FROM servicescategories
        ORDER BY ServicesCategory
    """)).fetchall()
    return [dict(r._mapping) for r in rows]

# -------------------------
# Get subcategories for a category
# -------------------------
@router.get("/api/services/categories/{category_id}/subcategories")
def get_subcategories(category_id: int, db: Session = Depends(get_db)):
    rows = db.execute(text("""
        SELECT ServiceSubCategoryID, ServiceSubCategoryName
        FROM servicessubcategories
        WHERE ServiceCategoryID = :cid
        ORDER BY ServiceSubCategoryName
    """), {"cid": category_id}).fetchall()
    return [dict(r._mapping) for r in rows]

# -------------------------
# Add a service
# -------------------------
@router.post("/api/services/add")
def add_service(data: dict, db: Session = Depends(get_db)):
    db.execute(text("""
        INSERT INTO Services (
            BusinessID, ServiceCategoryID, ServiceSubCategoryID, ServiceTitle,
            ServicePrice, ServiceContactForPrice, ServiceAvailable, ServicesDescription,
            ServicePhone, Servicewebsite, Serviceemail
        ) VALUES (
            :bid, :cat, :subcat, :title,
            :price, :cfp, :avail, :desc,
            :phone, :web, :email
        )
    """), {
        "bid": data.get("BusinessID"),
        "cat": data.get("ServiceCategoryID") or None,
        "subcat": data.get("ServiceSubCategoryID") or None,
        "title": data.get("ServiceTitle"),
        "price": data.get("ServicePrice") or None,
        "cfp": data.get("ServiceContactForPrice", 0),
        "avail": data.get("ServiceAvailable"),
        "desc": data.get("ServicesDescription"),
        "phone": data.get("ServicePhone"),
        "web": data.get("Servicewebsite"),
        "email": data.get("Serviceemail"),
    })
    new_id = db.execute(text("SELECT SCOPE_IDENTITY() AS id")).fetchone()
    db.commit()
    return {"ServicesID": int(new_id.id)}

# -------------------------
# Suggest a new category (sends email via SendGrid)
# -------------------------
@router.post("/api/services/suggest-category")
def suggest_category(data: dict):
    business_name = data.get("BusinessName", "Unknown")
    categories = data.get("Categories", "")
    subcategories = data.get("SubCategories", "")

    body = f"""
    <h2>New Service Category Suggestion</h2>
    <p><b>Business:</b> {business_name}</p>
    <p><b>Suggested Categories:</b><br>{categories}</p>
    <p><b>Suggested Sub-Categories:</b><br>{subcategories or 'None provided'}</p>
    """

    send_email(
        subject=f"Service Category Suggestion from {business_name}",
        body=body,
    )
    return {"message": "Suggestion sent"}
