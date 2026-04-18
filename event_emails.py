"""
Event registration confirmation emails.

Sends a polished confirmation with event details + a QR code that encodes
the registrant's check-in token. The QR is rendered via a hosted QR generator
(api.qrserver.com) so nothing extra needs to be installed and images survive
most email clients.
"""
import os
import urllib.parse

SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY", "")
FROM_EMAIL       = os.getenv("FROM_EMAIL", "john@oatmeal-ai.com")
FROM_NAME        = os.getenv("FROM_NAME", "Oatmeal Farm Network")
OFN_BASE_URL     = os.getenv("OFN_BASE_URL", "https://oatmealfarmnetwork.com")


def _qr_url(payload: str, size: int = 220) -> str:
    return (
        f"https://api.qrserver.com/v1/create-qr-code/"
        f"?size={size}x{size}&data={urllib.parse.quote(payload)}"
    )


def _send(to: str, subject: str, html: str) -> bool:
    if not SENDGRID_API_KEY or not to:
        return False
    try:
        import sendgrid
        from sendgrid.helpers.mail import Mail, Email, To, Content
        sg = sendgrid.SendGridAPIClient(api_key=SENDGRID_API_KEY)
        message = Mail(
            from_email=Email(FROM_EMAIL, FROM_NAME),
            to_emails=To(to),
            subject=subject,
            html_content=Content("text/html", html),
        )
        response = sg.send(message)
        return response.status_code < 300
    except Exception as ex:
        print(f"[event_email] send to {to} failed: {ex}")
        return False


def _fmt_date(d):
    if not d: return ''
    try:
        return d.strftime('%A, %B %d, %Y')
    except Exception:
        return str(d)


def _event_block(event: dict) -> str:
    addr = ', '.join(x for x in [
        event.get('EventLocationName'), event.get('EventLocationStreet'),
        event.get('EventLocationCity'), event.get('EventLocationState'),
        event.get('EventLocationZip')
    ] if x)
    return f"""
      <tr><td style="padding:6px 0;font-size:13px;color:#555">
        <strong>When:</strong> {_fmt_date(event.get('EventStartDate'))}
      </td></tr>
      {f'<tr><td style="padding:6px 0;font-size:13px;color:#555"><strong>Where:</strong> {addr}</td></tr>' if addr else ''}
    """


def send_registration_confirmation(
    to_email: str,
    attendee_name: str,
    event: dict,
    kind: str,
    reg_id: int,
    extra_html: str = "",
):
    """
    Generic confirmation. kind is one of Simple|Conference|Competition|Dining|Tour.
    QR encodes plain reg_id so the unified check-in scanner finds it by exact match.
    """
    if not to_email:
        return False
    qr = _qr_url(str(reg_id))
    event_id = event.get('EventID')
    subject = f"You're registered: {event.get('EventName', 'Event')}"
    name = (attendee_name or '').split()[0] if attendee_name else 'there'
    html = f"""
<!DOCTYPE html>
<html><body style="font-family:Georgia,serif;background:#FAF7EE;margin:0;padding:24px">
  <table width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;margin:0 auto;background:white;border-radius:12px;overflow:hidden">
    <tr><td style="background:#3D6B34;color:white;padding:20px 24px;">
      <div style="font-size:12px;text-transform:uppercase;letter-spacing:0.15em;opacity:0.8">Registration Confirmed</div>
      <div style="font-size:22px;font-weight:600;margin-top:4px">{event.get('EventName','Event')}</div>
    </td></tr>
    <tr><td style="padding:20px 24px">
      <p style="font-size:14px;color:#333;margin:0 0 12px">Hi {name},</p>
      <p style="font-size:14px;color:#555;margin:0 0 16px">
        Your spot is reserved. Details below — save this email and show the QR code at check-in.
      </p>
      <table width="100%" cellpadding="0" cellspacing="0" style="border-top:1px solid #eee;border-bottom:1px solid #eee;margin:12px 0">
        {_event_block(event)}
        <tr><td style="padding:6px 0;font-size:13px;color:#555">
          <strong>Type:</strong> {kind}
        </td></tr>
        <tr><td style="padding:6px 0;font-size:13px;color:#555">
          <strong>Reference #:</strong> {reg_id}
        </td></tr>
      </table>
      {extra_html}
      <div style="text-align:center;margin:20px 0">
        <img src="{qr}" alt="Check-in QR" style="border:6px solid #3D6B34;border-radius:8px" />
        <div style="font-size:11px;color:#999;margin-top:6px">Scan at check-in · Ref {reg_id}</div>
      </div>
      <p style="font-size:12px;color:#999;margin:16px 0 0">
        Questions? Reply to this email. View your registrations any time at
        <a href="{OFN_BASE_URL}/my-registrations" style="color:#3D6B34">{OFN_BASE_URL}/my-registrations</a>.
      </p>
    </td></tr>
  </table>
</body></html>"""
    return _send(to_email, subject, html)
