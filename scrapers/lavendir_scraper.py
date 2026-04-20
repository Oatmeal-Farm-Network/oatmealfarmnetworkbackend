"""
Lavendir's Python scraper — mirrors Chearvil's pipeline.

Layers:
  1. httpx fetch → BeautifulSoup parse
  2. Platform detection via /api/scraper-knowledge/detect
  3. Known-pattern lookup for this platform
  4. Design token extraction (colors, fonts, og:image, nav/body/accent roles)
  5. Layout-pattern detection (hero/card-grid/testimonials/gallery/etc.)
  6. Optional Playwright layer: computed styles + spatial content + screenshot
  7. Write-back to the knowledge service for every selector that produced a value

The returned dict has the same shape as Chearvil's scrape + build payloads so Lavendir
can reuse it for advice, for import-into-page, or for design-preview generation.
"""
from __future__ import annotations
import os, re, json, time, asyncio
from typing import Optional, Dict, Any, List, Tuple
from urllib.parse import urljoin, urlparse

import httpx

try:
    from bs4 import BeautifulSoup  # type: ignore
    BS4_AVAILABLE = True
except Exception:
    BS4_AVAILABLE = False

try:
    from playwright.async_api import async_playwright  # type: ignore
    PLAYWRIGHT_AVAILABLE = True
except Exception:
    PLAYWRIGHT_AVAILABLE = False


UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

BOT_SIGNALS = [
    "cloudflare", "just a moment", "ddos-guard",
    "access denied", "security check", "perimeterx",
]

# Backend base for the knowledge service. When Lavendir's scraper runs in-process
# it can also import the router functions directly — but going through HTTP keeps
# the same contract that Chearvil (Node) uses, so one code path exercises both.
KNOWLEDGE_BASE = os.getenv("OFN_BACKEND_URL", "http://localhost:8000").rstrip("/")
AGENT = "lavendir"


# ─────────────────────────────────────────────────────────────────────────────
# Small helpers
# ─────────────────────────────────────────────────────────────────────────────

def _clean(s: Optional[str]) -> str:
    if not s:
        return ""
    return re.sub(r"\s+", " ", s).strip()


def _resolve(base: str, href: Optional[str]) -> Optional[str]:
    if not href:
        return None
    href = href.strip()
    if href.startswith("data:") or href.startswith("javascript:"):
        return None
    try:
        return urljoin(base, href)
    except Exception:
        return None


def _hex_to_rgb(hex_s: str) -> Tuple[int, int, int]:
    h = hex_s.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _brightness(rgb: Tuple[int, int, int]) -> float:
    r, g, b = rgb
    return (r * 299 + g * 587 + b * 114) / 1000


def _saturation(rgb: Tuple[int, int, int]) -> float:
    r, g, b = rgb
    mx, mn = max(r, g, b), min(r, g, b)
    return 0.0 if mx == 0 else (mx - mn) / mx


def _norm_hex(raw: str) -> Optional[str]:
    s = raw.strip().lower().lstrip("#")
    if re.fullmatch(r"[0-9a-f]{3}", s):
        s = "".join(c * 2 for c in s)
    if not re.fullmatch(r"[0-9a-f]{6}", s):
        return None
    return "#" + s


def _is_near_white(rgb: Tuple[int, int, int]) -> bool:
    r, g, b = rgb
    return r > 238 and g > 238 and b > 238


def _is_near_black(rgb: Tuple[int, int, int]) -> bool:
    r, g, b = rgb
    return r < 15 and g < 15 and b < 15


def _colors_from_string(s: str) -> List[str]:
    out = []
    for m in re.finditer(r"#?([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b", s or ""):
        hx = _norm_hex(m.group(1))
        if hx:
            out.append(hx)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Knowledge-service client (best-effort, never raises)
# ─────────────────────────────────────────────────────────────────────────────

async def _knowledge_post(path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.post(f"{KNOWLEDGE_BASE}{path}", json=payload)
            if r.status_code < 400:
                return r.json() or {}
    except Exception as e:
        print(f"[lavendir_scraper] knowledge POST {path} failed: {e}")
    return {}


async def _knowledge_get(path: str, params: Dict[str, Any]) -> Dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{KNOWLEDGE_BASE}{path}", params=params)
            if r.status_code < 400:
                return r.json() or {}
    except Exception as e:
        print(f"[lavendir_scraper] knowledge GET {path} failed: {e}")
    return {}


async def detect_platform(html: str, url: Optional[str] = None) -> Dict[str, Any]:
    """Call knowledge service /detect. Returns {platform_key, platform_name, confidence, scores}.
    Passes URL so the server can cache results by domain."""
    # Pass only the head + first 20KB so we stay small on the wire
    head_cut = html[:30000]
    payload: Dict[str, Any] = {"html": head_cut}
    if url:
        payload["url"] = url
    return await _knowledge_post("/api/scraper-knowledge/detect", payload) or {
        "platform_key": "_generic", "platform_name": "Generic", "confidence": 0, "scores": {}
    }


async def lookup_patterns(platform_key: str, field_name: Optional[str] = None) -> List[Dict[str, Any]]:
    params: Dict[str, Any] = {"platform_key": platform_key}
    if field_name:
        params["field_name"] = field_name
    data = await _knowledge_get("/api/scraper-knowledge/lookup", params)
    return data.get("patterns", []) or []


async def lookup_patterns_bulk(platform_key: str, field_names: List[str],
                               limit_per_field: int = 8) -> Dict[str, List[Dict[str, Any]]]:
    """Fetch patterns for all fields in one HTTP round-trip.
    Falls back to per-field loop if the bulk endpoint isn't deployed yet."""
    data = await _knowledge_post("/api/scraper-knowledge/lookup-bulk", {
        "platform_key": platform_key,
        "field_names": list(field_names or []),
        "limit_per_field": int(limit_per_field),
    })
    grouped = (data or {}).get("patterns_by_field")
    if isinstance(grouped, dict) and grouped:
        return {f: grouped.get(f, []) or [] for f in field_names}
    # Fallback — iterate if bulk call didn't return usable data
    out: Dict[str, List[Dict[str, Any]]] = {}
    for f in field_names:
        out[f] = await lookup_patterns(platform_key, f)
    return out


async def record_success(platform_key: str, field_name: str, selector: str,
                         source_url: str, sample: str = "") -> None:
    await _knowledge_post("/api/scraper-knowledge/record-success", {
        "agent_name": AGENT, "platform_key": platform_key,
        "field_name": field_name, "selector_type": "css",
        "selector_value": selector, "source_url": source_url,
        "sample_value": (sample or "")[:800],
    })


async def record_failure(platform_key: str, field_name: str, selector: str,
                         source_url: str) -> None:
    await _knowledge_post("/api/scraper-knowledge/record-failure", {
        "agent_name": AGENT, "platform_key": platform_key,
        "field_name": field_name, "selector_type": "css",
        "selector_value": selector, "source_url": source_url,
    })


async def record_new_pattern(platform_key: str, field_name: str, selector: str,
                             source_url: str, sample: str = "") -> None:
    """Register a freshly discovered selector so future scrapes prefer it."""
    await _knowledge_post("/api/scraper-knowledge/record-new-pattern", {
        "agent_name": AGENT, "platform_key": platform_key,
        "field_name": field_name, "selector_type": "css",
        "selector_value": selector, "source_url": source_url,
        "sample_value": (sample or "")[:800],
    })


# Background tasks for knowledge writes — fire-and-forget so probe loop stays fast.
# Keep hard refs to prevent GC cancellation.
_BG_TASKS: set = set()

def _fire(coro) -> None:
    """Schedule a coroutine without awaiting it; hold a ref until it finishes."""
    try:
        task = asyncio.create_task(coro)
    except RuntimeError:
        # No running loop — drop it rather than blocking
        return
    _BG_TASKS.add(task)
    task.add_done_callback(_BG_TASKS.discard)


# ─────────────────────────────────────────────────────────────────────────────
# Design token extraction (BeautifulSoup layer — Chearvil's Cheerio port)
# ─────────────────────────────────────────────────────────────────────────────

def _extract_design_tokens(soup: "BeautifulSoup") -> Dict[str, Any]:
    color_freq:    Dict[str, int] = {}
    nav_colors:    Dict[str, int] = {}
    bg_colors:     Dict[str, int] = {}
    accent_colors: Dict[str, int] = {}
    fonts:         set[str] = set()

    # 1. meta theme-color
    theme = soup.find("meta", attrs={"name": "theme-color"})
    if theme and theme.get("content"):
        hx = _norm_hex(theme["content"])
        if hx:
            color_freq[hx] = color_freq.get(hx, 0) + 30

    # 2. og:image
    og = soup.find("meta", attrs={"property": "og:image"})
    og_image = og["content"] if (og and og.get("content")) else None

    # 3. Inline <style> blocks — aggregate CSS text
    css_parts = [t.get_text() for t in soup.find_all("style") if t.get_text()]
    css_text = "\n".join(css_parts)

    # Hex colors from CSS (general frequency signal)
    for m in re.finditer(r"#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b", css_text):
        hx = _norm_hex(m.group(1))
        if not hx:
            continue
        rgb = _hex_to_rgb(hx)
        if _is_near_white(rgb) or _is_near_black(rgb):
            continue
        color_freq[hx] = color_freq.get(hx, 0) + 1

    # Font families
    for m in re.finditer(r"font-family\s*:\s*([^;{}]+)", css_text, re.IGNORECASE):
        for raw in m.group(1).split(","):
            f = raw.strip().strip("'\"")
            # keep first up-to-3 words
            f = " ".join(f.split()[:3])
            if f and not re.fullmatch(
                r"(inherit|initial|unset|sans-serif|serif|monospace|cursive|fantasy|system-ui|-apple-system|BlinkMacSystemFont)",
                f, re.IGNORECASE
            ):
                fonts.add(f)

    def record(hex_s: Optional[str], bucket: Dict[str, int], weight: int) -> None:
        if not hex_s:
            return
        rgb = _hex_to_rgb(hex_s)
        if _is_near_white(rgb) or _is_near_black(rgb):
            return
        bucket[hex_s] = bucket.get(hex_s, 0) + weight
        color_freq[hex_s] = color_freq.get(hex_s, 0) + weight

    nav_selectors  = ["nav", "header", "#header", "#nav", ".header", ".nav",
                      "#menu", ".menu", "#navbar", ".navbar",
                      ".site-header", ".top-nav", "[role='navigation']"]
    body_selectors = ["body", "#wrapper", "#content", "#main", "main",
                      ".main", "#page", ".page", "#container", ".container", ".site-body"]
    cta_selectors  = ["a.button", "button", ".btn", ".cta",
                      "input[type='submit']", "input[type='button']", ".button"]

    def scan_role(selectors: List[str], bucket: Dict[str, int], weight: int) -> None:
        for sel in selectors:
            try:
                for el in soup.select(sel):
                    combined = " ".join([
                        el.get("style", ""), el.get("bgcolor", ""), el.get("color", "")
                    ])
                    for hx in _colors_from_string(combined):
                        record(hx, bucket, weight)
            except Exception:
                # selector syntax from [role=...] etc. can trip strict parsers; skip
                pass

    scan_role(nav_selectors,  nav_colors,   25)
    scan_role(body_selectors, bg_colors,    20)
    scan_role(cta_selectors,  accent_colors, 15)

    # CSS rule-level background-color by role
    patterns = [
        (re.compile(r"(?:nav|header|\.header|\.nav|#header|#nav|\.navbar|\.site-header|\.top-nav|\.menu)[^{]*\{([^}]*)\}", re.IGNORECASE),
         nav_colors, 20),
        (re.compile(r"(?:body|\.main|#content|#wrapper|\.site-body)[^{]*\{([^}]*)\}", re.IGNORECASE),
         bg_colors, 15),
        (re.compile(r"(?:\.btn|button|\.button|\.cta|a\.btn|input\[type=.submit.\])[^{]*\{([^}]*)\}", re.IGNORECASE),
         accent_colors, 15),
    ]
    for rx, bucket, w in patterns:
        for m in rx.finditer(css_text):
            body = m.group(1)
            bg = re.search(r"background(?:-color)?\s*:\s*(#[0-9a-fA-F]{3,6})", body, re.IGNORECASE)
            if bg:
                record(_norm_hex(bg.group(1)), bucket, w)

    # Sweep bgcolor attribute on any element (old HTML sites)
    for el in soup.select("[bgcolor]"):
        val = el.get("bgcolor", "")
        for hx in _colors_from_string(val):
            tag = (el.name or "").lower()
            if tag in ("nav", "header"):
                record(hx, nav_colors, 20)
            elif tag == "body":
                record(hx, bg_colors, 20)
            else:
                record(hx, color_freq, 3)

    # Pick best per role
    def top(m: Dict[str, int]) -> List[str]:
        return [k for k, _ in sorted(m.items(), key=lambda kv: kv[1], reverse=True)]

    top_colors = top(color_freq)[:10]

    nav_candidates = top(nav_colors)
    nav_bg = next((h for h in nav_candidates if _brightness(_hex_to_rgb(h)) < 160), None) \
           or (nav_candidates[0] if nav_candidates else None)

    bg_candidates = top(bg_colors)
    page_bg = next(
        (h for h in bg_candidates
         if 80 < _brightness(_hex_to_rgb(h)) < 235),
        None
    ) or (bg_candidates[0] if bg_candidates else None)

    accent_candidates = top(accent_colors)
    accent = next(
        (h for h in accent_candidates
         if _saturation(_hex_to_rgb(h)) > 0.25 and _brightness(_hex_to_rgb(h)) > 60),
        None
    ) or (accent_candidates[0] if accent_candidates else None)

    nav_text = None
    if nav_bg:
        nav_text = "#ffffff" if _brightness(_hex_to_rgb(nav_bg)) < 128 else "#111827"

    return {
        "colors":        top_colors,
        "fonts":         sorted(fonts)[:6],
        "ogImage":       og_image,
        "navBgColor":    nav_bg,
        "pageBgColor":   page_bg,
        "accentColor":   accent,
        "navTextColor":  nav_text,
        "footerBgColor": nav_bg,
    }


def _detect_layout_patterns(soup: "BeautifulSoup") -> Dict[str, Any]:
    sections: List[str] = []

    def any_match(*sels: str) -> bool:
        for sel in sels:
            try:
                if soup.select_one(sel):
                    return True
            except Exception:
                pass
        return False

    def count_match(*sels: str) -> int:
        n = 0
        for sel in sels:
            try:
                n += len(soup.select(sel))
            except Exception:
                pass
        return n

    if any_match("[class*='hero']", "[class*='banner']", "[class*='slider']", "[class*='carousel']", "[class*='jumbotron']"):
        sections.append("hero-section")
    if count_match("[class*='card']", "[class*='grid-item']", "[class*='feature']", "[class*='tile']") >= 3:
        sections.append("card-grid")
    if any_match("[class*='testimonial']", "[class*='review']", "[class*='quote']") or count_match("blockquote") >= 2:
        sections.append("testimonials")
    if any_match("[class*='gallery']", "[class*='lightbox']", "[class*='album']") or count_match("img") >= 8:
        sections.append("image-gallery")
    if count_match("[class*='faq']", "[class*='accordion']", "[class*='collapse']") >= 2:
        sections.append("faq")
    if count_match("[class*='team']", "[class*='staff']", "[class*='member']") >= 2:
        sections.append("team-section")
    if any_match("[class*='pricing']", "[class*='price-table']"):
        sections.append("pricing-table")

    # Nav links
    nav_links: List[str] = []
    seen: set[str] = set()
    for sel in ["nav a", "header a", "[role='navigation'] a", "#nav a", "#menu a", ".nav a"]:
        try:
            for a in soup.select(sel):
                t = _clean(a.get_text())
                if t and 1 < len(t) < 40 and t not in seen:
                    seen.add(t)
                    nav_links.append(t)
        except Exception:
            pass
    return {"sections": sections, "navLinks": nav_links[:14]}


# ─────────────────────────────────────────────────────────────────────────────
# Core content extraction (text/images/links)
# ─────────────────────────────────────────────────────────────────────────────

def _extract_content(soup: "BeautifulSoup", base_url: str) -> Dict[str, Any]:
    page_title = _clean(
        (soup.title.get_text() if soup.title else "")
        or (soup.h1.get_text() if soup.h1 else "")
        or base_url
    )

    meta_desc_el = soup.find("meta", attrs={"name": "description"}) \
                or soup.find("meta", attrs={"property": "og:description"})
    meta_description = _clean(meta_desc_el["content"]) if (meta_desc_el and meta_desc_el.get("content")) else ""

    # Remove noise (after design tokens + layout have already been captured)
    for sel in ["script", "style", "noscript", "iframe"]:
        for el in soup.find_all(sel):
            el.decompose()

    # Headings
    headings: List[Dict[str, str]] = []
    for tag in ["h1", "h2", "h3", "h4"]:
        for h in soup.find_all(tag):
            t = _clean(h.get_text())
            if t:
                headings.append({"level": tag.upper(), "text": t})

    # Body paragraphs
    body_text: List[str] = []
    body_selectors = ["p", "li", "td", "th", "blockquote", "figcaption",
                      "[class*='content']", "[class*='text']",
                      "[class*='description']", "[class*='body']"]
    seen_text: set[str] = set()
    for sel in body_selectors:
        try:
            for el in soup.select(sel):
                t = _clean(el.get_text())
                if t and len(t) > 20 and t not in seen_text:
                    seen_text.add(t)
                    body_text.append(t)
        except Exception:
            pass

    # Images
    images: List[Dict[str, Any]] = []
    seen_img: set[str] = set()
    for img in soup.find_all("img"):
        src = (img.get("src") or img.get("data-src")
               or img.get("data-lazy-src") or img.get("data-original"))
        abs_src = _resolve(base_url, src)
        if not abs_src or abs_src in seen_img:
            continue
        seen_img.add(abs_src)
        images.append({
            "url": abs_src,
            "alt": _clean(img.get("alt") or ""),
            "width":  img.get("width"),
            "height": img.get("height"),
        })
    # CSS background images
    for el in soup.select("[style*='background']"):
        style_val = el.get("style", "")
        m = re.search(r"url\(['\"]?([^'\")\s]+)['\"]?\)", style_val, re.IGNORECASE)
        if m:
            abs_src = _resolve(base_url, m.group(1))
            if abs_src and abs_src not in seen_img:
                seen_img.add(abs_src)
                images.append({"url": abs_src, "alt": "", "width": None, "height": None})

    # Links
    links: List[Dict[str, str]] = []
    seen_link: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = _resolve(base_url, a.get("href"))
        text = _clean(a.get_text())
        if href and text and href not in seen_link:
            seen_link.add(href)
            links.append({"href": href, "text": text[:200]})

    return {
        "pageTitle":       page_title,
        "metaDescription": meta_description,
        "headings":        headings,
        "bodyText":        body_text,
        "images":          images,
        "links":           links[:500],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Platform-aware field extraction + learning write-back
# ─────────────────────────────────────────────────────────────────────────────

FIELD_PROBES = [
    # (field_name, transform_result_to_sample)
    "hero_headline",
    "hero_image",
    "logo",
    "nav_links",
    "cta_button",
    "content_main",
    "blog_posts_list",
    "product_cards",
]


# Heuristic fallback selectors — tried in order when all learned patterns miss.
# If one matches, we grab the value AND register it as a new pattern for this
# platform so future scrapes of the same platform skip straight to it.
_HEURISTIC_SELECTORS: Dict[str, List[str]] = {
    "hero_headline":   ["main h1", "h1", "section:first-of-type h1", "header h1"],
    "hero_image":      ["main img", "section:first-of-type img", "header img", "img"],
    "logo":            ["a[href='/'] img", "header a img", ".logo img", "[class*='logo'] img"],
    "nav_links":       ["header nav a", "nav a[href]", "header a[href]", "[role='navigation'] a"],
    "cta_button":      ["a.button", "a.btn", "button.primary", "a[class*='cta']", "a[class*='button']"],
    "content_main":    ["main", "article", "[role='main']", "#main", "#content"],
    "blog_posts_list": ["article", "[class*='post']", "[class*='blog'] article", "main article"],
    "product_cards":   ["[class*='product']", "[class*='card']", "li.product", "[data-product-id]"],
}


# ── Gemini-assisted last-resort selector discovery ──
# Triggers only when learned patterns AND hardcoded heuristics both miss.
# One call handles all still-missing fields so we pay the latency/token cost once.
GEMINI_FALLBACK_MODEL = os.getenv("LAVENDIR_GEMINI_MODEL", "gemini-2.5-flash")

# Per-host cooldown so repeated scrapes of the same site don't re-pay the ~15s
# Gemini call when heuristics + learned patterns are still short.
_GEMINI_COOLDOWN_SEC = int(os.getenv("LAVENDIR_GEMINI_COOLDOWN_SEC", str(15 * 60)))
_GEMINI_COOLDOWN_PREFIX = "scraperkb:gemini-cooldown:"
_GEMINI_COOLDOWN_LOCAL: Dict[str, float] = {}


def _gemini_cooldown_redis():
    try:
        from saige.redis_client import get_redis_client
        return get_redis_client(decode_responses=True)
    except Exception:
        return None


def _host_of(url: Optional[str]) -> str:
    if not url:
        return ""
    try:
        h = (urlparse(url).netloc or "").lower()
        return h[4:] if h.startswith("www.") else h
    except Exception:
        return ""


def _gemini_cooldown_active(host: str) -> bool:
    if not host:
        return False
    client = _gemini_cooldown_redis()
    if client is not None:
        try:
            return bool(client.get(_GEMINI_COOLDOWN_PREFIX + host))
        except Exception:
            pass
    exp = _GEMINI_COOLDOWN_LOCAL.get(host, 0.0)
    return exp > time.time()


def _gemini_cooldown_mark(host: str) -> None:
    if not host:
        return
    client = _gemini_cooldown_redis()
    if client is not None:
        try:
            client.setex(_GEMINI_COOLDOWN_PREFIX + host, _GEMINI_COOLDOWN_SEC, "1")
            return
        except Exception:
            pass
    _GEMINI_COOLDOWN_LOCAL[host] = time.time() + _GEMINI_COOLDOWN_SEC


_FIELD_DESCRIPTIONS = {
    "hero_headline":   "the main page headline (the largest, most prominent heading)",
    "hero_image":      "the main banner/hero image (the largest visually prominent image at the top)",
    "logo":            "the site logo image (usually in the top-left, often a link to '/')",
    "nav_links":       "the primary navigation menu anchor links",
    "cta_button":      "the primary call-to-action button/link (e.g., 'Shop now', 'Get started', 'Contact us')",
    "content_main":    "the main content container (usually <main>, <article>, or role='main')",
    "blog_posts_list": "the list of blog posts on a blog index page",
    "product_cards":   "repeated product cards on a shop/listing page",
}


async def _gemini_discover_selectors(html: str, missing_fields: List[str],
                                     source_url: Optional[str] = None) -> Dict[str, str]:
    """Ask Gemini for CSS selectors for the fields that neither learned patterns
    nor hardcoded heuristics could match. Returns {field: selector} — missing or
    unparseable fields are simply absent. Fails closed on any error."""
    if not missing_fields:
        return {}
    host = _host_of(source_url)
    if _gemini_cooldown_active(host):
        print(f"[lavendir_scraper] gemini cooldown active for {host} — skipping")
        return {}
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        return {}
    try:
        import google.generativeai as genai
    except Exception:
        return {}
    # Mark cooldown up-front so concurrent scrapes of the same host don't stampede.
    _gemini_cooldown_mark(host)

    # Trim HTML to keep tokens sane. Prefer <body> contents; fall back to first N chars.
    snippet = html or ""
    m = re.search(r"<body\b[^>]*>([\s\S]*)</body>", snippet, re.IGNORECASE)
    if m:
        snippet = m.group(1)
    snippet = snippet[:12000]

    field_lines = "\n".join(f"- {f}: {_FIELD_DESCRIPTIONS.get(f, f)}" for f in missing_fields)
    prompt = (
        "You are extracting CSS selectors from an HTML page.\n"
        "For each listed field, return a single CSS selector that uniquely identifies that element "
        "on the page, or null if the page has no such element.\n\n"
        f"Fields:\n{field_lines}\n\n"
        "HTML (truncated):\n"
        "```html\n"
        f"{snippet}\n"
        "```\n\n"
        "Return ONLY a JSON object mapping field name to selector (or null). No prose, no code fences."
    )

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(
            model_name=GEMINI_FALLBACK_MODEL,
            generation_config={"response_mime_type": "application/json"},
        )
        # Gemini SDK's generate_content is sync; run in a thread so we don't block the loop.
        # Hard-cap at 15s — if Gemini is slow, scrape still returns with heuristic results.
        resp = await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(None, lambda: model.generate_content(prompt)),
            timeout=15.0,
        )
        text_out = (resp.text or "").strip()
        if not text_out:
            return {}
        data = json.loads(text_out)
        if not isinstance(data, dict):
            return {}
        out: Dict[str, str] = {}
        for f in missing_fields:
            v = data.get(f)
            if isinstance(v, str) and v.strip():
                out[f] = v.strip()
        return out
    except Exception as e:
        print(f"[lavendir_scraper] gemini selector fallback failed: {e}")
        return {}


def _extract_by_selector(soup: "BeautifulSoup", selector: str, field: str):
    """Run a selector and shape its output the same way the learned-pattern loop does.
    Returns (sample_str, structured_value) or (None, None) if nothing usable."""
    try:
        found = soup.select(selector)
    except Exception:
        return None, None
    if not found:
        return None, None
    if field in ("hero_image", "logo"):
        el = next((e for e in found if e.name == "img" or e.find("img")), None) or found[0]
        img = el if (el.name == "img") else el.find("img")
        src = img.get("src") if img else None
        if src:
            return src, src
        return None, None
    if field == "nav_links":
        vals = []
        for a in found[:14]:
            t = _clean(a.get_text())
            href = a.get("href", "")
            if t and href:
                vals.append({"text": t[:80], "href": href})
        if vals:
            return ", ".join(v["text"] for v in vals[:6]), vals
        return None, None
    text_val = _clean(found[0].get_text())
    if text_val:
        return text_val[:400], text_val
    return None, None


async def _probe_fields(soup: "BeautifulSoup", platform_key: str, source_url: str,
                        raw_html: Optional[str] = None) -> Dict[str, Any]:
    """For each field we care about, try learned selectors in order.
    Record success on the first one that yields a value; record failure for ones that didn't.
    After learned + heuristic passes, Gemini is asked once for any still-missing fields."""
    out: Dict[str, Any] = {}
    missing_fields: List[str] = []
    patterns_by_field = await lookup_patterns_bulk(platform_key, FIELD_PROBES)
    for field in FIELD_PROBES:
        patterns = patterns_by_field.get(field) or []
        winner = None
        first_sample = None
        tried: List[str] = []
        for p in patterns:
            sel = p.get("SelectorValue")
            if not sel:
                continue
            tried.append(sel)
            try:
                found = soup.select(sel)
            except Exception:
                # malformed selector — record once as failure so it falls in the rankings
                _fire(record_failure(platform_key, field, sel, source_url))
                continue
            if not found:
                continue
            # Shape the sample based on field
            if field in ("hero_image", "logo"):
                el = next((e for e in found if e.name == "img" or e.find("img")), None) or found[0]
                img = el if (el.name == "img") else el.find("img")
                if img and img.get("src"):
                    winner = sel
                    first_sample = img.get("src")
                    out[field] = {"selector": sel, "value": first_sample}
                    break
            elif field == "nav_links":
                vals = []
                for a in found[:14]:
                    t = _clean(a.get_text())
                    href = a.get("href", "")
                    if t and href:
                        vals.append({"text": t[:80], "href": href})
                if vals:
                    winner = sel
                    first_sample = ", ".join(v["text"] for v in vals[:6])
                    out[field] = {"selector": sel, "value": vals}
                    break
            else:
                text_val = _clean(found[0].get_text())
                if text_val:
                    winner = sel
                    first_sample = text_val[:400]
                    out[field] = {"selector": sel, "value": text_val}
                    break

        # Heuristic fallback — if no learned pattern matched, try generic selectors.
        # First hit gets recorded as a new_pattern so the flywheel grows for this platform.
        if winner is None:
            for sel in _HEURISTIC_SELECTORS.get(field, []):
                if sel in tried:
                    continue  # already scored as a failure above
                sample, value = _extract_by_selector(soup, sel, field)
                if value is None:
                    continue
                winner = sel
                first_sample = sample
                out[field] = {"selector": sel, "value": value, "source": "heuristic"}
                _fire(record_new_pattern(platform_key, field, sel, source_url, first_sample or ""))
                break

        # Write-back (fire-and-forget so probe loop doesn't block on network I/O):
        # winner gets a success; every other selector tried gets a failure.
        for sel in tried:
            if sel == winner:
                _fire(record_success(platform_key, field, sel, source_url, first_sample or ""))
            else:
                _fire(record_failure(platform_key, field, sel, source_url))

        if winner is None:
            missing_fields.append(field)

    # ── Gemini last-resort: one call for all still-missing fields ──
    if missing_fields and raw_html:
        suggestions = await _gemini_discover_selectors(raw_html, missing_fields, source_url=source_url)
        for field, sel in suggestions.items():
            sample, value = _extract_by_selector(soup, sel, field)
            if value is None:
                continue
            out[field] = {"selector": sel, "value": value, "source": "gemini"}
            _fire(record_new_pattern(platform_key, field, sel, source_url, sample or ""))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Optional Playwright layer
# ─────────────────────────────────────────────────────────────────────────────

def _looks_bot_blocked(html: str, status_code: int = 200) -> bool:
    """Heuristic check whether a fetched page is a bot-challenge / block page."""
    if status_code in (403, 429, 503):
        return True
    if not html:
        return False
    head = html[:6000].lower()
    if len(html) < 1200 and any(sig in head for sig in BOT_SIGNALS):
        return True
    # Common challenge markers that appear even when the body is nonzero
    for marker in (
        "just a moment", "checking your browser", "enable javascript",
        "ray id:", "cf-chl", "cloudflare-static", "please verify you are human",
        "access denied", "ddos-guard", "perimeterx",
    ):
        if marker in head:
            return True
    return False


async def _fetch_html_via_playwright(url: str, timeout_ms: int = 25000) -> Optional[str]:
    """Fetch fully-rendered HTML via Playwright. Returns None if unavailable or blocked."""
    if not PLAYWRIGHT_AVAILABLE:
        return None
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
            context = await browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent=UA,
            )
            page = await context.new_page()
            try:
                await page.goto(url, wait_until="networkidle", timeout=timeout_ms)
            except Exception:
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                    await page.wait_for_timeout(2500)
                except Exception:
                    await browser.close()
                    return None
            title = (await page.title() or "").lower()
            if any(sig in title for sig in BOT_SIGNALS):
                await browser.close()
                return None
            html = await page.content()
            await browser.close()
            return html
    except Exception:
        return None


async def _capture_page_styles(url: str, timeout_ms: int = 25000) -> Dict[str, Any]:
    """Run Playwright (if available) to get computed styles + spatial content + screenshot.
    Returns empty dict if Playwright is not installed or the site bot-blocks us."""
    if not PLAYWRIGHT_AVAILABLE:
        return {"available": False}
    result: Dict[str, Any] = {"available": True, "botBlocked": False}
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
            context = await browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent=UA,
            )
            page = await context.new_page()
            try:
                await page.goto(url, wait_until="networkidle", timeout=timeout_ms)
            except Exception:
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                    await page.wait_for_timeout(2500)
                except Exception as e:
                    await browser.close()
                    return {"available": True, "error": str(e)}

            title = (await page.title() or "").lower()
            if any(sig in title for sig in BOT_SIGNALS):
                await browser.close()
                return {"available": True, "botBlocked": True}

            styles = await page.evaluate("""() => {
                function rgb2hex(rgb) {
                  if (!rgb || rgb === 'rgba(0, 0, 0, 0)' || rgb === 'transparent') return null;
                  const m = rgb.match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/);
                  if (!m) return null;
                  const r = +m[1], g = +m[2], b = +m[3];
                  if (r>240&&g>240&&b>240) return null;
                  if (r<15&&g<15&&b<15) return null;
                  return '#' + [r,g,b].map(x => x.toString(16).padStart(2,'0')).join('');
                }
                function bg(sels){for (const s of sels){try{const el=document.querySelector(s);if(!el) continue;const h=rgb2hex(getComputedStyle(el).backgroundColor);if(h) return h;}catch{}}return null;}
                function col(sels){for (const s of sels){try{const el=document.querySelector(s);if(!el) continue;const h=rgb2hex(getComputedStyle(el).color);if(h) return h;}catch{}}return null;}
                return {
                  navBgColor:   bg(['nav','header','#header','#nav','.navbar','.nav','.site-header','.top-nav','[role=\"navigation\"]']),
                  pageBgColor:  bg(['body','#wrapper','#page','main','.site-body','#container']),
                  accentColor:  bg(['a.button','button[type=\"submit\"]','.btn','.cta','input[type=\"submit\"]','.button']),
                  navTextColor: col(['nav a','header a','.navbar a','.nav a','#menu a'])
                };
            }""")

            # Scroll for lazy loads
            await page.evaluate("""async () => {
                await new Promise(r => {
                  let d=0; const step=600; const max=Math.min(document.body.scrollHeight, 6000);
                  const t=setInterval(()=>{d+=step;window.scrollBy(0,step);if(d>=max){window.scrollTo(0,0);clearInterval(t);r();}},80);
                });
            }""")
            await page.wait_for_timeout(400)

            spatial = await page.evaluate("""() => {
                const items=[];
                document.querySelectorAll('h1,h2,h3,h4,h5,h6,p,li,td,th,figcaption,blockquote').forEach(el=>{
                  const t=(el.innerText||'').trim(); if(!t||t.length<20) return;
                  const r=el.getBoundingClientRect();
                  if (r.width<10||r.height<2) return;
                  const y=Math.round(r.top+window.scrollY); if (y>8000) return;
                  items.push({tag:el.tagName.toLowerCase(), text:t.substring(0,500), x:Math.round(r.left), y});
                });
                items.sort((a,b)=>a.y-b.y||a.x-b.x);
                const seen=new Set();
                return items.filter(i=>{if(seen.has(i.text)) return false; seen.add(i.text); return true;}).slice(0,200);
            }""")

            shot = await page.screenshot(type="jpeg", quality=60, clip={"x":0,"y":0,"width":1280,"height":900})
            import base64
            b64 = base64.b64encode(shot).decode("ascii")
            if len(b64) >= 400_000:
                b64 = ""
            await browser.close()
            result.update({"styles": styles, "spatialContent": spatial, "screenshotB64": b64})
    except Exception as e:
        result["error"] = str(e)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────

async def scrape(url: str, *, use_playwright: bool = False,
                 learn: bool = True, fetch_timeout: float = 20.0) -> Dict[str, Any]:
    """
    Fetch + parse + detect-platform + learning-aware field extraction.
    Returns a full payload compatible with Chearvil's /scrape response plus:
      - platform: {platform_key, platform_name, confidence, scores}
      - probed_fields: {field_name: {selector, value}}
      - capture:   optional Playwright results (styles/spatial/screenshot)
    """
    if not BS4_AVAILABLE:
        return {"error": "beautifulsoup4 is not installed. Run: pip install beautifulsoup4"}

    if not re.match(r"^https?://", url, re.IGNORECASE):
        url = "https://" + url.strip()

    t0 = time.time()
    bot_blocked = False
    fetch_method = "httpx"
    # ── Fetch ──
    try:
        async with httpx.AsyncClient(timeout=fetch_timeout, follow_redirects=True,
                                     headers={"User-Agent": UA}) as client:
            resp = await client.get(url)
            status_code = resp.status_code
            html = resp.text if status_code < 400 else ""
    except httpx.RequestError as e:
        status_code, html = 0, ""
        print(f"[lavendir_scraper] httpx fetch error: {type(e).__name__}: {e}")
    except Exception as e:
        status_code, html = 0, ""
        print(f"[lavendir_scraper] httpx fetch exception: {e}")

    # ── Auto Playwright fallback if the site looks bot-blocked ──
    if _looks_bot_blocked(html, status_code):
        bot_blocked = True
        if PLAYWRIGHT_AVAILABLE:
            rendered = await _fetch_html_via_playwright(url)
            if rendered:
                html = rendered
                status_code = 200
                fetch_method = "playwright-fallback"

    if not html:
        if status_code >= 400:
            return {"error": f"Target site returned HTTP {status_code}.", "status": status_code,
                    "bot_blocked": bot_blocked}
        return {"error": f"Could not reach {url}.", "bot_blocked": bot_blocked}

    soup = BeautifulSoup(html, "html.parser")

    # ── Detect platform + load known patterns ──
    platform = await detect_platform(html, url=url) if learn else {"platform_key": "_generic"}
    platform_key = platform.get("platform_key") or "_generic"

    # ── Extract design DNA BEFORE we strip <style> tags ──
    design_tokens  = _extract_design_tokens(soup)
    layout_patterns = _detect_layout_patterns(soup)

    # ── Platform-aware field probing (learning flywheel) ──
    probed: Dict[str, Any] = {}
    if learn:
        try:
            probed = await _probe_fields(soup, platform_key, url, raw_html=html)
        except Exception as e:
            print(f"[lavendir_scraper] probe error: {e}")

    # ── Core content extraction (uses a fresh soup because we're about to strip tags) ──
    # Re-parse so the structural tags are back for content extraction paths
    soup_for_content = BeautifulSoup(html, "html.parser")
    content = _extract_content(soup_for_content, url)

    # ── Optional Playwright layer ──
    capture: Dict[str, Any] = {"available": False}
    if use_playwright:
        capture = await _capture_page_styles(url)
        # Playwright styles are authoritative — overlay them on design_tokens
        ps_styles = capture.get("styles") or {}
        for k in ("navBgColor", "pageBgColor", "accentColor", "navTextColor"):
            if ps_styles.get(k):
                design_tokens[k] = ps_styles[k]

    return {
        "url":             url,
        "elapsed_ms":      int((time.time() - t0) * 1000),
        "platform":        platform,
        "designTokens":    design_tokens,
        "layoutPatterns":  layout_patterns,
        "probed_fields":   probed,
        "capture":         capture,
        "fetch_method":    fetch_method,
        "bot_blocked":     bot_blocked,
        **content,
        "stats": {
            "headings":   len(content["headings"]),
            "paragraphs": len(content["bodyText"]),
            "images":     len(content["images"]),
            "links":      len(content["links"]),
        },
    }


# Convenience synchronous wrapper for callers outside an event loop
def scrape_sync(url: str, **kwargs: Any) -> Dict[str, Any]:
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Caller is already in a loop — they should await scrape() directly.
            raise RuntimeError("scrape_sync called from within a running event loop; use `await scrape(url)`")
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(scrape(url, **kwargs))
