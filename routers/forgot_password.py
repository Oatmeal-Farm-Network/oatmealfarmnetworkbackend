# --- routers/forgot_password.py ---
import os
import logging
import sendgrid
from sendgrid.helpers.mail import Mail
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr

from database import get_db_cursor

logger = logging.getLogger(__name__)

router = APIRouter()

SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY", "")
FROM_EMAIL       = os.getenv("FROM_EMAIL", "john@oatmeal-ai.com")
SITE_NAME        = os.getenv("SITE_NAME", "Oatmeal Farm Network")


class ForgotPasswordRequest(BaseModel):
    Email: EmailStr


@router.post("/auth/forgot-password")
async def forgot_password(body: ForgotPasswordRequest):
    email = body.Email.strip().lower()

    # ── 1. Look up user in MSSQL ────────────────────────────────────────────
    try:
        cursor = get_db_cursor()
        cursor.execute(
            "SELECT PeopleFirstName, PeoplePassword FROM People WHERE LOWER(PeopleEmail) = %s",
            (email,)
        )
        row = cursor.fetchone()
    except Exception as exc:
        logger.exception("MSSQL query failed: %s", exc)
        raise HTTPException(status_code=500, detail="Database error. Please try again.")

    if not row:
        raise HTTPException(status_code=404, detail="Email not found")

    first_name      = row.get("PeopleFirstName", "")
    stored_password = row.get("PeoplePassword", "")

    if not stored_password:
        raise HTTPException(status_code=500, detail="No password on file. Please contact support.")

    # ── 2. Send via SendGrid ─────────────────────────────────────────────────
    if not SENDGRID_API_KEY:
        raise HTTPException(status_code=503, detail="Email service not configured.")

    html_body = f"""
    <font face="arial">
    Dear {first_name},<br><br>
    Your {SITE_NAME} password is provided below:<br><br>
    Your password: <b>{stored_password}</b><br><br>
    If you did not request this email, please contact us at 458.225.4903.<br><br>
    Thank You.<br><br>
    Sincerely,<br><br>
    {SITE_NAME}<br><br><br>
    <em>Protect Your Password — never share it with anyone,
    including {SITE_NAME} representatives.</em>
    </font>
    """

    try:
        sg = sendgrid.SendGridAPIClient(api_key=SENDGRID_API_KEY)
        sg.send(Mail(
            from_email=FROM_EMAIL,
            to_emails=email,
            subject=f"Your {SITE_NAME} Password",
            html_content=html_body,
        ))
        logger.info("Password email sent to %s", email)
    except Exception as exc:
        logger.exception("SendGrid send failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to send email. Please try again.")

    return {"message": "Password sent", "email": email}
