"""
Lavendir — AI Website Design Agent
Gemini-powered RAG + function-calling agent that guides users through building
their website and can make changes directly (with user confirmation).
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db
from pydantic import BaseModel
from typing import Optional, List, Any
import os, json, datetime

router = APIRouter(prefix="/api/lavendir", tags=["lavendir-ai"])

AGENT_NAME = "Lavendir"

# ── GCP / Firestore config ────────────────────────────────────────
GCP_PROJECT   = "animated-flare-421518"
GCP_CREDS     = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
FIRESTORE_DB  = "artemis"
LAVENDIR_COLLECTION = "lavendir-docs"

# ── Pydantic models ───────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str        # 'user' | 'assistant'
    content: str

class ChatRequest(BaseModel):
    website_id: int
    business_id: int
    messages: List[ChatMessage]
    current_page: Optional[str] = None

class ConfirmAction(BaseModel):
    website_id: int
    business_id: int
    action: str      # action name
    params: dict     # params to execute
    confirmed: bool


# ── Firestore RAG ─────────────────────────────────────────────────

_firestore_client = None

def _get_firestore():
    global _firestore_client
    if _firestore_client:
        return _firestore_client
    try:
        from google.cloud import firestore
        if GCP_CREDS:
            from google.oauth2 import service_account
            creds = service_account.Credentials.from_service_account_file(
                GCP_CREDS,
                scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
            _firestore_client = firestore.Client(
                project=GCP_PROJECT, database=FIRESTORE_DB, credentials=creds
            )
        else:
            _firestore_client = firestore.Client(
                project=GCP_PROJECT, database=FIRESTORE_DB
            )
        print("[Lavendir] Firestore connected")
    except Exception as e:
        print(f"[Lavendir] Firestore unavailable: {e}")
    return _firestore_client


def _rag_search(query: str, n: int = 5) -> str:
    """
    Search lavendir-docs. Supports both:
    - Vector search (if docs have 'embedding' field)
    - Full-text fallback (returns all docs, ranked by keyword presence)
    """
    try:
        db = _get_firestore()
        if not db:
            return ""

        col = db.collection(LAVENDIR_COLLECTION)

        # Try vector search first
        try:
            from google.cloud.firestore_v1.vector import Vector
            from google.cloud.firestore_v1.base_vector_query import DistanceMeasure
            import google.generativeai as genai
            genai.configure(api_key=os.getenv("GOOGLE_API_KEY", ""))
            result = genai.embed_content(
                model="models/text-embedding-004",
                content=query,
                task_type="retrieval_query"
            )
            q_vec = result["embedding"]
            vq = col.find_nearest(
                vector_field="embedding",
                query_vector=Vector(q_vec),
                distance_measure=DistanceMeasure.COSINE,
                limit=n
            )
            docs = list(vq.stream())
            if docs:
                parts = []
                for doc in docs:
                    d = doc.to_dict()
                    content = d.get("content") or d.get("text") or ""
                    if content:
                        parts.append(content)
                if parts:
                    return "Knowledge base:\n" + "\n---\n".join(parts)
        except Exception:
            pass  # fall through to keyword scan

        # Fallback: fetch up to 50 docs, return those containing query keywords
        all_docs = list(col.limit(50).stream())
        keywords = query.lower().split()
        scored = []
        for doc in all_docs:
            d = doc.to_dict()
            # Handle flat docs like {"1": "some text"} or {"content": "..."}
            content = ""
            if "content" in d:
                content = str(d["content"])
            elif "text" in d:
                content = str(d["text"])
            else:
                # join all string values
                content = " ".join(str(v) for v in d.values() if isinstance(v, str))
            if not content.strip():
                continue
            score = sum(1 for kw in keywords if kw in content.lower())
            if score > 0:
                scored.append((score, content))

        scored.sort(reverse=True)
        top = [c for _, c in scored[:n]]
        if top:
            return "Knowledge base:\n" + "\n---\n".join(top)

    except Exception as e:
        print(f"[Lavendir] RAG search error: {e}")
    return ""


# ── Live website context (SQL) ────────────────────────────────────

def _get_site_context(website_id: int, business_id: int, db: Session) -> str:
    try:
        site = db.execute(
            text("""SELECT SiteName, Slug, Tagline, PrimaryColor, SecondaryColor,
                          AccentColor, BgColor, TextColor, FontFamily, IsPublished,
                          LogoURL, Phone, Email, Address
                   FROM BusinessWebsite WHERE WebsiteID=:wid"""),
            {"wid": website_id}
        ).fetchone()
    except Exception:
        site = None

    try:
        pages = db.execute(
            text("SELECT PageName, Slug, IsPublished, IsHomePage FROM BusinessWebPage WHERE WebsiteID=:wid ORDER BY SortOrder"),
            {"wid": website_id}
        ).fetchall()
    except Exception:
        pages = []

    try:
        biz = db.execute(
            text("SELECT b.BusinessName, bt.BusinessType FROM Business b JOIN BusinessTypes bt ON bt.BusinessTypeID=b.BusinessTypeID WHERE b.BusinessID=:bid"),
            {"bid": business_id}
        ).fetchone()
    except Exception:
        biz = None

    lines = []
    if biz:
        lines.append(f"Business: {biz.BusinessName} ({biz.BusinessType})")
    if site:
        lines += [
            f"Site name: {site.SiteName}",
            f"URL slug: /sites/{site.Slug}",
            f"Tagline: {site.Tagline or 'Not set'}",
            f"Primary color: {site.PrimaryColor}  Secondary: {site.SecondaryColor}  Accent: {site.AccentColor}",
            f"Background: {site.BgColor}  Text: {site.TextColor}",
            f"Font: {site.FontFamily}",
            f"Published: {'Yes' if site.IsPublished else 'No'}",
            f"Logo: {'Set' if site.LogoURL else 'Not set'}",
            f"Phone: {site.Phone or 'Not set'}  Email: {site.Email or 'Not set'}",
        ]
    if pages:
        lines.append("Pages: " + ", ".join(
            f"{p.PageName}{'[Home]' if p.IsHomePage else ''}{'[Hidden]' if not p.IsPublished else ''}"
            for p in pages
        ))
    else:
        lines.append("Pages: None created yet")

    return "\n".join(lines)


# ── Tools Lavendir can call ───────────────────────────────────────

TOOLS = [
    {
        "name": "update_site_design",
        "description": "Update site colors, font, tagline, or name. Use when the user wants to change the look of their site.",
        "parameters": {
            "type": "object",
            "properties": {
                "site_name":       {"type": "string", "description": "New site name"},
                "tagline":         {"type": "string", "description": "New tagline"},
                "primary_color":   {"type": "string", "description": "Hex color for nav/header background"},
                "secondary_color": {"type": "string", "description": "Hex color for secondary elements"},
                "accent_color":    {"type": "string", "description": "Hex color for buttons/highlights"},
                "bg_color":        {"type": "string", "description": "Hex color for page background"},
                "text_color":      {"type": "string", "description": "Hex color for body text"},
                "font_family":     {"type": "string", "description": "CSS font family string"},
                "nav_text_color":  {"type": "string", "description": "Hex color for nav text"},
                "footer_bg_color": {"type": "string", "description": "Hex color for footer background"},
            },
            "required": []
        }
    },
    {
        "name": "update_site_settings",
        "description": "Update site contact info, social links, or URL slug.",
        "parameters": {
            "type": "object",
            "properties": {
                "phone":         {"type": "string"},
                "email":         {"type": "string"},
                "address":       {"type": "string"},
                "facebook_url":  {"type": "string"},
                "instagram_url": {"type": "string"},
                "twitter_url":   {"type": "string"},
                "slug":          {"type": "string", "description": "URL slug (lowercase, hyphens only)"},
            },
            "required": []
        }
    },
    {
        "name": "add_page",
        "description": "Add a new page to the website.",
        "parameters": {
            "type": "object",
            "properties": {
                "page_name": {"type": "string", "description": "Display name of the page"},
                "slug":      {"type": "string", "description": "URL slug for the page"},
            },
            "required": ["page_name"]
        }
    },
    {
        "name": "publish_site",
        "description": "Publish or unpublish the website.",
        "parameters": {
            "type": "object",
            "properties": {
                "publish": {"type": "boolean", "description": "True to publish, False to unpublish"}
            },
            "required": ["publish"]
        }
    },
]

# Human-readable summaries for confirmation prompts
def _describe_action(action: str, params: dict) -> str:
    if action == "update_site_design":
        changes = ", ".join(f"{k} → {v}" for k, v in params.items())
        return f"Update design: {changes}"
    if action == "update_site_settings":
        changes = ", ".join(f"{k} → {v}" for k, v in params.items())
        return f"Update settings: {changes}"
    if action == "add_page":
        return f"Add a new page: \"{params.get('page_name')}\""
    if action == "publish_site":
        return "Publish your website" if params.get("publish") else "Unpublish your website"
    return f"{action}: {params}"


# ── Execute confirmed action ──────────────────────────────────────

def _execute_action(action: str, params: dict, website_id: int, business_id: int, db: Session) -> str:
    import models
    from datetime import datetime as dt

    if action == "update_site_design":
        site = db.query(models.BusinessWebsite).filter(models.BusinessWebsite.WebsiteID == website_id).first()
        if not site:
            return "Site not found."
        field_map = {
            "site_name": "SiteName", "tagline": "Tagline",
            "primary_color": "PrimaryColor", "secondary_color": "SecondaryColor",
            "accent_color": "AccentColor", "bg_color": "BgColor",
            "text_color": "TextColor", "font_family": "FontFamily",
            "nav_text_color": "NavTextColor", "footer_bg_color": "FooterBgColor",
        }
        for k, v in params.items():
            if k in field_map and v:
                setattr(site, field_map[k], v)
        site.UpdatedAt = dt.utcnow()
        db.commit()
        return "Design updated successfully."

    if action == "update_site_settings":
        site = db.query(models.BusinessWebsite).filter(models.BusinessWebsite.WebsiteID == website_id).first()
        if not site:
            return "Site not found."
        field_map = {
            "phone": "Phone", "email": "Email", "address": "Address",
            "facebook_url": "FacebookURL", "instagram_url": "InstagramURL",
            "twitter_url": "TwitterURL", "slug": "Slug",
        }
        for k, v in params.items():
            if k in field_map and v:
                setattr(site, field_map[k], v)
        site.UpdatedAt = dt.utcnow()
        db.commit()
        return "Settings updated successfully."

    if action == "add_page":
        import re
        page_name = params.get("page_name", "New Page")
        slug = params.get("slug") or re.sub(r'[^a-z0-9]+', '-', page_name.lower()).strip('-')
        page = models.BusinessWebPage(
            WebsiteID=website_id, BusinessID=business_id,
            PageName=page_name, Slug=slug,
            IsPublished=True, IsHomePage=False,
            SortOrder=999, CreatedAt=dt.utcnow(), UpdatedAt=dt.utcnow()
        )
        db.add(page); db.commit()
        return f"Page \"{page_name}\" added successfully."

    if action == "publish_site":
        site = db.query(models.BusinessWebsite).filter(models.BusinessWebsite.WebsiteID == website_id).first()
        if not site:
            return "Site not found."
        site.IsPublished = params.get("publish", True)
        site.UpdatedAt = dt.utcnow()
        db.commit()
        return "Site published." if site.IsPublished else "Site unpublished."

    return "Unknown action."


# ── System prompt ─────────────────────────────────────────────────

def _build_system_prompt(site_context: str, rag_context: str) -> str:
    return f"""You are {AGENT_NAME}, a warm and knowledgeable AI website design assistant for OatmealFarmNetwork — a platform for farmers, ranchers, and agricultural businesses.

You guide users in building beautiful, effective farm websites. You can ALSO make changes to their website directly when asked — you will propose the change and wait for the user to confirm before executing it.

WEBSITE BUILDER FEATURES YOU KNOW:
- Pages, Blocks (hero, about, content, livestock, produce, meat, services, gallery, blog, contact, divider)
- Design: colors, fonts, logo, header images with date ranges
- Settings: site name, slug, contact info, social media
- SEO: meta title, canonical URL, Open Graph image, schema markup
- Version History: save and restore snapshots
- 12 color palettes: Farmstead, Harvest, Modern Market, Artisan, Fresh, Classic, Meadow, Sunset Ranch, Slate & Stone, Lavender Field, Coastal, Midnight
- Publish/Unpublish control

WHEN THE USER ASKS YOU TO MAKE A CHANGE:
- Use the appropriate tool to propose the change
- Be specific about what you're about to change
- Keep responses concise — 2-3 short paragraphs max
- After a change is confirmed and done, tell the user to refresh their browser to see it

CURRENT WEBSITE STATE:
{site_context}

{f'KNOWLEDGE BASE:{chr(10)}{rag_context}' if rag_context else ''}

Always be encouraging, practical, and warm — like a knowledgeable creative friend helping them build something beautiful."""


# ── Chat endpoint ─────────────────────────────────────────────────

@router.post("/chat")
async def lavendir_chat(body: ChatRequest, db: Session = Depends(get_db)):
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="AI service not configured")

    # Build context
    site_context = _get_site_context(body.website_id, body.business_id, db)
    last_user_msg = next((m.content for m in reversed(body.messages) if m.role == "user"), "")
    rag_context   = _rag_search(last_user_msg) if last_user_msg else ""
    system_prompt = _build_system_prompt(site_context, rag_context)

    try:
        import google.generativeai as genai
        from google.generativeai.types import Tool, FunctionDeclaration
        genai.configure(api_key=api_key)

        # Build tool declarations for Gemini
        gemini_tools = [Tool(function_declarations=[
            FunctionDeclaration(
                name=t["name"],
                description=t["description"],
                parameters=t["parameters"]
            ) for t in TOOLS
        ])]

        model = genai.GenerativeModel(
            model_name="gemini-1.5-flash",
            system_instruction=system_prompt,
            tools=gemini_tools,
            generation_config={"temperature": 0.7, "max_output_tokens": 600},
        )

        history = []
        for msg in body.messages[:-1]:
            history.append({
                "role": "user" if msg.role == "user" else "model",
                "parts": [msg.content]
            })

        chat = model.start_chat(history=history)
        response = chat.send_message(last_user_msg)

        # Check if Gemini wants to call a tool
        candidate = response.candidates[0]
        for part in candidate.content.parts:
            if hasattr(part, "function_call") and part.function_call.name:
                fc = part.function_call
                action = fc.name
                params = dict(fc.args)
                description = _describe_action(action, params)
                return {
                    "role": "assistant",
                    "content": f"I'd like to make this change for you:\n\n**{description}**\n\nShall I go ahead?",
                    "pending_action": {"action": action, "params": params, "description": description},
                    "agent": AGENT_NAME,
                }

        reply = response.text

    except ImportError:
        reply = _fallback_response(last_user_msg)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI error: {str(e)}")

    return {"role": "assistant", "content": reply, "agent": AGENT_NAME}


# ── Confirm / reject an action ────────────────────────────────────

@router.post("/confirm")
def lavendir_confirm(body: ConfirmAction, db: Session = Depends(get_db)):
    if not body.confirmed:
        return {"role": "assistant", "content": "No problem — I won't make that change. What else can I help you with?", "agent": AGENT_NAME}

    result = _execute_action(body.action, body.params, body.website_id, body.business_id, db)
    return {
        "role": "assistant",
        "content": f"Done! {result} Refresh your browser to see the update. What would you like to do next?",
        "agent": AGENT_NAME,
        "action_completed": body.action,
    }


# ── Suggestions ───────────────────────────────────────────────────

@router.get("/suggestions/{website_id}")
def get_suggestions(website_id: int, db: Session = Depends(get_db)):
    suggestions = []
    try:
        site = db.execute(text("SELECT IsPublished, LogoURL, Tagline, Phone, Email FROM BusinessWebsite WHERE WebsiteID=:wid"), {"wid": website_id}).fetchone()
        if site:
            if not site.IsPublished:
                suggestions.append({"text": "Publish my site", "action": "publish"})
            if not site.LogoURL:
                suggestions.append({"text": "Help me upload a logo", "action": "design"})
            if not site.Tagline:
                suggestions.append({"text": "Write a tagline for my site", "action": "settings"})
            if not site.Phone and not site.Email:
                suggestions.append({"text": "Add my contact information", "action": "settings"})
        page_count = db.execute(text("SELECT COUNT(*) FROM BusinessWebPage WHERE WebsiteID=:wid"), {"wid": website_id}).fetchone()[0]
        if page_count < 3:
            suggestions.append({"text": "What pages should I add?", "action": "add_page"})
        header_count = db.execute(text("SELECT COUNT(*) FROM WebsiteHeaderImages WHERE WebsiteID=:wid"), {"wid": website_id}).fetchone()[0]
        if header_count == 0:
            suggestions.append({"text": "Add a header image", "action": "design"})
    except Exception:
        pass

    if not suggestions:
        suggestions = [
            {"text": "Suggest a color palette for my farm", "action": "design"},
            {"text": "How do I add seasonal header images?", "action": "design"},
            {"text": "Save a version backup", "action": "settings"},
            {"text": "Help me improve my About page", "action": "content"},
        ]
    return suggestions[:4]


# ── Fallback ──────────────────────────────────────────────────────

def _fallback_response(msg: str) -> str:
    msg = msg.lower()
    if any(w in msg for w in ["color","colour","palette","theme","design"]):
        return "To change your colors, go to the **Design** tab. You have 12 color palettes to choose from — Farmstead, Harvest, Modern Market, Artisan, Fresh, Classic, Meadow, Sunset Ranch, Slate & Stone, Lavender Field, Coastal, and Midnight. You can also fine-tune individual colors."
    if any(w in msg for w in ["page","add page"]):
        return "To add a new page, click **+ Add Page** at the top of the builder. You can then add content blocks to it."
    if any(w in msg for w in ["publish","live","public"]):
        return "When ready, click **Publish Site** in the top right to make your site public. You can unpublish anytime."
    if any(w in msg for w in ["seo","google","search"]):
        return "For SEO settings, go to the **Settings** tab and look for the SEO & Metadata section."
    return f"I'm {AGENT_NAME}, your website design assistant! I can help you build and improve your farm website — and I can even make changes directly when you ask. What would you like to work on?"
