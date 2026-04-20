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
import os, json, datetime, asyncio

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
        events = db.execute(
            text("""SELECT TOP 5 EventID, EventName, EventStartDate, IsPublished
                      FROM OFNEvents
                     WHERE BusinessID=:bid AND Deleted=0
                       AND (EventEndDate IS NULL OR EventEndDate >= CAST(GETDATE() AS DATE))
                     ORDER BY EventStartDate ASC"""),
            {"bid": business_id}
        ).fetchall()
    except Exception:
        events = []

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

    if events:
        ev_lines = []
        for ev in events:
            status = "Published" if ev.IsPublished else "DRAFT"
            start = str(ev.EventStartDate).split(" ")[0] if ev.EventStartDate else "TBD"
            ev_lines.append(f"  #{ev.EventID} {ev.EventName} — {start} [{status}]")
        lines.append("Upcoming events:\n" + "\n".join(ev_lines))
    else:
        lines.append("Upcoming events: None")

    # Audit findings — so Lavendir can give concrete improvement advice
    try:
        findings = _audit_site(website_id, business_id, db)
        if findings:
            lines.append("")
            lines.append(_format_audit_for_prompt(findings))
    except Exception as e:
        print(f"[Lavendir] audit error: {e}")

    return "\n".join(lines)


# ── Site audit / review ───────────────────────────────────────────

VALID_BLOCK_TYPES = {
    "hero", "about", "content", "content_2col", "content_4col",
    "livestock", "studs", "produce", "meat", "processed_food", "services",
    "marketplace", "gallery", "blog", "events", "contact", "links",
    "testimonials", "testimonial_random", "packages", "divider",
}


def _audit_site(website_id: int, business_id: int, db: Session) -> List[dict]:
    """
    Walk the site and return a prioritized list of findings.

    Each finding: {severity: 'critical'|'high'|'medium'|'low',
                   area: 'site'|'design'|'content'|'seo'|'events',
                   message: str, fix_hint: str}
    """
    findings: List[dict] = []

    try:
        site = db.execute(text("""
            SELECT SiteName, Slug, Tagline, LogoURL, Phone, Email, Address,
                   IsPublished, FacebookURL, InstagramURL, TwitterURL,
                   PrimaryColor, SecondaryColor, AccentColor, BgColor, TextColor
              FROM BusinessWebsite WHERE WebsiteID=:wid
        """), {"wid": website_id}).fetchone()
    except Exception:
        site = None

    if not site:
        findings.append({
            "severity": "critical", "area": "site",
            "message": "No website record found.",
            "fix_hint": "Create a website first in the builder.",
        })
        return findings

    # Site-level
    if not site.IsPublished:
        findings.append({
            "severity": "high", "area": "site",
            "message": "Site is not yet published — visitors can't see it.",
            "fix_hint": "Publish the site once the core pages look right.",
        })
    if not (site.Tagline and site.Tagline.strip()):
        findings.append({
            "severity": "medium", "area": "content",
            "message": "No tagline — sites with a short descriptor convert better.",
            "fix_hint": "Add a 5-10 word tagline describing your farm.",
        })
    if not site.LogoURL:
        findings.append({
            "severity": "medium", "area": "design",
            "message": "No logo uploaded.",
            "fix_hint": "Upload a logo so your header looks branded.",
        })
    if not site.Phone and not site.Email:
        findings.append({
            "severity": "high", "area": "content",
            "message": "No phone or email on the site — visitors can't reach you.",
            "fix_hint": "Add at least one contact method in Settings.",
        })
    if not (site.FacebookURL or site.InstagramURL or site.TwitterURL):
        findings.append({
            "severity": "low", "area": "content",
            "message": "No social-media links — adds trust and discoverability.",
            "fix_hint": "Link your social accounts in Settings.",
        })

    # Pages
    try:
        pages = db.execute(text("""
            SELECT PageID, PageName, Slug, IsHomePage, IsPublished, SortOrder
              FROM BusinessWebPage WHERE WebsiteID=:wid ORDER BY SortOrder
        """), {"wid": website_id}).fetchall()
    except Exception:
        pages = []

    if not pages:
        findings.append({
            "severity": "critical", "area": "site",
            "message": "No pages exist on the site.",
            "fix_hint": "Add at least a homepage, an About page, and a Contact page.",
        })
        return findings

    home_pages = [p for p in pages if p.IsHomePage]
    if not home_pages:
        findings.append({
            "severity": "high", "area": "site",
            "message": "No homepage set — visitors won't have a landing page.",
            "fix_hint": "Mark one page as the homepage.",
        })
    elif len(home_pages) > 1:
        findings.append({
            "severity": "medium", "area": "site",
            "message": f"Multiple homepages set ({len(home_pages)}) — only one should be the home.",
            "fix_hint": "Clear the homepage flag on all but one page.",
        })

    page_names_lower = {(p.PageName or "").lower() for p in pages}
    if not any("about" in n for n in page_names_lower):
        findings.append({
            "severity": "medium", "area": "content",
            "message": "No About page — visitors look here to build trust.",
            "fix_hint": "Add an About page.",
        })
    if not any("contact" in n for n in page_names_lower):
        findings.append({
            "severity": "medium", "area": "content",
            "message": "No Contact page.",
            "fix_hint": "Add a Contact page or include contact info on the home page.",
        })

    # Blocks per page
    try:
        blocks = db.execute(text("""
            SELECT b.BlockID, b.PageID, b.BlockType, b.BlockData, b.SortOrder
              FROM BusinessWebBlock b
              JOIN BusinessWebPage p ON p.PageID = b.PageID
             WHERE p.WebsiteID = :wid
        """), {"wid": website_id}).fetchall()
    except Exception:
        blocks = []

    blocks_by_page: dict = {}
    for b in blocks:
        blocks_by_page.setdefault(b.PageID, []).append(b)

    home_page = home_pages[0] if home_pages else (pages[0] if pages else None)
    if home_page:
        home_blocks = blocks_by_page.get(home_page.PageID, [])
        home_types = {b.BlockType for b in home_blocks}
        if not home_blocks:
            findings.append({
                "severity": "critical", "area": "content",
                "message": f"Homepage \"{home_page.PageName}\" has zero blocks.",
                "fix_hint": "Add at least a hero and an about block to the homepage.",
            })
        else:
            if "hero" not in home_types:
                findings.append({
                    "severity": "high", "area": "content",
                    "message": "Homepage has no hero banner — the first impression is weak.",
                    "fix_hint": "Add a hero block with a headline and farm photo.",
                })
            if "about" not in home_types and "content" not in home_types:
                findings.append({
                    "severity": "medium", "area": "content",
                    "message": "Homepage has no About/Content block explaining who you are.",
                    "fix_hint": "Add an About block telling your farm's story.",
                })
            if len(home_blocks) < 3:
                findings.append({
                    "severity": "medium", "area": "content",
                    "message": f"Homepage only has {len(home_blocks)} block(s) — feels thin.",
                    "fix_hint": "Add 2-3 more blocks (e.g. gallery, events, testimonials).",
                })

    # Empty blocks
    empty_block_count = 0
    hero_no_image = 0
    for b in blocks:
        try:
            data = json.loads(b.BlockData) if b.BlockData else {}
        except Exception:
            data = {}
        if b.BlockType in ("content", "about"):
            if not (data.get("body") or "").strip() and not (data.get("heading") or "").strip():
                empty_block_count += 1
        if b.BlockType == "hero" and not (data.get("image_url") or "").strip():
            hero_no_image += 1

    if empty_block_count:
        findings.append({
            "severity": "medium", "area": "content",
            "message": f"{empty_block_count} content/about block(s) have no heading or body yet.",
            "fix_hint": "Fill in or remove the empty blocks.",
        })
    if hero_no_image:
        findings.append({
            "severity": "medium", "area": "design",
            "message": "Hero block has no background image.",
            "fix_hint": "Upload a farm photo to the hero block.",
        })

    # Events
    try:
        draft_events = db.execute(text("""
            SELECT COUNT(*) FROM OFNEvents
             WHERE BusinessID=:bid AND Deleted=0 AND IsPublished=0
               AND (EventEndDate IS NULL OR EventEndDate >= CAST(GETDATE() AS DATE))
        """), {"bid": business_id}).fetchone()[0]
        pub_events = db.execute(text("""
            SELECT COUNT(*) FROM OFNEvents
             WHERE BusinessID=:bid AND Deleted=0 AND IsPublished=1
               AND (EventEndDate IS NULL OR EventEndDate >= CAST(GETDATE() AS DATE))
        """), {"bid": business_id}).fetchone()[0]
    except Exception:
        draft_events, pub_events = 0, 0

    if draft_events > 0:
        findings.append({
            "severity": "medium", "area": "events",
            "message": f"{draft_events} upcoming event(s) are still in draft and not visible to visitors.",
            "fix_hint": "Publish the drafts so they show up on your site and in the network feed.",
        })
    has_events_block = any(b.BlockType == "events" for b in blocks)
    if pub_events > 0 and not has_events_block:
        findings.append({
            "severity": "medium", "area": "events",
            "message": f"You have {pub_events} published event(s) but no Events block on your site.",
            "fix_hint": "Add an Upcoming Events block to your homepage.",
        })

    # SEO — missing metadata
    try:
        seo_row = db.execute(text("""
            SELECT MetaTitle, MetaDescription, OgImage
              FROM BusinessWebsite WHERE WebsiteID=:wid
        """), {"wid": website_id}).fetchone()
    except Exception:
        seo_row = None
    if seo_row:
        if not (seo_row.MetaTitle or "").strip():
            findings.append({
                "severity": "low", "area": "seo",
                "message": "No SEO meta title set — Google will use the site name as a fallback.",
                "fix_hint": "Set a 50-60 character meta title in Settings.",
            })
        if not (seo_row.MetaDescription or "").strip():
            findings.append({
                "severity": "low", "area": "seo",
                "message": "No SEO meta description — Google will auto-generate one (usually poorly).",
                "fix_hint": "Write a 150-160 character meta description in Settings.",
            })

    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    findings.sort(key=lambda f: severity_order.get(f["severity"], 9))
    return findings


def _format_audit_for_prompt(findings: List[dict]) -> str:
    if not findings:
        return "AUDIT: No issues found — the site looks solid."
    lines = ["AUDIT FINDINGS (sorted by priority):"]
    for f in findings[:15]:
        lines.append(f"  [{f['severity'].upper()}] ({f['area']}) {f['message']}")
        if f.get("fix_hint"):
            lines.append(f"      → Fix: {f['fix_hint']}")
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
        "name": "list_page_templates",
        "description": "List page templates available for this business's type. Call this before add_page_from_template to know which template_key values are valid and which pages are relevant for the user's BusinessType. For Agricultural associations (BusinessTypeID=1) this returns membership, registrar, convention, advocacy, co-op, etc. templates.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "add_page_from_template",
        "description": "Create a new page pre-populated with seeded blocks from a named template. Use when the user asks for a specific kind of page (e.g. 'add a membership page', 'set up a registry search', 'I need a board of directors page'). Prefer this over add_page when a matching template exists — it seeds the page with sensible default content the user can then edit.",
        "parameters": {
            "type": "object",
            "properties": {
                "template_key": {"type": "string", "description": "The key of the template to apply (e.g. 'assoc_join_renew', 'assoc_board_of_directors'). Call list_page_templates first if unsure."},
                "page_name":    {"type": "string", "description": "Optional override for the page name. Defaults to the template's name."},
                "slug":         {"type": "string", "description": "Optional URL slug. Defaults to the template's slug."},
            },
            "required": ["template_key"]
        }
    },
    {
        "name": "add_pages_bulk",
        "description": "Apply a batch of templates to the site in one call — great for seeding a fresh site with a starter pack (e.g. Home + About + Contact + Join + Events). Skips invalid or gated keys rather than failing. Use when the user asks for a 'starter pack', 'the essentials', or to 'set up the basic pages'.",
        "parameters": {
            "type": "object",
            "properties": {
                "template_keys": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of template keys to apply, in order. Invalid or gated keys are skipped silently.",
                },
            },
            "required": ["template_keys"]
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
    {
        "name": "add_events_block",
        "description": "Add an Upcoming Events block to the homepage (or a specific page) that displays the user's published events. Use when the user wants to promote their farm events, clinics, auctions, tours, or workshops on their site.",
        "parameters": {
            "type": "object",
            "properties": {
                "heading":    {"type": "string", "description": "Section heading to display (e.g. 'Upcoming Events', 'Farm Tours & Clinics')"},
                "layout":     {"type": "string", "description": "'cards' or 'list' — cards is more visual, list is compact"},
                "max_items":  {"type": "integer", "description": "Maximum number of events to show (default 6, range 1-50)"},
                "page_name":  {"type": "string", "description": "Which page to add it to. Defaults to the homepage."},
            },
            "required": []
        }
    },
    {
        "name": "publish_event",
        "description": "Publish one of the user's draft events so it appears on the site and in the public events feed. Use when the user asks to publish an event, make an event live, or push an event out.",
        "parameters": {
            "type": "object",
            "properties": {
                "event_id":    {"type": "integer", "description": "The EventID to publish. If the user names an event instead, match it by title."},
                "event_title": {"type": "string", "description": "The event's name. Used to look up the EventID if event_id is not known."},
            },
            "required": []
        }
    },
    {
        "name": "add_block",
        "description": "Add a content block to a page. Use for common improvements: adding a hero banner, about section, contact block, gallery, events block, blog feed, testimonials, etc. Valid types: hero, about, content, livestock, studs, produce, meat, processed_food, services, marketplace, gallery, blog, events, contact, links, testimonials, testimonial_random, packages, divider.",
        "parameters": {
            "type": "object",
            "properties": {
                "block_type": {"type": "string", "description": "The kind of block to add. See list above."},
                "page_name":  {"type": "string", "description": "Which page to add it to. Defaults to the homepage."},
                "heading":    {"type": "string", "description": "Heading text for blocks that have one (hero headline, about heading, content heading, section title)."},
                "body":       {"type": "string", "description": "Body text for about/content blocks, or sub-text for hero."},
                "image_url":  {"type": "string", "description": "Image URL for blocks that show an image (hero, about, content)."},
            },
            "required": ["block_type"]
        }
    },
    {
        "name": "update_block",
        "description": "Edit fields of an existing block — change a heading, rewrite the body text, swap an image, update CTA. Use when improving existing copy found in the audit.",
        "parameters": {
            "type": "object",
            "properties": {
                "block_id":  {"type": "integer", "description": "The BlockID of the block to update."},
                "heading":   {"type": "string", "description": "New heading text."},
                "body":      {"type": "string", "description": "New body text."},
                "image_url": {"type": "string", "description": "New image URL."},
                "cta_text":  {"type": "string", "description": "New call-to-action button text."},
                "cta_link":  {"type": "string", "description": "New call-to-action link/URL."},
            },
            "required": ["block_id"]
        }
    },
    {
        "name": "review_site",
        "description": "Run a full audit of the website and return a prioritized list of improvement findings. Use when the user asks you to review, audit, critique, or improve their site — or asks 'what should I do next?'.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "scrape_website",
        "description": "Scrape any public website and report what you found — platform/CMS, color palette, fonts, logo, hero content, and structure. Read-only; use when the user asks what a site looks like, to analyze a URL, or to gather design DNA before making changes. Every scrape also teaches the shared learning system so future scrapes of similar sites are smarter.",
        "parameters": {
            "type": "object",
            "properties": {
                "url":           {"type": "string", "description": "The full URL to scrape (https://…)."},
                "deep":          {"type": "boolean", "description": "If true, also run the browser-based capture for computed styles + screenshot. Slower but more accurate. Default false."},
            },
            "required": ["url"]
        }
    },
    {
        "name": "review_competitor_site",
        "description": "Scrape a competitor/inspiration URL and narrate what makes it work — design tokens, copy voice, layout choices, and concrete takeaways the user can apply to their own site. Read-only.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Competitor or inspiration URL."},
            },
            "required": ["url"]
        }
    },
    {
        "name": "generate_hero_image",
        "description": "Generate a photorealistic hero image for the user's website using AI. Use when the user asks for a new hero image, banner, or cover photo — or when you suggest one during a review. The image is generated at chat time and shown in the confirmation so the user can see it BEFORE it's applied to their site.",
        "parameters": {
            "type": "object",
            "properties": {
                "description": {"type": "string", "description": "What the image should show, in natural language (e.g. 'a golden hour shot of grass-fed cattle on rolling hills')."},
                "style":       {"type": "string", "description": "'photo' (default), 'illustration', 'watercolor', or 'cinematic'."},
                "page_name":   {"type": "string", "description": "Which page to put it on. Defaults to the homepage."},
                "apply_to":    {"type": "string", "description": "'hero_block' (default) replaces the hero image on the page; 'header' sets the site-wide header image."},
            },
            "required": ["description"]
        }
    },
    {
        "name": "preview_design_change",
        "description": "Render a visual preview of a proposed design change — shows the new colors, fonts, and heading styles in a mockup card the user can see before applying. Read-only; returns a preview URL.",
        "parameters": {
            "type": "object",
            "properties": {
                "primary_color":   {"type": "string"},
                "secondary_color": {"type": "string"},
                "accent_color":    {"type": "string"},
                "bg_color":        {"type": "string"},
                "text_color":      {"type": "string"},
                "font_family":     {"type": "string"},
                "label":           {"type": "string", "description": "Short name for the design direction (e.g. 'Farmhouse Modern')."},
            },
            "required": []
        }
    },
    {
        "name": "import_from_website",
        "description": "Scrape another website and import its hero headline, about copy, design colors, and gallery images onto one of the user's pages. Use when the user says things like 'pull in content from my old site' or 'import from this URL'. Requires user confirmation before writing.",
        "parameters": {
            "type": "object",
            "properties": {
                "url":       {"type": "string", "description": "Source URL to import from."},
                "page_name": {"type": "string", "description": "Which page on the user's site to import into. Defaults to the homepage."},
                "include":   {"type": "string", "description": "Comma-separated subset of 'hero,about,gallery,design'. Default 'hero,about,design'."},
            },
            "required": ["url"]
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
    if action == "list_page_templates":
        return "Look up page templates available for your business type"
    if action == "add_page_from_template":
        key = params.get("template_key")
        name = params.get("page_name")
        return f"Create a new page from template '{key}'" + (f" named \"{name}\"" if name else "")
    if action == "add_pages_bulk":
        keys = params.get("template_keys") or []
        if len(keys) <= 5:
            return f"Apply {len(keys)} templates: {', '.join(keys)}"
        return f"Apply {len(keys)} templates (starter pack)"
    if action == "publish_site":
        return "Publish your website" if params.get("publish") else "Unpublish your website"
    if action == "add_events_block":
        heading = params.get("heading") or "Upcoming Events"
        page    = params.get("page_name") or "your homepage"
        layout  = params.get("layout") or "cards"
        return f"Add an \"{heading}\" events block ({layout} layout) to {page}"
    if action == "publish_event":
        label = params.get("event_title") or f"event #{params.get('event_id')}"
        return f"Publish event: {label}"
    if action == "add_block":
        bt = params.get("block_type") or "block"
        page = params.get("page_name") or "your homepage"
        return f"Add a {bt} block to {page}"
    if action == "update_block":
        fields = [k for k in ("heading", "body", "image_url", "cta_text", "cta_link") if params.get(k)]
        return f"Update block #{params.get('block_id')} ({', '.join(fields) or 'fields'})"
    if action == "review_site":
        return "Run a full audit of your site and report findings"
    if action == "scrape_website":
        return f"Scrape {params.get('url')} and report what I find"
    if action == "review_competitor_site":
        return f"Analyze {params.get('url')} for design & copy takeaways"
    if action == "import_from_website":
        page = params.get("page_name") or "your homepage"
        inc  = params.get("include") or "hero,about,design"
        return f"Import from {params.get('url')} → {page} ({inc})"
    if action == "generate_hero_image":
        where = "site header" if params.get("apply_to") == "header" else f"hero on {params.get('page_name') or 'your homepage'}"
        return f"Use the generated image as the {where}"
    if action == "preview_design_change":
        return f"Preview the \"{params.get('label') or 'new'}\" design direction"
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

    if action == "list_page_templates":
        import page_templates
        biz = db.query(models.Business).filter(models.Business.BusinessID == business_id).first()
        bt_id = biz.BusinessTypeID if biz else None
        tpls = page_templates.list_templates(bt_id)
        if not tpls:
            return f"No page templates available for BusinessTypeID {bt_id}."
        by_section = {}
        for t in tpls:
            by_section.setdefault(t.get("section", "Other"), []).append(t)
        lines = [f"Found {len(tpls)} templates for BusinessTypeID {bt_id}:"]
        for section in sorted(by_section.keys()):
            lines.append(f"\n{section}:")
            for t in by_section[section]:
                lines.append(f"  - {t['key']} — {t['name']}")
        return "\n".join(lines)

    if action == "add_page_from_template":
        import re, json as _json
        import page_templates
        key = params.get("template_key")
        tpl = page_templates.get_template(key) if key else None
        if not tpl:
            return f"Template '{key}' not found. Call list_page_templates to see available keys."
        gate = tpl.get("business_type_ids")
        if gate is not None:
            biz = db.query(models.Business).filter(models.Business.BusinessID == business_id).first()
            if not biz or biz.BusinessTypeID not in gate:
                return f"Template '{key}' is not available for this business type."
        page_name = (params.get("page_name") or tpl.get("name") or "New Page").strip()
        base_slug = params.get("slug") or tpl.get("slug") or page_name
        base_slug = re.sub(r'[^a-z0-9-]+', '-', base_slug.lower()).strip('-') or "page"
        slug = base_slug
        i = 2
        while db.query(models.BusinessWebPage).filter(
            models.BusinessWebPage.WebsiteID == website_id,
            models.BusinessWebPage.Slug == slug,
        ).first():
            slug = f"{base_slug}-{i}"
            i += 1
        last = db.query(models.BusinessWebPage).filter(
            models.BusinessWebPage.WebsiteID == website_id
        ).order_by(models.BusinessWebPage.SortOrder.desc()).first()
        next_order = (last.SortOrder + 1) if last and last.SortOrder is not None else 0
        page = models.BusinessWebPage(
            WebsiteID=website_id, BusinessID=business_id,
            PageName=page_name, Slug=slug,
            PageTitle=tpl.get("page_title"),
            MetaDescription=tpl.get("meta_description"),
            SortOrder=next_order, IsPublished=True, IsHomePage=False,
            IsNavHeading=False,
            CreatedAt=dt.utcnow(), UpdatedAt=dt.utcnow(),
        )
        db.add(page); db.commit(); db.refresh(page)
        blocks = tpl.get("default_blocks", []) or []
        for idx, b in enumerate(blocks):
            db.add(models.BusinessWebBlock(
                PageID=page.PageID,
                BlockType=b.get("block_type", "content"),
                BlockData=_json.dumps(b.get("block_data", {})),
                SortOrder=idx,
                CreatedAt=dt.utcnow(), UpdatedAt=dt.utcnow(),
            ))
        db.commit()
        return f"Page \"{page_name}\" created from template '{key}' with {len(blocks)} seeded block(s)."

    if action == "add_pages_bulk":
        import re, json as _json
        import page_templates
        keys = params.get("template_keys") or []
        biz = db.query(models.Business).filter(models.Business.BusinessID == business_id).first()
        bt_id = biz.BusinessTypeID if biz else None
        last = db.query(models.BusinessWebPage).filter(
            models.BusinessWebPage.WebsiteID == website_id
        ).order_by(models.BusinessWebPage.SortOrder.desc()).first()
        next_order = (last.SortOrder + 1) if last and last.SortOrder is not None else 0
        created, skipped = [], []
        for key in keys:
            tpl = page_templates.get_template(key)
            if not tpl:
                skipped.append(f"{key} (not found)"); continue
            gate = tpl.get("business_type_ids")
            if gate is not None and bt_id not in gate:
                skipped.append(f"{key} (not available for this business type)"); continue
            page_name = (tpl.get("name") or "New Page").strip()
            base_slug = re.sub(r'[^a-z0-9-]+', '-', (tpl.get("slug") or page_name).lower()).strip('-') or "page"
            slug = base_slug
            i = 2
            while db.query(models.BusinessWebPage).filter(
                models.BusinessWebPage.WebsiteID == website_id,
                models.BusinessWebPage.Slug == slug,
            ).first():
                slug = f"{base_slug}-{i}"
                i += 1
            page = models.BusinessWebPage(
                WebsiteID=website_id, BusinessID=business_id,
                PageName=page_name, Slug=slug,
                PageTitle=tpl.get("page_title"),
                MetaDescription=tpl.get("meta_description"),
                SortOrder=next_order, IsPublished=True, IsHomePage=False,
                IsNavHeading=False,
                CreatedAt=dt.utcnow(), UpdatedAt=dt.utcnow(),
            )
            db.add(page); db.commit(); db.refresh(page)
            next_order += 1
            for idx, b in enumerate(tpl.get("default_blocks", []) or []):
                db.add(models.BusinessWebBlock(
                    PageID=page.PageID,
                    BlockType=b.get("block_type", "content"),
                    BlockData=_json.dumps(b.get("block_data", {})),
                    SortOrder=idx,
                    CreatedAt=dt.utcnow(), UpdatedAt=dt.utcnow(),
                ))
            db.commit()
            created.append(page_name)
        parts = [f"Created {len(created)} page(s): {', '.join(created)}" if created else "No pages created."]
        if skipped:
            parts.append(f"Skipped: {'; '.join(skipped)}")
        return " ".join(parts)

    if action == "publish_site":
        site = db.query(models.BusinessWebsite).filter(models.BusinessWebsite.WebsiteID == website_id).first()
        if not site:
            return "Site not found."
        site.IsPublished = params.get("publish", True)
        site.UpdatedAt = dt.utcnow()
        db.commit()
        return "Site published." if site.IsPublished else "Site unpublished."

    if action == "add_events_block":
        page_name = params.get("page_name")
        page_row = None
        if page_name:
            page_row = db.execute(
                text("SELECT PageID FROM BusinessWebPage WHERE WebsiteID=:wid AND PageName=:pn"),
                {"wid": website_id, "pn": page_name},
            ).fetchone()
        if not page_row:
            page_row = db.execute(
                text("SELECT TOP 1 PageID FROM BusinessWebPage WHERE WebsiteID=:wid AND IsHomePage=1"),
                {"wid": website_id},
            ).fetchone()
        if not page_row:
            page_row = db.execute(
                text("SELECT TOP 1 PageID FROM BusinessWebPage WHERE WebsiteID=:wid ORDER BY SortOrder"),
                {"wid": website_id},
            ).fetchone()
        if not page_row:
            return "No page found to add the events block to. Add a page first."
        page_id = page_row[0]

        max_sort = db.execute(
            text("SELECT ISNULL(MAX(SortOrder), 0) FROM BusinessWebBlock WHERE PageID=:pid"),
            {"pid": page_id},
        ).fetchone()[0]
        block_data = {
            "heading":       params.get("heading") or "Upcoming Events",
            "heading_style": "h2",
            "layout":        params.get("layout") if params.get("layout") in ("cards", "list") else "cards",
            "max_items":     int(params.get("max_items") or 6),
        }
        block = models.BusinessWebBlock(
            PageID=page_id, BlockType="events",
            BlockData=json.dumps(block_data),
            SortOrder=int(max_sort) + 10,
            CreatedAt=dt.utcnow(), UpdatedAt=dt.utcnow(),
        )
        db.add(block); db.commit()
        return f"Upcoming Events block added to your {'homepage' if not page_name else page_name}."

    if action == "publish_event":
        event_id = params.get("event_id")
        if not event_id and params.get("event_title"):
            match = db.execute(
                text("""SELECT TOP 1 EventID FROM OFNEvents
                         WHERE BusinessID=:bid AND Deleted=0 AND EventName LIKE :nm
                         ORDER BY EventStartDate DESC"""),
                {"bid": business_id, "nm": f"%{params['event_title']}%"},
            ).fetchone()
            if match:
                event_id = match[0]
        if not event_id:
            return "I couldn't find that event. Can you tell me its name or ID?"
        row = db.execute(
            text("SELECT EventName, BusinessID FROM OFNEvents WHERE EventID=:eid AND Deleted=0"),
            {"eid": int(event_id)},
        ).fetchone()
        if not row:
            return f"Event #{event_id} not found."
        if int(row.BusinessID) != int(business_id):
            return "That event belongs to a different business — I can only publish events for this account."
        db.execute(
            text("UPDATE OFNEvents SET IsPublished=1 WHERE EventID=:eid"),
            {"eid": int(event_id)},
        )
        db.commit()
        return f"Event \"{row.EventName}\" is now published."

    if action == "add_block":
        block_type = (params.get("block_type") or "").strip().lower()
        if block_type not in VALID_BLOCK_TYPES:
            return f"'{block_type}' isn't a valid block type. Try hero, about, content, events, blog, contact, gallery, or testimonials."
        page_name = params.get("page_name")
        page_row = None
        if page_name:
            page_row = db.execute(
                text("SELECT PageID FROM BusinessWebPage WHERE WebsiteID=:wid AND PageName=:pn"),
                {"wid": website_id, "pn": page_name},
            ).fetchone()
        if not page_row:
            page_row = db.execute(
                text("SELECT TOP 1 PageID FROM BusinessWebPage WHERE WebsiteID=:wid AND IsHomePage=1"),
                {"wid": website_id},
            ).fetchone()
        if not page_row:
            page_row = db.execute(
                text("SELECT TOP 1 PageID FROM BusinessWebPage WHERE WebsiteID=:wid ORDER BY SortOrder"),
                {"wid": website_id},
            ).fetchone()
        if not page_row:
            return "No page found. Add a page first."
        page_id = page_row[0]

        # Seed sensible defaults per block type
        data = {}
        heading   = params.get("heading")
        body      = params.get("body")
        image_url = params.get("image_url")
        if block_type == "hero":
            data = {
                "headline": heading or "Welcome to Our Farm",
                "subtext":  body or "Fresh, local, and sustainably grown.",
                "image_url": image_url or "",
                "cta_text": "Learn More", "cta_link": "#about",
                "overlay": True, "align": "center",
            }
        elif block_type in ("about", "content"):
            data = {
                "heading": heading or ("About Us" if block_type == "about" else ""),
                "body":    body or "",
                "image_url": image_url or "",
                "image_position": "right",
            }
        elif block_type == "events":
            data = {"heading": heading or "Upcoming Events", "heading_style": "h2",
                    "layout": "cards", "max_items": 6}
        elif block_type == "blog":
            data = {"heading": heading or "From the Blog", "heading_style": "h2", "max_items": 3}
        elif block_type == "contact":
            data = {"heading": heading or "Get in Touch"}
        elif block_type == "gallery":
            data = {"heading": heading or "Photo Gallery", "max_items": 12}
        else:
            data = {"heading": heading or "", "body": body or "", "image_url": image_url or ""}

        max_sort = db.execute(
            text("SELECT ISNULL(MAX(SortOrder), 0) FROM BusinessWebBlock WHERE PageID=:pid"),
            {"pid": page_id},
        ).fetchone()[0]
        block = models.BusinessWebBlock(
            PageID=page_id, BlockType=block_type,
            BlockData=json.dumps(data),
            SortOrder=int(max_sort) + 10,
            CreatedAt=dt.utcnow(), UpdatedAt=dt.utcnow(),
        )
        db.add(block); db.commit()
        return f"{block_type.title()} block added to your {'homepage' if not page_name else page_name}."

    if action == "update_block":
        block_id = params.get("block_id")
        if not block_id:
            return "block_id is required."
        block = db.query(models.BusinessWebBlock).filter(
            models.BusinessWebBlock.BlockID == int(block_id)
        ).first()
        if not block:
            return f"Block #{block_id} not found."
        try:
            data = json.loads(block.BlockData) if block.BlockData else {}
        except Exception:
            data = {}
        changed = []
        # Hero uses 'headline'/'subtext' — map heading/body accordingly
        if block.BlockType == "hero":
            if params.get("heading"):
                data["headline"] = params["heading"]; changed.append("headline")
            if params.get("body"):
                data["subtext"] = params["body"]; changed.append("subtext")
        else:
            if params.get("heading") is not None:
                data["heading"] = params["heading"]; changed.append("heading")
            if params.get("body") is not None:
                data["body"] = params["body"]; changed.append("body")
        if params.get("image_url") is not None:
            data["image_url"] = params["image_url"]; changed.append("image")
        if params.get("cta_text") is not None:
            data["cta_text"] = params["cta_text"]; changed.append("cta_text")
        if params.get("cta_link") is not None:
            data["cta_link"] = params["cta_link"]; changed.append("cta_link")
        block.BlockData = json.dumps(data)
        block.UpdatedAt = dt.utcnow()
        db.commit()
        return f"Block #{block_id} updated ({', '.join(changed) or 'no changes'})."

    if action == "review_site":
        findings = _audit_site(website_id, business_id, db)
        if not findings:
            return "I ran a full audit and didn't find any issues — your site looks solid."
        # Format as a readable bulleted list the LLM can narrate
        lines = ["Here's what I found (in priority order):"]
        for f in findings[:12]:
            sev = f["severity"].upper()
            lines.append(f"• [{sev}] {f['message']}")
            if f.get("fix_hint"):
                lines.append(f"    → {f['fix_hint']}")
        return "\n".join(lines)

    if action == "import_from_website":
        return _execute_import_from_website(params, website_id, business_id, db)

    if action == "generate_hero_image":
        return _execute_apply_hero_image(params, website_id, business_id, db)

    return "Unknown action."


def _execute_apply_hero_image(params: dict, website_id: int, business_id: int, db: Session) -> str:
    """Apply a pre-generated hero image URL (stored in params.image_url) to a hero block or site header."""
    import models
    from datetime import datetime as dt_now

    image_url = (params.get("image_url") or "").strip()
    if not image_url:
        return "No image was generated — I couldn't apply anything."
    apply_to = (params.get("apply_to") or "hero_block").lower()

    if apply_to == "header":
        site = db.query(models.BusinessWebsite).filter(
            models.BusinessWebsite.WebsiteID == website_id
        ).first()
        if not site:
            return "Site not found."
        if hasattr(site, "BgImageURL"):
            site.BgImageURL = image_url
        site.UpdatedAt = dt_now.utcnow()
        db.commit()
        return "Header image applied."

    # Default: apply to the hero block on the target page
    page_name = params.get("page_name")
    page_row = None
    if page_name:
        page_row = db.execute(
            text("SELECT PageID FROM BusinessWebPage WHERE WebsiteID=:wid AND PageName=:pn"),
            {"wid": website_id, "pn": page_name},
        ).fetchone()
    if not page_row:
        page_row = db.execute(
            text("SELECT TOP 1 PageID FROM BusinessWebPage WHERE WebsiteID=:wid AND IsHomePage=1"),
            {"wid": website_id},
        ).fetchone()
    if not page_row:
        return "No page found. Add a page first."
    page_id = page_row[0]

    hero = db.execute(
        text("SELECT TOP 1 BlockID, BlockData FROM BusinessWebBlock "
             "WHERE PageID=:pid AND BlockType='hero' ORDER BY SortOrder"),
        {"pid": page_id},
    ).fetchone()

    if hero:
        try:
            data = json.loads(hero.BlockData) if hero.BlockData else {}
        except Exception:
            data = {}
        data["image_url"] = image_url
        db.execute(
            text("UPDATE BusinessWebBlock SET BlockData=:d, UpdatedAt=:u WHERE BlockID=:bid"),
            {"d": json.dumps(data), "u": dt_now.utcnow(), "bid": hero.BlockID},
        )
        db.commit()
        return "Hero image swapped."

    # No hero yet — create one
    max_sort = db.execute(
        text("SELECT ISNULL(MAX(SortOrder), 0) FROM BusinessWebBlock WHERE PageID=:pid"),
        {"pid": page_id},
    ).fetchone()[0]
    db.add(models.BusinessWebBlock(
        PageID=page_id, BlockType="hero",
        BlockData=json.dumps({
            "headline": "", "subtext": "",
            "image_url": image_url,
            "cta_text": "Learn More", "cta_link": "#about",
            "overlay": True, "align": "center",
        }),
        SortOrder=int(max_sort) + 10,
        CreatedAt=dt_now.utcnow(), UpdatedAt=dt_now.utcnow(),
    ))
    db.commit()
    return "New hero block created with the generated image."


def _build_hero_prompt(description: str, style: Optional[str]) -> str:
    style = (style or "photo").lower()
    style_map = {
        "photo":        "professional photograph, natural lighting, cinematic composition, 4k, sharp focus",
        "illustration": "hand-drawn illustration, warm color palette, organic linework",
        "watercolor":   "soft watercolor painting, flowing brushwork, gentle pastel tones",
        "cinematic":    "cinematic wide shot, dramatic golden-hour lighting, depth of field, shallow focus",
    }
    tail = style_map.get(style, style_map["photo"])
    return f"Website hero banner: {description}. {tail}. 16:9 composition, no text overlays, no logos, farm/agricultural context."


# ── Preview token store (Redis when available; in-memory fallback) ─

_PREVIEW_STORE: dict = {}
_PREVIEW_TTL_SEC = 30 * 60
_PREVIEW_KEY_PREFIX = "lavendir:preview:"


def _preview_redis():
    """Return a text-decode Redis client, or None if unavailable."""
    try:
        from saige.redis_client import get_redis_client
        return get_redis_client(decode_responses=True)
    except Exception:
        return None


def _store_preview(payload: dict) -> str:
    import uuid, time as _t, json as _j
    token = uuid.uuid4().hex
    client = _preview_redis()
    if client is not None:
        try:
            client.setex(
                _PREVIEW_KEY_PREFIX + token,
                _PREVIEW_TTL_SEC,
                _j.dumps(payload, default=str),
            )
            return token
        except Exception:
            pass  # fall through to in-memory
    # In-memory fallback — prune stale first
    now = _t.time()
    for k in list(_PREVIEW_STORE.keys()):
        if _PREVIEW_STORE[k].get("_exp", 0) < now:
            _PREVIEW_STORE.pop(k, None)
    payload["_exp"] = now + _PREVIEW_TTL_SEC
    _PREVIEW_STORE[token] = payload
    return token


def _load_preview(token: str) -> Optional[dict]:
    import json as _j
    client = _preview_redis()
    if client is not None:
        try:
            raw = client.get(_PREVIEW_KEY_PREFIX + token)
            if raw:
                return _j.loads(raw)
        except Exception:
            pass
    return _PREVIEW_STORE.get(token)


# ── Last-scrape memory (per website_id; lets next turn reference "that site") ──

_LAST_SCRAPE_STORE: dict = {}
_LAST_SCRAPE_TTL_SEC = 30 * 60
_LAST_SCRAPE_KEY_PREFIX = "lavendir:lastscrape:"


def _store_last_scrape(website_id: int, data: dict) -> None:
    import json as _j, time as _t
    # Keep payload small — only what's useful to reference later
    trimmed = {
        "url": data.get("url"),
        "platform": data.get("platform"),
        "designTokens": data.get("designTokens"),
        "layoutPatterns": data.get("layoutPatterns"),
        "summary": data.get("summary"),
        "stored_at": _t.time(),
    }
    client = _preview_redis()
    if client is not None:
        try:
            client.setex(
                f"{_LAST_SCRAPE_KEY_PREFIX}{website_id}",
                _LAST_SCRAPE_TTL_SEC,
                _j.dumps(trimmed, default=str),
            )
            return
        except Exception:
            pass
    trimmed["_exp"] = _t.time() + _LAST_SCRAPE_TTL_SEC
    _LAST_SCRAPE_STORE[website_id] = trimmed


def _load_last_scrape(website_id: int) -> Optional[dict]:
    import json as _j, time as _t
    client = _preview_redis()
    if client is not None:
        try:
            raw = client.get(f"{_LAST_SCRAPE_KEY_PREFIX}{website_id}")
            if raw:
                return _j.loads(raw)
        except Exception:
            pass
    entry = _LAST_SCRAPE_STORE.get(website_id)
    if entry and entry.get("_exp", 0) > _t.time():
        return entry
    return None


def _clear_last_scrape(website_id: int) -> None:
    client = _preview_redis()
    if client is not None:
        try:
            client.delete(f"{_LAST_SCRAPE_KEY_PREFIX}{website_id}")
        except Exception:
            pass
    _LAST_SCRAPE_STORE.pop(website_id, None)


def _last_scrape_meta(website_id: int) -> Optional[dict]:
    """Tiny dict suitable for chat response / chip UI. None if nothing remembered."""
    entry = _load_last_scrape(website_id)
    if not entry:
        return None
    platform = entry.get("platform") or {}
    return {
        "url": entry.get("url"),
        "platform_name": platform.get("platform_name"),
        "stored_at": entry.get("stored_at"),
        "ttl_sec": _LAST_SCRAPE_TTL_SEC,
    }


def _format_last_scrape(entry: dict) -> str:
    """Short prompt snippet describing the last scraped site."""
    if not entry:
        return ""
    url = entry.get("url") or "that site"
    platform = entry.get("platform") or {}
    tokens = entry.get("designTokens") or {}
    patterns = entry.get("layoutPatterns") or {}
    lines = [f"Last scraped site: {url}"]
    if platform.get("platform_name"):
        lines.append(f"  platform: {platform.get('platform_name')}")
    if tokens.get("colors"):
        cs = tokens["colors"]
        if isinstance(cs, list) and cs:
            lines.append(f"  colors: {', '.join(str(c) for c in cs[:5])}")
    if tokens.get("fonts"):
        fs = tokens["fonts"]
        if isinstance(fs, list) and fs:
            lines.append(f"  fonts: {', '.join(str(f) for f in fs[:3])}")
    if patterns.get("has_hero"):
        lines.append("  has hero section")
    if patterns.get("has_blog"):
        lines.append("  has blog")
    lines.append('If the user says "that site", "import from there", or similar, treat this as the target.')
    return "\n".join(lines)


def _render_design_preview_html(p: dict) -> str:
    primary   = p.get("primary_color")   or "#3D6B34"
    secondary = p.get("secondary_color") or "#819360"
    accent    = p.get("accent_color")    or "#FFC567"
    bg        = p.get("bg_color")        or "#FFFFFF"
    text_c    = p.get("text_color")      or "#111827"
    font      = p.get("font_family")     or "Inter, sans-serif"
    label     = p.get("label")           or "Design preview"
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{label}</title>
<style>
  body {{ margin:0; font-family:{font}; background:{bg}; color:{text_c}; }}
  .nav {{ background:{primary}; color:#fff; padding:16px 24px; font-weight:600; }}
  .hero {{ padding:64px 32px; background:linear-gradient(135deg,{primary}22,{accent}33); }}
  .hero h1 {{ margin:0 0 12px 0; font-size:44px; }}
  .cta {{ display:inline-block; margin-top:12px; background:{accent}; color:#111; padding:12px 20px; border-radius:6px; font-weight:600; }}
  .section {{ padding:32px; }}
  .swatches {{ display:flex; gap:12px; }}
  .sw {{ flex:1; padding:16px; border-radius:6px; color:#fff; font-size:12px; }}
  .foot {{ background:{secondary}; color:#fff; padding:24px; font-size:13px; }}
</style></head><body>
  <div class="nav">Your Farm · Home · About · Shop · Contact</div>
  <div class="hero">
    <h1>Welcome to your farm</h1>
    <p>This is how your hero headline will read with the <b>{label}</b> direction.</p>
    <span class="cta">Shop the farm →</span>
  </div>
  <div class="section">
    <h2>Section heading</h2>
    <p>Body copy sits on <code>{bg}</code> in <code>{text_c}</code>. Font: {font}.</p>
    <div class="swatches">
      <div class="sw" style="background:{primary}">primary {primary}</div>
      <div class="sw" style="background:{secondary}">secondary {secondary}</div>
      <div class="sw" style="background:{accent};color:#111">accent {accent}</div>
    </div>
  </div>
  <div class="foot">Footer · © Your Farm</div>
</body></html>"""


# ── Scraper-backed helpers ────────────────────────────────────────

def _run_scrape(url: str, *, deep: bool = False) -> dict:
    """Run the Lavendir scraper from a sync context. Returns {} on failure."""
    try:
        from scrapers.lavendir_scraper import scrape as _scrape_async
    except Exception as e:
        return {"error": f"Scraper unavailable: {e}"}
    try:
        return asyncio.run(_scrape_async(url, use_playwright=bool(deep), learn=True))
    except RuntimeError:
        # Fall back to a fresh loop if we're already inside one
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_scrape_async(url, use_playwright=bool(deep), learn=True))
        finally:
            loop.close()
    except Exception as e:
        return {"error": f"Scrape failed: {e}"}


def _summarize_scrape(data: dict, *, competitor: bool = False) -> str:
    if not data or data.get("error"):
        return f"I couldn't scrape that site — {data.get('error', 'unknown error')}"
    platform = data.get("platform") or {}
    dt       = data.get("designTokens") or {}
    lp       = data.get("layoutPatterns") or {}
    stats    = data.get("stats") or {}
    title    = data.get("pageTitle") or ""
    pname    = platform.get("platform_name") or platform.get("platform_key") or "unknown"
    conf     = platform.get("confidence")
    colors   = ", ".join(
        c for c in [dt.get("navBgColor"), dt.get("pageBgColor"), dt.get("accentColor")] if c
    ) or "—"
    fonts    = dt.get("bodyFont") or dt.get("headingFont") or "—"
    sections = ", ".join(lp.get("sections") or []) or "—"
    lines = [
        f"**{title or data.get('url')}**",
        f"• Platform: {pname}" + (f" (confidence {conf})" if conf else ""),
        f"• Colors: {colors}",
        f"• Fonts: {fonts}",
        f"• Sections detected: {sections}",
        f"• Stats: {stats.get('headings', 0)} headings, {stats.get('paragraphs', 0)} paragraphs, "
        f"{stats.get('images', 0)} images",
    ]
    if competitor:
        headline = (data.get("headings") or [{}])[0].get("text") if data.get("headings") else ""
        if headline:
            lines.append(f"• Hero headline voice: \"{headline}\"")
        lines.append("")
        lines.append("Takeaways you can apply:")
        if dt.get("accentColor"):
            lines.append(f"  → Their accent color ({dt['accentColor']}) reads well over their page background — "
                         f"want me to try a similar palette on your site?")
        if "hero" in (lp.get("sections") or []):
            lines.append("  → They lead with a hero banner. If your homepage doesn't have one, I can add it.")
        if "testimonials" in (lp.get("sections") or []):
            lines.append("  → They use testimonials for social proof — I can add a testimonials block for you.")
    return "\n".join(lines)


def _execute_import_from_website(params: dict, website_id: int, business_id: int, db: Session) -> str:
    """Scrape a URL and drop hero/about/gallery/design onto the user's page."""
    import models
    from datetime import datetime as dt_now

    url = (params.get("url") or "").strip()
    if not url:
        return "I need a URL to import from."
    include_raw = (params.get("include") or "hero,about,design").lower()
    include = {s.strip() for s in include_raw.split(",") if s.strip()}
    page_name = params.get("page_name")

    data = _run_scrape(url, deep=False)
    if data.get("error"):
        return f"Import failed — {data['error']}"

    page_row = None
    if page_name:
        page_row = db.execute(
            text("SELECT PageID FROM BusinessWebPage WHERE WebsiteID=:wid AND PageName=:pn"),
            {"wid": website_id, "pn": page_name},
        ).fetchone()
    if not page_row:
        page_row = db.execute(
            text("SELECT TOP 1 PageID FROM BusinessWebPage WHERE WebsiteID=:wid AND IsHomePage=1"),
            {"wid": website_id},
        ).fetchone()
    if not page_row:
        return "No page found to import into. Add a page first."
    page_id = page_row[0]

    max_sort = db.execute(
        text("SELECT ISNULL(MAX(SortOrder), 0) FROM BusinessWebBlock WHERE PageID=:pid"),
        {"pid": page_id},
    ).fetchone()[0]
    sort = int(max_sort)

    tokens    = data.get("designTokens") or {}
    headings  = data.get("headings") or []
    bodies    = data.get("bodyText") or []
    images    = data.get("images") or []
    added: list[str] = []

    if "design" in include:
        site = db.query(models.BusinessWebsite).filter(
            models.BusinessWebsite.WebsiteID == website_id
        ).first()
        if site:
            if tokens.get("navBgColor"):   site.PrimaryColor   = tokens["navBgColor"]
            if tokens.get("accentColor"):  site.AccentColor    = tokens["accentColor"]
            if tokens.get("pageBgColor"):  site.BgColor        = tokens["pageBgColor"]
            if tokens.get("navTextColor"): site.NavTextColor   = tokens["navTextColor"]
            if tokens.get("bodyFont"):     site.FontFamily     = tokens["bodyFont"]
            site.UpdatedAt = dt_now.utcnow()
            added.append("design palette")

    if "hero" in include and headings:
        headline = headings[0].get("text") if isinstance(headings[0], dict) else str(headings[0])
        hero_image = ""
        for img in images:
            src = img.get("src") if isinstance(img, dict) else None
            if src and not src.endswith(".svg"):
                hero_image = src
                break
        block_data = {
            "headline": headline or "Welcome",
            "subtext": (bodies[0] if bodies else "")[:240],
            "image_url": hero_image,
            "cta_text": "Learn More", "cta_link": "#about",
            "overlay": True, "align": "center",
        }
        sort += 10
        db.add(models.BusinessWebBlock(
            PageID=page_id, BlockType="hero",
            BlockData=json.dumps(block_data), SortOrder=sort,
            CreatedAt=dt_now.utcnow(), UpdatedAt=dt_now.utcnow(),
        ))
        added.append("hero block")

    if "about" in include:
        body = "\n\n".join(bodies[1:4]) if len(bodies) > 1 else (bodies[0] if bodies else "")
        if body:
            sort += 10
            db.add(models.BusinessWebBlock(
                PageID=page_id, BlockType="about",
                BlockData=json.dumps({
                    "heading": "About Us", "body": body[:1200],
                    "image_url": "", "image_position": "right",
                }),
                SortOrder=sort,
                CreatedAt=dt_now.utcnow(), UpdatedAt=dt_now.utcnow(),
            ))
            added.append("about block")

    if "gallery" in include and len(images) >= 3:
        srcs = []
        for img in images[:12]:
            src = img.get("src") if isinstance(img, dict) else None
            if src and not src.endswith(".svg"):
                srcs.append(src)
        if len(srcs) >= 3:
            sort += 10
            db.add(models.BusinessWebBlock(
                PageID=page_id, BlockType="gallery",
                BlockData=json.dumps({
                    "heading": "Photo Gallery",
                    "images": srcs, "max_items": len(srcs),
                }),
                SortOrder=sort,
                CreatedAt=dt_now.utcnow(), UpdatedAt=dt_now.utcnow(),
            ))
            added.append("gallery block")

    db.commit()
    if not added:
        return f"I scraped {url} but didn't find enough content to import. Try a different URL or a deeper page."
    return f"Imported from {url}: {', '.join(added)}."


# ── System prompt ─────────────────────────────────────────────────

def _build_system_prompt(site_context: str, rag_context: str, recent_scrape: str = "") -> str:
    return f"""You are {AGENT_NAME}, a warm and knowledgeable AI website design assistant for OatmealFarmNetwork — a platform for farmers, ranchers, and agricultural businesses.

You guide users in building beautiful, effective farm websites. You can ALSO make changes to their website directly when asked — you will propose the change and wait for the user to confirm before executing it.

WEBSITE BUILDER FEATURES YOU KNOW:
- Pages, Blocks (hero, about, content, livestock, produce, meat, services, gallery, blog, events, contact, divider)
- Design: colors, fonts, logo, header images with date ranges
- Settings: site name, slug, contact info, social media
- SEO: meta title, canonical URL, Open Graph image, schema markup
- Version History: save and restore snapshots
- 12 color palettes: Farmstead, Harvest, Modern Market, Artisan, Fresh, Classic, Meadow, Sunset Ranch, Slate & Stone, Lavender Field, Coastal, Midnight
- Publish/Unpublish control
- Events: the farm can host events (clinics, auctions, farm tours, workshops, fiber-arts gatherings, dinners). Events can be displayed on the site via the "Upcoming Events" block, and individual events can be published/unpublished. Only PUBLISHED events appear on the public site and in the network feed.

WHEN THE USER ASKS YOU TO MAKE A CHANGE:
- Use the appropriate tool to propose the change
- Be specific about what you're about to change
- Keep responses concise — 2-3 short paragraphs max
- After a change is confirmed and done, tell the user to refresh their browser to see it

EVENT HINTS:
- If the user has draft events (shown above as [DRAFT]) and asks about promoting/showing their event, offer to publish it with `publish_event`.
- If the user wants their events visible on their site, use `add_events_block` to drop an Upcoming Events block on their homepage (or a specific page).
- You can reference an event by its ID or by its name — if the user gives a name, use `event_title` and the system will match it.

REVIEWING & IMPROVING THE SITE:
- The site context above already includes an AUDIT FINDINGS block listing prioritized issues — reference these directly when giving advice.
- When the user asks to "review", "audit", "critique", or "improve" the site, call the `review_site` tool (it runs inline, no confirmation needed).
- After reviewing, offer to fix the top 1-2 issues using the appropriate tool: `add_block` to add missing sections (hero, about, contact, gallery, events, blog, testimonials, etc.), `update_block` to rewrite weak copy or swap images, `update_site_design`/`update_site_settings` for design and contact fixes, `publish_event` for draft events.
- Lead with the highest-severity findings. Be specific ("Your homepage has no hero banner — want me to add one?") rather than vague.
- Don't overwhelm — surface 3-4 top findings, then offer to fix them one at a time.

GENERATING VISUAL DESIGNS:
- You can PRODUCE designs the user can see BEFORE applying them.
- For hero/banner imagery, call `generate_hero_image(description, style?, page_name?, apply_to?)` — the image is generated at chat time, shown in the response, and the user confirms before it lands on their site. Write rich descriptions grounded in their farm (what animals, what landscape, what season).
- For color/typography direction, call `preview_design_change(primary_color, accent_color, font_family, label, …)` — this returns a live mockup URL showing the proposed palette. If the user likes it they can confirm and the same params apply via `update_site_design`.
- Suggest visual design proactively when users are vague ("I want it to feel more homey" → propose 2-3 palette directions with `preview_design_change`; "the hero is boring" → offer `generate_hero_image`).

WEB SCRAPING & COMPETITIVE RESEARCH:
- When the user pastes a URL or asks about "their old site", a competitor, or a design they like, use `scrape_website(url)` to fetch and report what you found (platform, colors, fonts, layout, images). Runs inline.
- Use `review_competitor_site(url)` instead when the intent is comparison or inspiration — you'll get design takeaways phrased for coaching.
- To actually pull content in, use `import_from_website(url, page_name, include)` — this writes blocks to their page and requires confirmation. `include` is a comma-separated subset of "hero,about,gallery,design".
- Every scrape teaches a shared knowledge base you and Chearvil (the admin scraper) share, so the more sites you read, the better both of you get at reading similar ones.

CURRENT WEBSITE STATE:
{site_context}

{f'KNOWLEDGE BASE:{chr(10)}{rag_context}' if rag_context else ''}

{f'RECENT WEB RESEARCH:{chr(10)}{recent_scrape}' if recent_scrape else ''}

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
    recent_scrape = _format_last_scrape(_load_last_scrape(body.website_id) or {})
    system_prompt = _build_system_prompt(site_context, rag_context, recent_scrape)

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
            model_name="gemini-2.5-flash",
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

                # Read-only actions: run inline, return results in the reply
                if action == "review_site":
                    audit_text = _execute_action(
                        action, params, body.website_id, body.business_id, db
                    )
                    return {
                        "role": "assistant",
                        "content": audit_text + "\n\nWant me to fix any of these for you?",
                        "agent": AGENT_NAME,
                    }

                if action == "preview_design_change":
                    token = _store_preview({"kind": "design", **params})
                    return {
                        "role": "assistant",
                        "content": (f"Here's a quick preview of the **{params.get('label') or 'proposed'}** design direction. "
                                    f"If you like it, I can apply it to your site."),
                        "preview_url": f"/api/lavendir/preview/{token}",
                        "pending_action": {
                            "action": "update_site_design",
                            "params": {k: v for k, v in params.items() if k != "label"},
                            "description": _describe_action("update_site_design",
                                                            {k: v for k, v in params.items() if k != "label"}),
                        },
                        "agent": AGENT_NAME,
                    }

                if action == "generate_hero_image":
                    description = (params.get("description") or "").strip()
                    if not description:
                        return {
                            "role": "assistant",
                            "content": "What would you like the hero image to show?",
                            "agent": AGENT_NAME,
                        }
                    prompt_text = _build_hero_prompt(description, params.get("style"))
                    try:
                        from image_service import generate_image_bytes, upload_image_to_gcs
                        import uuid as _uuid
                        img_bytes = await asyncio.get_event_loop().run_in_executor(
                            None, generate_image_bytes, prompt_text
                        )
                        filename = f"website-hero/{body.website_id}_{_uuid.uuid4().hex[:10]}.png"
                        image_url = await asyncio.get_event_loop().run_in_executor(
                            None, upload_image_to_gcs, img_bytes, filename, "image/png"
                        )
                    except Exception as e:
                        return {
                            "role": "assistant",
                            "content": f"I couldn't generate that image — {e}",
                            "agent": AGENT_NAME,
                        }
                    confirm_params = {
                        "image_url": image_url,
                        "apply_to":  params.get("apply_to") or "hero_block",
                        "page_name": params.get("page_name"),
                    }
                    return {
                        "role": "assistant",
                        "content": (f"Here's the hero image I generated from: *\"{description}\"*. "
                                    f"Want me to use it on your site?"),
                        "preview_image_url": image_url,
                        "pending_action": {
                            "action": "generate_hero_image",
                            "params": confirm_params,
                            "description": _describe_action("generate_hero_image", confirm_params),
                        },
                        "agent": AGENT_NAME,
                    }

                if action in ("scrape_website", "review_competitor_site"):
                    url = (params.get("url") or "").strip()
                    if not url:
                        return {
                            "role": "assistant",
                            "content": "Which URL would you like me to look at?",
                            "agent": AGENT_NAME,
                        }
                    try:
                        from scrapers.lavendir_scraper import scrape as _scrape_async
                        data = await _scrape_async(
                            url,
                            use_playwright=bool(params.get("deep")),
                            learn=True,
                        )
                    except Exception as e:
                        return {
                            "role": "assistant",
                            "content": f"I couldn't scrape {url} — {e}",
                            "agent": AGENT_NAME,
                        }
                    competitor = (action == "review_competitor_site")
                    summary = _summarize_scrape(data, competitor=competitor)
                    try:
                        _store_last_scrape(body.website_id, {**data, "summary": summary})
                    except Exception:
                        pass
                    tail = ("\n\nWant me to try any of these ideas on your site?" if competitor
                            else "\n\nWant me to import anything from this site onto one of your pages?")
                    return {
                        "role": "assistant",
                        "content": summary + tail,
                        "agent": AGENT_NAME,
                        "scrape_result": {
                            "url": data.get("url"),
                            "platform": data.get("platform"),
                            "designTokens": data.get("designTokens"),
                            "layoutPatterns": data.get("layoutPatterns"),
                        },
                        "last_scrape": _last_scrape_meta(body.website_id),
                    }

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


# ── Design preview endpoint (iframe target) ──────────────────────

@router.get("/preview/{token}")
def lavendir_preview(token: str):
    from fastapi.responses import HTMLResponse, PlainTextResponse
    payload = _load_preview(token)
    if not payload:
        return PlainTextResponse("Preview expired or not found.", status_code=404)
    if payload.get("kind") == "design":
        return HTMLResponse(_render_design_preview_html(payload))
    return PlainTextResponse("Unknown preview type.", status_code=400)


# ── Last-scrape chip endpoints ───────────────────────────────────

@router.get("/last-scrape/{website_id}")
def lavendir_get_last_scrape(website_id: int):
    return {"last_scrape": _last_scrape_meta(website_id)}


@router.delete("/last-scrape/{website_id}")
def lavendir_clear_last_scrape(website_id: int):
    _clear_last_scrape(website_id)
    return {"cleared": True}


# ── Standalone review endpoint (for UI-driven audit panel) ────────

@router.get("/review/{website_id}")
def review_website(website_id: int, business_id: int, db: Session = Depends(get_db)):
    """Return a prioritized list of improvement findings for a site.
    Used by the frontend for a standalone 'Review My Site' panel."""
    findings = _audit_site(website_id, business_id, db)
    by_severity = {"critical": [], "high": [], "medium": [], "low": []}
    for f in findings:
        by_severity.setdefault(f["severity"], []).append(f)
    return {
        "website_id": website_id,
        "business_id": business_id,
        "finding_count": len(findings),
        "by_severity": by_severity,
        "findings": findings,
    }


# ── Suggestions ───────────────────────────────────────────────────

@router.get("/suggestions/{website_id}")
def get_suggestions(website_id: int, db: Session = Depends(get_db)):
    suggestions = [{"text": "Review my site and suggest improvements", "action": "review"}]
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
        if page_count < 2:
            suggestions.append({"text": "Add a starter pack of pages (Home, About, Contact, and more)", "action": "starter_pack"})
        elif page_count < 3:
            suggestions.append({"text": "What pages should I add?", "action": "add_page"})
        header_count = db.execute(text("SELECT COUNT(*) FROM WebsiteHeaderImages WHERE WebsiteID=:wid"), {"wid": website_id}).fetchone()[0]
        if header_count == 0:
            suggestions.append({"text": "Add a header image", "action": "design"})

        # Event-aware nudges
        biz_row = db.execute(
            text("SELECT TOP 1 BusinessID FROM BusinessWebsite WHERE WebsiteID=:wid"),
            {"wid": website_id},
        ).fetchone()
        if biz_row:
            bid = biz_row[0]
            # Association-specific nudge: if this business is an Agricultural association
            # (BusinessTypeID=1) and they don't yet have common association pages, suggest them.
            try:
                bt_row = db.execute(
                    text("SELECT BusinessTypeID FROM Business WHERE BusinessID=:bid"),
                    {"bid": bid},
                ).fetchone()
                if bt_row and bt_row[0] == 1:
                    existing_slugs = {r[0] for r in db.execute(
                        text("SELECT Slug FROM BusinessWebPage WHERE WebsiteID=:wid"),
                        {"wid": website_id},
                    ).fetchall()}
                    if "join" not in existing_slugs:
                        suggestions.append({"text": "Add a membership join/renew page", "action": "add_page_template"})
                    elif "register-animal" not in existing_slugs and "online-registry" not in existing_slugs:
                        suggestions.append({"text": "Add a registry/registration page", "action": "add_page_template"})
                    elif "annual-convention" not in existing_slugs:
                        suggestions.append({"text": "Add an annual convention page", "action": "add_page_template"})
            except Exception:
                pass
            draft_count = db.execute(
                text("""SELECT COUNT(*) FROM OFNEvents
                         WHERE BusinessID=:bid AND Deleted=0 AND IsPublished=0
                           AND (EventEndDate IS NULL OR EventEndDate >= CAST(GETDATE() AS DATE))"""),
                {"bid": bid},
            ).fetchone()[0]
            pub_count = db.execute(
                text("""SELECT COUNT(*) FROM OFNEvents
                         WHERE BusinessID=:bid AND Deleted=0 AND IsPublished=1
                           AND (EventEndDate IS NULL OR EventEndDate >= CAST(GETDATE() AS DATE))"""),
                {"bid": bid},
            ).fetchone()[0]
            if draft_count > 0:
                suggestions.append({"text": f"Publish my draft event{'s' if draft_count > 1 else ''}", "action": "events"})
            if pub_count > 0:
                has_events_block = db.execute(
                    text("""SELECT COUNT(*) FROM BusinessWebBlock b
                              JOIN BusinessWebPage p ON p.PageID = b.PageID
                             WHERE p.WebsiteID=:wid AND b.BlockType='events'"""),
                    {"wid": website_id},
                ).fetchone()[0]
                if not has_events_block:
                    suggestions.append({"text": "Show my events on the homepage", "action": "events"})
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
