"""
Cassia — AI customer success agent for Oatmeal Farm Network.

Guides new users through two stages:
  1. Account creation — gathers business info conversationally, then creates
     the Business record in the database.
  2. Subscription selection — loads the feature catalog, understands the
     user's needs, recommends a plan, then signals the frontend to initiate
     Stripe payment.

Architecture mirrors Pairsley/Rosemarie:
  - Gemini LLM (shared llm.py)
  - Redis short-term memory (shared message_buffer.py)
  - Firestore long-term memory  (Cassia_chats collection)
  - Firestore RAG (Cassia_docs collection)
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.tools import tool

from chat_history import ChatHistory
from config import DB_CONFIG, SHORT_TERM_N
from llm import llm
from message_buffer import get_last_n, push_message
from rag import RAGSystem

try:
    import pymssql
    _PMS_AVAILABLE = True
except ImportError:
    _PMS_AVAILABLE = False

logger = logging.getLogger("cassia")

CASSIA_CHATS_COLLECTION = "Cassia_chats"
CASSIA_DOCS_COLLECTION  = "Cassia_docs"


# ── Long-term memory ──────────────────────────────────────────────────────────

class CassiaChatHistory(ChatHistory):
    @property
    def threads_col(self):
        try:
            db = self.firestore_db
            if db:
                return db.collection(CASSIA_CHATS_COLLECTION)
        except Exception as e:
            logger.error("[Cassia] threads_col error: %s", e)
        return None


cassia_chat_history = CassiaChatHistory()
rag_cassia = RAGSystem(CASSIA_DOCS_COLLECTION, label="cassia")


# ── DB helpers ────────────────────────────────────────────────────────────────

def _connect():
    if not _PMS_AVAILABLE or not all(
        [DB_CONFIG.get("host"), DB_CONFIG.get("user"), DB_CONFIG.get("database")]
    ):
        return None
    try:
        return pymssql.connect(
            server=DB_CONFIG["host"],
            port=DB_CONFIG["port"],
            user=DB_CONFIG["user"],
            password=DB_CONFIG["password"],
            database=DB_CONFIG["database"],
            as_dict=True,
        )
    except Exception as e:
        logger.error("[Cassia] DB connect failed: %s", e)
        return None


def _query(sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
    conn = _connect()
    if not conn:
        return []
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        return list(cur.fetchall())
    except Exception as e:
        logger.error("[Cassia] query failed: %s", e)
        return []
    finally:
        conn.close()


def _execute(sql: str, params: tuple = ()) -> int:
    conn = _connect()
    if not conn:
        return 0
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        conn.commit()
        return cur.rowcount
    except Exception as e:
        logger.error("[Cassia] execute failed: %s", e)
        return 0
    finally:
        conn.close()


def _insert_returning_id(sql: str, params: tuple = ()) -> Optional[int]:
    """Run an INSERT and return SCOPE_IDENTITY (MSSQL last-inserted row ID)."""
    conn = _connect()
    if not conn:
        return None
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        cur.execute("SELECT SCOPE_IDENTITY() AS new_id")
        row = cur.fetchone()
        conn.commit()
        return int(row["new_id"]) if row and row.get("new_id") else None
    except Exception as e:
        logger.error("[Cassia] insert_returning_id failed: %s", e)
        return None
    finally:
        conn.close()


# ── Tools ─────────────────────────────────────────────────────────────────────

@tool
def cassia_knowledge_tool(query: str = "") -> str:
    """Search Cassia's knowledge base for platform information, feature
    explanations, pricing details, and FAQs. Use when the user asks
    'what does X do', 'how does Y work', 'what's included', or similar
    platform-knowledge questions."""
    q = (query or "").strip()
    if not q:
        return "Please provide a specific question to search."
    ctx = rag_cassia.get_context_for_query(q)
    return ctx if ctx else (
        "I don't have specific documentation on that — I'll answer from my general knowledge."
    )


@tool
def get_business_types_tool(dummy: str = "") -> str:
    """Retrieve the list of available business types with their IDs. ALWAYS
    call this before asking the user what type of business they have, so you
    can present real options and capture the correct BusinessTypeID integer."""
    rows = _query(
        "SELECT BusinessTypeID, BusinessType FROM BusinessTypes "
        "WHERE IsActive = 1 ORDER BY BusinessType"
    )
    if not rows:
        # Fallback when DB is unavailable
        return (
            "Available business types (ID = Name):\n"
            "8 = Farm / Ranch\n"
            "1 = Restaurant / Food Service\n"
            "2 = Artisan / Specialty Producer\n"
            "3 = Farmer's Market\n"
            "4 = Association / Co-op\n"
            "5 = Supplier / Vendor\n"
            "6 = Other"
        )
    lines = "\n".join(
        f"{r['BusinessTypeID']} = {r['BusinessType']}" for r in rows
    )
    return f"Available business types (ID = Name):\n{lines}"


@tool
def get_states_tool(country: str = "USA") -> str:
    """Get the list of states/provinces for a country with their StateIndex
    IDs. Call this when you need to map a user's state name to the integer
    StateIndex required by the account creation form."""
    rows = _query(
        "SELECT StateIndex, name FROM States WHERE country = %s ORDER BY name",
        (country,),
    )
    if not rows:
        return (
            f"Could not load states for {country}. "
            "Ask the user to type their full state name and I'll do my best."
        )
    lines = ", ".join(f"{r['name']} ({r['StateIndex']})" for r in rows)
    return f"States for {country}:\n{lines}"


@tool
def create_business_account_tool(
    people_id: int = 0,
    business_type_id: int = 0,
    business_name: str = "",
    business_website: str = "",
    address_street: str = "",
    address_apt: str = "",
    address_city: str = "",
    state_index: int = 0,
    address_zip: str = "",
    phone: str = "",
    livestock_disclaimer: bool = False,
    sales_disclaimer: bool = False,
) -> str:
    """Create the business account after confirming all required information
    with the user. Only call this AFTER the user has reviewed and confirmed
    a summary of their information.

    Required fields: business_type_id, state_index, phone.
    For Farm/Ranch (type 8): livestock_disclaimer AND sales_disclaimer must be True.

    Returns 'SUCCESS:BusinessID=<id>' on success, or 'ERROR:<reason>'."""
    if not business_type_id:
        return "ERROR: business_type_id is required."
    if not state_index:
        return "ERROR: state_index is required."
    if not phone:
        return "ERROR: phone number is required."
    if int(business_type_id) == 8:
        if not livestock_disclaimer:
            return "ERROR: livestock legal disclaimer consent is required for Farm/Ranch accounts."
        if not sales_disclaimer:
            return "ERROR: sales legal disclaimer consent is required for Farm/Ranch accounts."

    new_bid = _insert_returning_id(
        """
        INSERT INTO Business (
            BusinessTypeID, BusinessName, BusinessWebsite,
            AddressStreet, AddressApt, AddressCity,
            AddressZip, StateIndex, BusinessPhone,
            LivestockLegalDisclaimer, SalesLegalDisclaimer, Permission
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1)
        """,
        (
            int(business_type_id),
            str(business_name or "")[:200],
            str(business_website or "")[:500],
            str(address_street or "")[:200],
            str(address_apt or "")[:50],
            str(address_city or "")[:100],
            str(address_zip or "")[:20],
            int(state_index),
            str(phone or "")[:50],
            1 if livestock_disclaimer else 0,
            1 if sales_disclaimer else 0,
        ),
    )

    if not new_bid:
        return "ERROR: Could not create business account. The database may be unavailable."

    # Link the business to the person
    if people_id:
        _execute(
            "INSERT INTO PeopleBusiness (PeopleID, BusinessID, AccessLevel) "
            "VALUES (%s, %s, 3)",
            (int(people_id), int(new_bid)),
        )

    return f"SUCCESS:BusinessID={new_bid}"


@tool
def get_subscription_catalog_tool(dummy: str = "") -> str:
    """Load the full subscription feature catalog and per-tier pricing. Call
    this before discussing subscription plans so you have accurate pricing
    data. Returns all available feature modules and their costs by tier."""
    cats = _query(
        "SELECT CategoryID, CategoryName FROM FeatureCategory ORDER BY SortOrder"
    )
    tiers = _query(
        "SELECT CategoryID, TierName, Price, TransactionRate, Qty "
        "FROM FeatureCategoryTierPricing WHERE IsAvailable = 1"
    )

    if not cats:
        return (
            "Subscription tiers overview:\n"
            "• Hobby (Free, ad-supported): For very small operations just starting out\n"
            "• Starter: Core features — best value for most farms\n"
            "• Business: Full feature access + higher limits\n"
            "• Enterprise: Unlimited + premium support\n"
            "Pricing is per module. Ask me which features matter most and I'll build a custom quote."
        )

    tier_map: Dict[int, list] = {}
    for t in tiers:
        tier_map.setdefault(t["CategoryID"], []).append(t)

    lines = ["Feature modules and pricing by tier:"]
    for c in cats:
        cid = c["CategoryID"]
        t_rows = tier_map.get(cid, [])
        priced = []
        for t in t_rows:
            if t.get("Price", 0) and float(t["Price"]) > 0:
                label = f"{t['TierName']} ${float(t['Price']):.2f}/mo"
                if t.get("Qty"):
                    label += f" (up to {t['Qty']})"
                priced.append(label)
            elif t.get("TransactionRate", 0) and float(t["TransactionRate"]) > 0:
                priced.append(f"{t['TierName']} {float(t['TransactionRate'])}% tx fee")
        price_str = " | ".join(priced) if priced else "Included free on paid tiers"
        lines.append(f"• {c['CategoryName']}: {price_str}")

    return "\n".join(lines)


@tool
def prepare_checkout_tool(
    tier: str = "starter",
    categories: str = "",
    line_items_json: str = "[]",
    monthly_total: float = 0.0,
) -> str:
    """Signal that the customer has chosen their plan and is ready to pay.
    Call this ONLY after the customer explicitly confirms their plan choice.

    tier: 'hobby' | 'starter' | 'business' | 'enterprise'
    categories: comma-separated feature module names they're subscribing to
    line_items_json: JSON array of {name, price, note} objects for the receipt
    monthly_total: total monthly cost in USD (0.00 for free hobby tier)"""
    return f"CHECKOUT_READY:tier={tier}:total={monthly_total}"


cassia_tools = [
    cassia_knowledge_tool,
    get_business_types_tool,
    get_states_tool,
    create_business_account_tool,
    get_subscription_catalog_tool,
    prepare_checkout_tool,
]


# ── System prompt ─────────────────────────────────────────────────────────────

CASSIA_SYSTEM_PROMPT = """You are Cassia, the customer success specialist for Oatmeal Farm Network — a comprehensive platform for farmers, ranchers, artisan producers, food service businesses, associations, and agricultural suppliers.

## Your Role
You guide new members through two stages:
1. **Account Setup** — collect required information through friendly conversation, confirm it, then create their business account.
2. **Subscription Selection** — understand their needs and recommend the right plan with accurate pricing.

## Your Personality
- Warm, patient, and genuinely curious about their operation
- You celebrate agriculture — farming and ranching is meaningful work
- Speak plainly, no jargon, ask ONE question at a time
- Never pushy about upgrades; help them find the plan that truly fits

---

## STAGE 1: ACCOUNT CREATION

### Conversation order (stick to this sequence):
1. Call get_business_types_tool, then ask what type of operation they have
2. Ask for their state (call get_states_tool to look up the StateIndex integer)
3. Ask for their phone number
4. Ask for their business name (mention it's optional and can be added later)
5. Ask if they have a website (optional)
6. Ask for their city and state/zip (optional, but nice for the profile)
7. **Farm/Ranch accounts only (BusinessTypeID = 8):** Before creating the account, you MUST explain both legal disclaimers and get explicit YES consent for each:
   - Livestock disclaimer: "By creating a Farm/Ranch account, you acknowledge that Oatmeal Farm Network is not responsible for the accuracy of livestock health claims, pedigrees, or sale prices listed by members."
   - Sales disclaimer: "You agree that all livestock sales through the platform comply with applicable local, state, and federal regulations."
   - Ask: "Do you agree to both of these? Please reply Yes or No."

### Before calling create_business_account_tool:
Show the user a clear summary of what you're about to submit, like:
"Here's what I have — does everything look right?
  • Type: [business type]
  • State: [state name]
  • Phone: [phone]
  • Name: [name or 'not set']"
Wait for their confirmation before calling the tool.

### After account creation:
Acknowledge warmly ("Your account is created! Now let's find the right plan.") and move directly to Stage 2.

---

## STAGE 2: SUBSCRIPTION SETUP

1. Call get_subscription_catalog_tool to load current pricing
2. Ask 2–3 focused questions: operation size, what they primarily want to do (sell livestock? host events? build a website? use the marketplace?), team size
3. Make a specific recommendation with clear reasoning ("Based on what you've told me, I'd suggest Starter — here's why...")
4. Walk through the pricing: list the modules they'd get and the monthly cost
5. Ask if they'd like to proceed
6. When they confirm: call prepare_checkout_tool with the tier, categories, line_items_json (JSON array of {name, price} objects), and monthly_total

---

## Tool Rules
- Call get_business_types_tool BEFORE presenting type options to the user
- Call get_states_tool before or after asking for their state (use it to find the StateIndex integer)
- NEVER call create_business_account_tool without user confirmation of a summary
- NEVER call prepare_checkout_tool until user explicitly says yes to the plan
- Use cassia_knowledge_tool for any platform "what is / how does" questions

## Style
- One question at a time
- 2–4 sentences per response (more only when explaining pricing or disclaimers)
- Never repeat questions already answered in this conversation
- If they want to change something before account creation, update your collected info and re-confirm"""


# ── Core chat loop ────────────────────────────────────────────────────────────

def _render_short_term(messages: List[Dict[str, Any]]) -> str:
    if not messages:
        return ""
    lines = ["Recent conversation (oldest first):"]
    for m in messages[-SHORT_TERM_N:]:
        role = (m.get("role") or "user").upper()
        content = (m.get("content") or "").strip()
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines)


def respond(
    user_input: str,
    thread_id: str,
    user_id: str,
    business_id: Optional[int] = None,
    max_iterations: int = 5,
) -> Dict[str, Any]:
    """Run one Cassia conversation turn.

    Persists the exchange to Firestore + Redis, runs a ReAct tool loop,
    and returns a JSON-ready dict that may include 'action' and 'data'
    keys when special events occur (account creation, checkout ready).
    """
    turn_start = time.monotonic()

    cassia_chat_history.save_message(
        user_id=user_id, thread_id=thread_id, role="user", content=user_input,
    )
    push_message(thread_id=thread_id, message={"role": "user", "content": user_input})

    last_n = get_last_n(thread_id, SHORT_TERM_N) or []
    short_term = _render_short_term(last_n)

    try:
        rag_ctx = rag_cassia.get_context_for_query(user_input) or ""
    except Exception as e:
        logger.warning("[Cassia] RAG error: %s", e)
        rag_ctx = ""

    llm_with_tools = llm.bind_tools(cassia_tools)

    prompt_parts = [CASSIA_SYSTEM_PROMPT]
    prompt_parts.append(
        f"\nSystem context: people_id for this session is {user_id}. "
        "Pass this as people_id when calling create_business_account_tool."
    )
    if short_term:
        prompt_parts.append(f"\n[Conversation history]\n{short_term}")
    if rag_ctx:
        prompt_parts.append(f"\n[Platform knowledge]\n{rag_ctx}")
    prompt_parts.append(f"\n[User message]\n{user_input}")
    current_input = "\n".join(prompt_parts)

    tool_results_context = ""
    side_data: Dict[str, Any] = {}
    final_response = ""
    response = None

    try:
        for iteration in range(max_iterations):
            composed = current_input
            if tool_results_context:
                composed += f"\n\n[Tool results so far]\n{tool_results_context}"

            response = llm_with_tools.invoke(composed)
            tool_calls = getattr(response, "tool_calls", None) or []

            if tool_calls and iteration < max_iterations - 1:
                for tc in tool_calls:
                    name = tc.get("name", "")
                    args = tc.get("args", {}) or {}
                    result = _dispatch_tool(name, args, user_id, side_data)
                    if result:
                        tool_results_context = (
                            (tool_results_context + "\n\n" if tool_results_context else "")
                            + f"[{name}]\n{result}"
                        )
                continue

            final_response = getattr(response, "content", None) or str(response)
            break
        else:
            if response is not None:
                final_response = getattr(response, "content", None) or str(response)
            else:
                final_response = "I ran into a snag — please try again in a moment."
    except Exception as e:
        logger.error("[Cassia] respond error: %s", e, exc_info=True)
        final_response = "I hit a snag. Please try again in a moment."

    latency_ms = int((time.monotonic() - turn_start) * 1000)

    cassia_chat_history.save_message(
        user_id=user_id, thread_id=thread_id, role="assistant",
        content=final_response, metadata={"latency_ms": latency_ms},
    )
    push_message(
        thread_id=thread_id,
        message={"role": "assistant", "content": final_response},
    )

    result: Dict[str, Any] = {
        "status": "ok",
        "thread_id": thread_id,
        "response": final_response,
        "latency_ms": latency_ms,
    }
    if side_data:
        result.update(side_data)
    return result


def _dispatch_tool(
    name: str,
    args: Dict[str, Any],
    user_id: str,
    side_data: Dict[str, Any],
) -> str:
    """Invoke a Cassia tool, populate side_data for UI events, return text for LLM."""
    try:
        if name == "cassia_knowledge_tool":
            return cassia_knowledge_tool.invoke({"query": args.get("query", "")})

        if name == "get_business_types_tool":
            return get_business_types_tool.invoke({"dummy": ""})

        if name == "get_states_tool":
            return get_states_tool.invoke({"country": args.get("country", "USA")})

        if name == "create_business_account_tool":
            result_str = create_business_account_tool.invoke({
                "people_id":           int(user_id or 0),
                "business_type_id":    int(args.get("business_type_id", 0) or 0),
                "business_name":       str(args.get("business_name", "") or ""),
                "business_website":    str(args.get("business_website", "") or ""),
                "address_street":      str(args.get("address_street", "") or ""),
                "address_apt":         str(args.get("address_apt", "") or ""),
                "address_city":        str(args.get("address_city", "") or ""),
                "state_index":         int(args.get("state_index", 0) or 0),
                "address_zip":         str(args.get("address_zip", "") or ""),
                "phone":               str(args.get("phone", "") or ""),
                "livestock_disclaimer": bool(args.get("livestock_disclaimer", False)),
                "sales_disclaimer":    bool(args.get("sales_disclaimer", False)),
            })
            if result_str.startswith("SUCCESS:BusinessID="):
                bid = int(result_str.split("=")[1])
                side_data["action"] = "account_created"
                side_data["data"]   = {"business_id": bid}
                return f"Account created successfully. BusinessID is {bid}. Now proceed to subscription."
            return result_str

        if name == "get_subscription_catalog_tool":
            return get_subscription_catalog_tool.invoke({"dummy": ""})

        if name == "prepare_checkout_tool":
            tier        = str(args.get("tier", "starter"))
            cats_raw    = args.get("categories", "")
            categories  = (
                [c.strip() for c in str(cats_raw).split(",") if c.strip()]
                if isinstance(cats_raw, str) else list(cats_raw or [])
            )
            items_raw   = args.get("line_items_json", "[]") or "[]"
            try:
                line_items = json.loads(items_raw) if isinstance(items_raw, str) else list(items_raw)
            except Exception:
                line_items = []
            total = float(args.get("monthly_total", 0) or 0)

            side_data["action"] = "initiate_checkout"
            side_data["data"]   = {
                "tier":          tier,
                "categories":    categories,
                "line_items":    line_items,
                "monthly_total": total,
            }
            return "Checkout data prepared. The frontend will now handle payment."

    except Exception as e:
        logger.error("[Cassia] tool %s failed: %s", name, e)
        return f"(tool {name} error: {e})"

    return f"(unknown tool: {name})"


# ── Read helpers for the REST layer ──────────────────────────────────────────

def list_threads(
    user_id: str, limit: int = 20, cursor: Optional[str] = None
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    return cassia_chat_history.get_threads(user_id, limit=limit, cursor=cursor)


def get_messages(
    user_id: str, thread_id: str, limit: int = 50, cursor: Optional[str] = None
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    return cassia_chat_history.get_messages(user_id, thread_id, limit=limit, cursor=cursor)


def delete_thread(user_id: str, thread_id: str) -> bool:
    return cassia_chat_history.delete_thread(user_id, thread_id)
