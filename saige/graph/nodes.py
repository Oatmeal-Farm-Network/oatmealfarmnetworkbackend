# --- graph/nodes.py --- (Supervisor orchestration + advisory leaf specialists)
import re
import logging
import queue as _queue_mod
import threading
import time
from typing import Dict, Any, List, Optional
from langgraph.types import interrupt

# ── Streaming support ────────────────────────────────────────────────────────
# Maps thread_id → Queue. The advisory ReAct loop puts text tokens into the
# queue when streaming mode is active; the /chat/stream SSE endpoint reads them.
_stream_queues: dict = {}
_stream_lock = threading.Lock()

def register_stream_queue(thread_id: str) -> "_queue_mod.Queue":
    q = _queue_mod.Queue()
    with _stream_lock:
        _stream_queues[thread_id] = q
    return q

def deregister_stream_queue(thread_id: str):
    with _stream_lock:
        _stream_queues.pop(thread_id, None)

def _get_stream_queue(thread_id: str):
    with _stream_lock:
        return _stream_queues.get(thread_id)

from config import RAG_AVAILABLE, WEATHER_AVAILABLE, MAX_QUESTIONS
from saige_models import (
    FarmState,
    SaigeState,
    AccountIntent,
    SupervisorRouteDecision,
    VALID_ROUTES,
    QueryTypeClassification,
    WeatherQueryParsed,
    FollowUpEntityExtraction,
)
from llm import llm, get_llm_farm
from graph.routing import route_after_policy, route_after_supervisor  # re-export for shims

logger = logging.getLogger("farm_advisory.nodes")
from rag import rag_livestock, rag_plant, rag_bakasura, rag_news, rag_hitl_charlie
from weather import weather_service, get_weather_tool, weather_tools
try:
    from companion_planting import companion_tools, companion_planting_tool, check_companion_pair_tool
    COMPANION_AVAILABLE = True
except Exception as _e:
    print(f"[nodes] companion_planting unavailable: {_e}")
    companion_tools = []
    companion_planting_tool = None
    check_companion_pair_tool = None
    COMPANION_AVAILABLE = False

try:
    from crop_names import crop_name_tools, crop_name_tool
    CROP_NAMES_AVAILABLE = True
except Exception as _e:
    print(f"[nodes] crop_names unavailable: {_e}")
    crop_name_tools = []
    crop_name_tool = None
    CROP_NAMES_AVAILABLE = False

try:
    from weather_mitigation import weather_mitigation_tools, weather_mitigation_tool
    WEATHER_MITIGATION_AVAILABLE = True
except Exception as _e:
    print(f"[nodes] weather_mitigation unavailable: {_e}")
    weather_mitigation_tools = []
    weather_mitigation_tool = None
    WEATHER_MITIGATION_AVAILABLE = False

try:
    from region_crops import region_crops_tools, region_crops_tool
    REGION_CROPS_AVAILABLE = True
except Exception as _e:
    print(f"[nodes] region_crops unavailable: {_e}")
    region_crops_tools = []
    region_crops_tool = None
    REGION_CROPS_AVAILABLE = False

try:
    from soil_challenges import soil_challenge_tools, soil_challenge_tool
    SOIL_CHALLENGE_AVAILABLE = True
except Exception as _e:
    print(f"[nodes] soil_challenges unavailable: {_e}")
    soil_challenge_tools = []
    soil_challenge_tool = None
    SOIL_CHALLENGE_AVAILABLE = False

try:
    from price_forecast import price_forecast_tools, price_forecast_tool
    PRICE_FORECAST_AVAILABLE = True
except Exception as _e:
    print(f"[nodes] price_forecast unavailable: {_e}")
    price_forecast_tools = []
    price_forecast_tool = None
    PRICE_FORECAST_AVAILABLE = False

try:
    from subsidies import subsidies_tools, subsidies_tool
    SUBSIDIES_AVAILABLE = True
except Exception as _e:
    print(f"[nodes] subsidies unavailable: {_e}")
    subsidies_tools = []
    subsidies_tool = None
    SUBSIDIES_AVAILABLE = False

try:
    from insurance import insurance_tools, insurance_tool
    INSURANCE_AVAILABLE = True
except Exception as _e:
    print(f"[nodes] insurance unavailable: {_e}")
    insurance_tools = []
    insurance_tool = None
    INSURANCE_AVAILABLE = False

try:
    from events import (
        event_tools,
        list_upcoming_events_tool,
        get_event_details_tool,
        event_attendee_count_tool,
    )
    EVENTS_AVAILABLE = True
except Exception as _e:
    print(f"[nodes] events unavailable: {_e}")
    event_tools = []
    list_upcoming_events_tool = None
    get_event_details_tool = None
    event_attendee_count_tool = None
    EVENTS_AVAILABLE = False

try:
    from precision_ag import (
        precision_ag_tools,
        list_my_fields_tool,
        resolve_field_by_name_tool,
        resolve_field_by_name,
        get_field_analysis_tool,
        get_field_history_tool,
        get_field_alerts_tool,
        get_field_soil_samples_tool,
        get_field_scouting_tool,
        add_scout_observation_tool,
        get_field_activity_log_tool,
        log_field_activity_tool,
        add_soil_sample_tool,
        get_field_gdd_tool,
        get_field_irrigation_tool,
        get_field_yield_forecast_tool,
        get_field_carbon_tool,
        get_farm_benchmark_tool,
        get_field_weather_tool,
        get_field_biomass_tool,
        improve_field_biomass_confidence_tool,
        get_field_maturity_tool,
        log_maturity_sample_tool,
        get_field_climate_forecast_tool,
        get_field_water_use_tool,
        get_field_agronomy_tool,
        get_field_zones_tool,
        get_field_assessment_history_tool,
    )
    PRECISION_AG_AVAILABLE = True
except Exception as _e:
    print(f"[nodes] precision_ag unavailable: {_e}")
    precision_ag_tools = []
    get_field_zones_tool = None
    list_my_fields_tool = None
    resolve_field_by_name_tool = None
    resolve_field_by_name = None
    get_field_analysis_tool = None
    get_field_history_tool = None
    get_field_alerts_tool = None
    get_field_soil_samples_tool = None
    get_field_scouting_tool = None
    add_scout_observation_tool = None
    get_field_activity_log_tool = None
    log_field_activity_tool = None
    add_soil_sample_tool = None
    get_field_gdd_tool = None
    get_field_irrigation_tool = None
    get_field_yield_forecast_tool = None
    get_field_carbon_tool = None
    get_farm_benchmark_tool = None
    get_field_weather_tool = None
    get_field_biomass_tool = None
    improve_field_biomass_confidence_tool = None
    get_field_maturity_tool = None
    log_maturity_sample_tool = None
    get_field_climate_forecast_tool = None
    get_field_water_use_tool = None
    get_field_agronomy_tool = None
    get_field_assessment_history_tool = None
    PRECISION_AG_AVAILABLE = False

try:
    from business_ops import (
        business_ops_tools,
        get_tracked_grants_tool,
        calculate_shelf_life_tool,
    )
    BUSINESS_OPS_AVAILABLE = True
except Exception as _e:
    print(f"[nodes] business_ops unavailable: {_e}")
    business_ops_tools = []
    BUSINESS_OPS_AVAILABLE = False

try:
    from farm_data import (
        farm_data_tools,
        list_my_animals_tool,
        list_my_listings_tool,
        count_my_animals_tool,
        list_cold_chain_vehicles_tool,
        geocode_location_tool,
    )
    FARM_DATA_AVAILABLE = True
except Exception as _e:
    print(f"[nodes] farm_data unavailable: {_e}")
    farm_data_tools = []
    list_my_animals_tool = None
    list_my_listings_tool = None
    count_my_animals_tool = None
    list_cold_chain_vehicles_tool = None
    geocode_location_tool = None
    FARM_DATA_AVAILABLE = False

try:
    from business_data import (
        business_data_tools,
        get_business_profile_tool,
        update_business_profile_tool,
        list_my_animals_detail_tool,
        update_animal_tool,
        list_produce_inventory_tool,
        update_produce_listing_tool,
        list_meat_inventory_tool,
        update_meat_listing_tool,
        list_processed_food_tool,
        update_processed_food_tool,
        list_my_blog_posts_tool,
        create_blog_post_tool,
        list_my_services_tool,
        add_service_listing_tool,
        list_seller_orders_tool,
        confirm_seller_order_tool,
        reject_seller_order_tool,
        ship_seller_order_tool,
        list_cold_chain_readings_tool,
        log_cold_chain_reading_tool,
        list_cold_chain_shipments_tool,
        list_my_certifications_tool,
        add_certification_tool,
    )
    BUSINESS_DATA_AVAILABLE = True
except Exception as _e:
    print(f"[nodes] business_data unavailable: {_e}")
    business_data_tools = []
    get_business_profile_tool = None
    update_business_profile_tool = None
    list_my_animals_detail_tool = None
    update_animal_tool = None
    list_produce_inventory_tool = None
    update_produce_listing_tool = None
    list_meat_inventory_tool = None
    update_meat_listing_tool = None
    list_processed_food_tool = None
    update_processed_food_tool = None
    list_my_blog_posts_tool = None
    create_blog_post_tool = None
    list_my_services_tool = None
    add_service_listing_tool = None
    list_seller_orders_tool = None
    confirm_seller_order_tool = None
    reject_seller_order_tool = None
    ship_seller_order_tool = None
    list_cold_chain_readings_tool = None
    log_cold_chain_reading_tool = None
    list_cold_chain_shipments_tool = None
    list_my_certifications_tool = None
    add_certification_tool = None
    BUSINESS_DATA_AVAILABLE = False

try:
    from knowledge_base import (
        knowledge_base_tools,
        search_plants_tool,
        get_plant_detail_tool,
        search_ingredients_tool,
        get_ingredient_detail_tool,
        get_animal_detail_tool,
    )
    KNOWLEDGE_BASE_AVAILABLE = True
except Exception as _e:
    print(f"[nodes] knowledge_base unavailable: {_e}")
    knowledge_base_tools = []
    search_plants_tool = None
    get_plant_detail_tool = None
    search_ingredients_tool = None
    get_ingredient_detail_tool = None
    get_animal_detail_tool = None
    KNOWLEDGE_BASE_AVAILABLE = False

try:
    from actions import (
        actions_tools,
        draft_produce_listing_tool,
        draft_meat_listing_tool,
        draft_processed_food_listing_tool,
        draft_event_tool,
        draft_blog_post_tool,
    )
    ACTIONS_AVAILABLE = True
except Exception as _e:
    print(f"[nodes] actions unavailable: {_e}")
    actions_tools = []
    draft_produce_listing_tool = None
    draft_meat_listing_tool = None
    draft_processed_food_listing_tool = None
    draft_event_tool = None
    draft_blog_post_tool = None
    ACTIONS_AVAILABLE = False

try:
    from agronomy import (
        agronomy_tools,
        planting_calendar_tool,
        irrigation_schedule_tool,
        manure_pairing_tool,
    )
    AGRONOMY_AVAILABLE = True
except Exception as _e:
    print(f"[nodes] agronomy unavailable: {_e}")
    agronomy_tools = []
    planting_calendar_tool = None
    irrigation_schedule_tool = None
    manure_pairing_tool = None
    AGRONOMY_AVAILABLE = False

try:
    from chef import (
        chef_tools,
        save_recipe_tool,
        cost_recipe_tool,
        seasonal_menu_tool,
        set_par_tool,
        check_par_levels_tool,
        draft_restock_order_tool,
        provenance_cards_tool,
    )
    CHEF_AVAILABLE = True
except Exception as _e:
    print(f"[nodes] chef unavailable: {_e}")
    chef_tools = []
    save_recipe_tool = None
    cost_recipe_tool = None
    seasonal_menu_tool = None
    set_par_tool = None
    check_par_levels_tool = None
    draft_restock_order_tool = None
    provenance_cards_tool = None
    CHEF_AVAILABLE = False

try:
    from pest_detection import pest_detection_tools, get_recent_pest_detections_tool
    PEST_DETECTION_AVAILABLE = True
except Exception as _e:
    print(f"[nodes] pest_detection unavailable: {_e}")
    pest_detection_tools = []
    get_recent_pest_detections_tool = None
    PEST_DETECTION_AVAILABLE = False

try:
    from push_notifications import push_notification_tools, send_push_notification_tool
    PUSH_NOTIFICATIONS_AVAILABLE = True
except Exception as _e:
    print(f"[nodes] push_notifications unavailable: {_e}")
    push_notification_tools = []
    send_push_notification_tool = None
    PUSH_NOTIFICATIONS_AVAILABLE = False

try:
    from weather_alerts import weather_alert_tools, check_my_weather_alerts_tool
    WEATHER_ALERTS_AVAILABLE = True
except Exception as _e:
    print(f"[nodes] weather_alerts unavailable: {_e}")
    weather_alert_tools = []
    check_my_weather_alerts_tool = None
    WEATHER_ALERTS_AVAILABLE = False

try:
    from history_store import history_tools, get_my_recent_history_tool
    HISTORY_STORE_AVAILABLE = True
except Exception as _e:
    print(f"[nodes] history_store unavailable: {_e}")
    history_tools = []
    get_my_recent_history_tool = None
    HISTORY_STORE_AVAILABLE = False

try:
    from jokes import joke_tools, tell_joke_tool
    JOKES_AVAILABLE = True
except Exception as _e:
    print(f"[nodes] jokes unavailable: {_e}")
    joke_tools = []
    tell_joke_tool = None
    JOKES_AVAILABLE = False

VALID_ADVISORY_TYPES = {"weather", "livestock", "crops", "mixed", "news", "bakasura", "joke"}
ADVISORY_TYPE_ALIASES = {
    "crop": "crops",
    "crops": "crops",
    "livestock": "livestock",
    "animal": "livestock",
    "animals": "livestock",
    "weather": "weather",
    "mixed": "mixed",
    "news": "news",
    "market": "news",
    "market news": "news",
    "headline": "news",
    "headlines": "news",
    "current events": "news",
    "bakasura": "bakasura",
    "bakasura-docs": "bakasura",
    "docs": "bakasura",
    "joke": "joke",
    "jokes": "joke",
    "funny": "joke",
}


def normalize_advisory_type(value: Optional[str]) -> Optional[str]:
    """Normalize free-form advisory labels into supported route types."""
    if not value:
        return None
    normalized = ADVISORY_TYPE_ALIASES.get(value.strip().lower())
    return normalized if normalized in VALID_ADVISORY_TYPES else None


def _keyword_present(text: str, keyword: str) -> bool:
    if " " in keyword:
        return keyword in text
    return bool(re.search(rf"\b{re.escape(keyword)}s?\b", text))


def _count_keyword_matches(text: str, keywords: List[str]) -> int:
    return sum(1 for keyword in keywords if _keyword_present(text, keyword))


def _infer_answer_slot(question_text: str, has_existing_issue: bool) -> str:
    """
    Infer which state slot an interrupt answer should update.
    Prevents adding location/crop answers into current_issues.
    """
    q_lower = question_text.lower()
    if any(token in q_lower for token in ["location", "where", "region", "city", "state", "country"]):
        return "location"
    if any(token in q_lower for token in ["size", "acre", "hectare", "land"]):
        return "farm_size"
    if _is_goal_question(question_text):
        return "issue"
    if any(token in q_lower for token in ["crop", "growing", "plant", "livestock", "animal", "breed", "raising", "field"]):
        return "crops"
    if any(token in q_lower for token in ["issue", "problem", "symptom", "challenge", "goal", "objective", "purpose"]):
        return "issue"
    # If we already have an issue and question does not target a known slot,
    # treat this answer as additional issue detail.
    return "issue"


def _is_goal_question(question_text: str) -> bool:
    q_lower = question_text.lower()
    goal_markers = [
        "primary goal", "goal", "objective", "purpose", "looking to",
        "trying to", "aim", "target", "why",
    ]
    return any(marker in q_lower for marker in goal_markers)


def _build_fallback_options(question_text: str, answer_slot: str) -> List[str]:
    """Build deterministic, context-aware options when LLM options are weak/inconsistent."""
    q_lower = question_text.lower()

    if answer_slot == "location":
        return ["North region", "South region", "Central region", "Other"]
    if answer_slot == "farm_size":
        return ["Small (1-5 acres)", "Medium (5-20 acres)", "Large (20+ acres)", "Other"]
    if _is_goal_question(question_text):
        return [
            "Weed or pest control",
            "Improve soil fertility",
            "Increase farm income",
            "Other goal",
        ]

    if any(token in q_lower for token in ["which animal", "which livestock", "type of animal", "type of livestock", "breed"]):
        return ["Ducks", "Buffalo/Cattle", "Goats/Sheep", "Not sure yet"]
    if any(token in q_lower for token in ["what crop", "which crop", "growing", "planting", "field type"]):
        return ["Rice/Paddy", "Wheat/Maize", "Vegetables", "Other"]
    if any(token in q_lower for token in ["issue", "problem", "symptom", "challenge"]):
        return ["Pest attack", "Disease symptoms", "Low yield", "Other"]

    return ["Improve productivity", "Reduce risk", "Increase income", "Other"]


def _options_are_consistent(question_text: str, options: List[str], answer_slot: str) -> bool:
    """Guardrail to ensure options directly answer the question being asked."""
    if not options or len(options) < 3:
        return False

    opts_lower = [opt.lower().strip() for opt in options if opt and opt.strip()]
    if len(opts_lower) < 3:
        return False
    if any(opt.startswith("option ") for opt in opts_lower):
        return False

    if answer_slot == "location":
        location_markers = ["region", "city", "state", "north", "south", "central"]
        return sum(1 for opt in opts_lower if any(marker in opt for marker in location_markers)) >= 2

    if answer_slot == "farm_size":
        size_markers = ["small", "medium", "large", "acre", "hectare"]
        return sum(1 for opt in opts_lower if any(marker in opt for marker in size_markers)) >= 2

    if _is_goal_question(question_text):
        goal_markers = [
            "control", "improve", "increase", "reduce", "manage",
            "income", "fertility", "productivity", "protection", "goal",
        ]
        return sum(1 for opt in opts_lower if any(marker in opt for marker in goal_markers)) >= 2

    return True


# ============================================================================
# SAIGE PERSONA
# ============================================================================

_SAIGE_PERSONA = """
IDENTITY & VOICE — You are Saige (pronounced exactly like "Sage" — the herb, rhymes with "page"). A woman in her early 40s, Caucasian, with a deep outdoor tan from years of working on farms and ranches. You carry a slight Texan accent — nothing heavy, just enough to add warmth and color to the way you talk.

ROLE — You are a professional farm and food advisor. You help farmers with planting, growing, harvesting, livestock care, soil health, and marketing. You also help restaurant owners and food suppliers source local ingredients and build farm-to-table connections.

PERSONALITY —
- Warm and relationship-focused. You remember people's farms, their animals, their challenges. You ask follow-up questions when it helps.
- Professional but never stiff. You mix technical agricultural vocabulary with plain, friendly language.
- Politically neutral. You never take sides on policy, GMOs, organic vs. conventional, or land use debates — you give the pros and cons and let the farmer decide.
- Pragmatic and solution-oriented. You focus on what actually works, not what's theoretically ideal.
- Approachable. You're the advisor farmers call when they're worried about their crops or an animal is off — you calm them down and help them think through it.

SPEECH STYLE — Casual Texan warmth mixed with technical precision when the topic calls for it.
- Use "y'all" naturally (not constantly, just when addressing a group or being warm).
- Occasional phrases like "sure thing", "you bet", "I reckon", "right off the bat", "holler at me if".
- Keep answers concise by default. Go detailed when the topic is complex or the farmer seems to need depth.
- Never be preachy or lecture. Give the answer, give the options, respect the farmer's judgment.
- Do NOT open responses with "Hello", "Hi there", "Great question!", or any filler greeting. Start with the substance.
""".strip()


# ============================================================================
# UNIFIED ADVISORY ENGINE (DRY Principle)
# ============================================================================

def run_advisory_agent(state: FarmState, role_prompt: str, rag_systems: list = None) -> Dict[str, Any]:
    """
    Unified engine for all advisory nodes (Crop, Livestock, Mixed).
    Handles context gathering, RAG retrieval, and the Tool-Calling Loop.
    """
    print(f"\n[Advisory Agent] Processing with role: {role_prompt[:50]}...")

    # Handle general questions directly without RAG or farming prompts
    _assessment = state.get("assessment_summary", "")
    _history = state.get("history") or []
    _msg = ""
    for _h in reversed(_history):
        if _h.startswith("User:"):
            _msg = _h.replace("User:", "", 1).strip()
            break
    if not _msg:
        _msg = str(state.get("user_message") or "")
    _identity_kw = ("what is my name", "what's my name", "whats my name", "my name",
                    "what is your name", "what's your name", "who are you", "your name",
                    "tell me about yourself", "introduce yourself", "what can you do",
                    "business account", "signed in with", "which account", "what account",
                    "businessid", "business_id", "business id", "my business",
                    "peopleid", "people_id", "people id", "user id", "userid",
                    "my email", "what is my email", "my phone", "what is my phone",
                    "my account", "my profile", "who am i")
    _is_general_path = (
        _is_account_identity_query(_msg)
        or _assessment.startswith("General question:")
        or (
            _assessment.startswith("Farmer seeks assistance with:") and
            any(k in _assessment.lower() for k in _identity_kw) and
            not any(k in _assessment.lower() for k in ("field", "ndvi", "crop", "livestock", "weather", "soil"))
        )
    )
    if _is_general_path:
        print(f"[Advisory Agent] General/identity question - answering directly")
        _pid = state.get("people_id")
        _ml = _msg.lower()

        # Joke fast-path — call tell_joke_tool directly, no LLM needed
        if JOKES_AVAILABLE and tell_joke_tool and any(k in _ml for k in ("joke", "something funny", "make me laugh")):
            print(f"[Advisory Agent] Joke request fast-path for people_id={_pid}")
            _joke = tell_joke_tool.invoke({"people_id": str(_pid or "")})
            return {"diagnosis": _joke, "recommendations": []}

        # Saige self-identity — pre-canned, no LLM needed
        _saige_identity_kw = ("what is your name", "what's your name", "whats your name",
                              "your name", "who are you", "what are you",
                              "tell me about yourself", "introduce yourself",
                              "what can you do", "what can you help", "how do you work")
        # Don't treat "what is my name" as Saige self-intro
        if any(k in _ml for k in _saige_identity_kw) and "my name" not in _ml and "my email" not in _ml:
            _uname = (state.get("user_name") or "").split()[0] if state.get("user_name") else ""
            _greeting = f"Hey {_uname}! " if _uname else ""
            return {
                "diagnosis": (
                    f"{_greeting}My name is Saige — pronounced just like 'Sage', the herb. "
                    "I'm a farm and food advisor. I help farmers with planting, growing, harvesting, "
                    "livestock care, soil health, field monitoring, and marketing. "
                    "I can also help restaurant owners and food suppliers connect with local farms. "
                    "What can I help you with today?"
                ),
                "recommendations": [],
            }

        if _is_account_identity_query(_msg) or any(
            k in _ml for k in ("my name", "my email", "my phone", "people id", "user id", "business id", "my account", "my profile")
        ):
            _profile = {}
            try:
                from user_profile import get_account_profile
                _profile = get_account_profile(str(_pid or ""), state.get("business_id")) or {}
            except Exception:
                pass
            _answer = _format_account_answer(
                _msg,
                people_id=str(_pid or ""),
                business_id=state.get("business_id"),
                user_name=str(state.get("user_name") or ""),
                profile=_profile,
            )
            return {"diagnosis": _answer, "recommendations": []}

        try:
            _name_hint = state.get("user_name") or ""
            _name_ctx = (
                f"You are talking with {_name_hint}. "
                if _name_hint else ""
            )
            _resp = llm.invoke(
                f"{_SAIGE_PERSONA}\n\n"
                f"{_name_ctx}"
                "The user is mid-conversation. Answer the question directly and concisely. "
                "Do NOT invent the user's email, phone, name, or IDs. "
                "Do NOT introduce yourself, do NOT greet the user, and do NOT open with phrases like "
                "'Hello there', 'Hi', 'I'm Saige', or 'your friendly assistant'. "
                "Skip the preamble — start with the answer.\n\n"
                f"Question: {_msg}"
            )
            _answer = _resp.content if hasattr(_resp, "content") else str(_resp)
        except Exception as _e:
            _answer = "I am here to help! Could you rephrase your question?"
        return {"diagnosis": _answer, "recommendations": []}

    # 1. Gather Context from State
    location = state.get("location", "Unknown")
    crops = state.get("crops") or []
    issues = state.get("current_issues") or []
    assessment = state.get("assessment_summary", "")
    history = state.get("history") or []
    soil_info = state.get("soil_info") or {}
    _image_data = state.get("image_data") or None  # base64 image for multimodal queries

    latest_user_message = ""
    for msg in reversed(history):
        if msg.startswith("User:"):
            latest_user_message = msg.replace("User:", "", 1).strip()
            break
    if not latest_user_message:
        latest_user_message = ", ".join(issues) if issues else "General inquiry"

    # ── Lightweight intent router ────────────────────────────────────────────
    # Detect the primary intent from the user message so we can prune RAG and
    # the tool list before doing any expensive work.  Matches are broad enough
    # to catch paraphrases without needing an LLM call.
    _rl = latest_user_message.lower()

    _MAP_KW_MATCH = any(k in _rl for k in (
        "zoom to", "zoom in to", "zoom into", "zoom the map", "zoom map",
        "zoom in on", "zoom over to", "zoom over", "zoom out",
        "go to zip", "fly to", "center on", "center map",
        "navigate to", "pan to", "jump to", "move map to", "focus on zip",
        "show zip", "show me on the map", "take me to zip", "go to the zip",
        "move to the map", "go to the map", "take the map to",
        "show me where", "take me to", "bring the map",
        "move over to", "move the map", "move to the",
    ))
    # Address pattern: "1365 Spring Street Medford", "242 Oak Ave Portland OR", etc.
    _MAP_ADDR_MATCH = bool(re.search(
        r'\b\d{2,5}\b.{0,40}\b(street|st|avenue|ave|road|rd|boulevard|blvd|'
        r'drive|dr|lane|ln|way|court|ct|place|pl|highway|hwy|parkway|pkwy|route|rte)\b',
        _rl, re.IGNORECASE,
    ))
    _INTENT_MAP = _MAP_KW_MATCH or _MAP_ADDR_MATCH

    _INTENT_BUSINESS = any(k in _rl for k in (
        "my animal", "my listing", "my inventory", "my order", "my service",
        "my blog", "my cert", "my profile", "my account", "my vehicle",
        "my truck", "my fleet", "my ranch info", "my business",
        "cold chain vehicle", "list vehicle", "fleet vehicle",
        "cold chain reading", "temperature reading",
        "my grant", "my tracker", "grant track", "tracking grant",
        "what grant", "which grant", "grant appli", "program appli",
        "what program", "programs i track", "grants i track",
        "shelf life", "shelf-life", "cargo freshness", "temperature excursion",
        "produce still good", "shipment viable", "days left", "how fresh",
        "cold chain sla", "sla impact", "degradation",
    ))

    _INTENT_PRECISION_AG = any(k in _rl for k in (
        "my field", "ndvi", "evi", "savi", "my crop monitoring",
        "field analysis", "field alert", "field health", "field soil",
        "biomass confidence", "improve confidence", "field zones",
        "management zone", "yield forecast", "gdd", "growing degree",
        "irrigation recom", "field weather", "scouting report",
        "field activity", "field assessment", "log scouting",
        "log field", "add soil sample",
    ))

    _INTENT_ACCOUNTING = any(k in _rl for k in (
        "invoice", "overdue", "payment", "accounts receivable",
        "accounts payable", "accounting snapshot", "my books",
        "how are the books", "open invoice", "customer payment",
        "recent payment", "cash flow", "sponsorship revenue",
        "booth service revenue", "lead summary", "event lead",
        "event registration", "floor plan status", "coi",
        "certificate of insur",
    ))

    _INTENT_KNOWLEDGE_ONLY = not (_INTENT_MAP or _INTENT_BUSINESS
                                  or _INTENT_PRECISION_AG or _INTENT_ACCOUNTING)

    # Suppress RAG for all non-knowledge intents — those queries don't benefit
    # from vector retrieval and it just wastes 500-800 ms.
    if not _INTENT_KNOWLEDGE_ONLY:
        rag_systems = []
        print(f"[Intent Router] RAG suppressed — intent: "
              f"map={_INTENT_MAP} biz={_INTENT_BUSINESS} "
              f"precag={_INTENT_PRECISION_AG} acct={_INTENT_ACCOUNTING}")
    # ── end intent router ─────────────────────────────────────────────────────

    recent_turns = "\n".join(history[-8:]) if history else "Not available"

    soil_lines = []
    if isinstance(soil_info, dict) and soil_info:
        for key in ["ph", "electrical_conductivity", "cec", "organic_matter", "nitrogen", "phosphorus", "potassium"]:
            if key in soil_info and soil_info[key] is not None:
                soil_lines.append(f"- {key}: {soil_info[key]}")
        if soil_info.get("raw_text"):
            soil_lines.append(f"- raw_report: {str(soil_info['raw_text'])[:600]}")
    soil_section = "Soil test data:\n" + "\n".join(soil_lines) if soil_lines else "Soil test data: Not provided"

    # 2. RAG Retrieval (Centralized hybrid)
    rag_context = ""
    rag_citations: List[Dict[str, Any]] = []
    rag_timings: Dict[str, float] = {}
    if rag_systems and RAG_AVAILABLE:
        query_text = f"{', '.join(crops)} {', '.join(issues)} {assessment} {latest_user_message}"
        context_parts = []
        for rag_sys in rag_systems:
            try:
                rag_sys.initialize()
                hits = rag_sys.search(query_text)
                if hasattr(rag_sys, "last_timings"):
                    for k, v in (rag_sys.last_timings or {}).items():
                        rag_timings[f"{rag_sys._label}:{k}"] = v
                if hits:
                    for h in hits:
                        rag_citations.append({
                            "doc_id": h.get("doc_id"),
                            "chunk_id": h.get("chunk_id"),
                            "title": h.get("title"),
                            "url": h.get("url"),
                            "score": h.get("score"),
                            "quote": h.get("quote") or (h.get("content") or "")[:180],
                            "source": h.get("collection") or rag_sys._label,
                            "snippet": (h.get("content") or "")[:180],
                        })
                    ctx = rag_sys.get_context_for_query(query_text) if not hits else None
                    # Prefer formatting from hits to avoid double retrieve when cache cold
                    if hits:
                        lines = [f"Relevant {rag_sys._label} information from database:\n"]
                        for i, h in enumerate(hits, 1):
                            lines.append(
                                f"{i}. [{h.get('chunk_id') or h.get('doc_id') or i}] "
                                f"({h.get('title') or rag_sys._label}) {h.get('content', '')}"
                            )
                        context_parts.append("\n".join(lines))
                    elif ctx:
                        context_parts.append(ctx)
                    print(f"[Advisory Agent] RAG context retrieved from {rag_sys._label} hits={len(hits)}")
            except Exception as e:
                print(f"[Advisory Agent] RAG error ({rag_sys._label}): {e}")
        rag_context = "\n\n".join(context_parts)

    # 2.5  Business Context Pre-fetch (conditional)
    # Only fetch when business data is likely relevant — skip for pure weather/crop/livestock
    # advisory queries that have no business-data keywords, to avoid 2 unnecessary DB round-trips.
    business_snapshot = ""
    _bid_prefetch = state.get("business_id")
    _lum_for_prefetch = latest_user_message.lower()
    _biz_relevant_kw = (
        "my animal", "my listing", "my inventory", "my order", "my service",
        "my blog", "my cert", "my profile", "my account", "my vehicle", "my truck",
        "my fleet", "my ranch", "my farm data", "my business", "marketplace",
        "cold chain", "produce", "meat", "processed food", "sell", "selling",
        "shipment", "delivery", "business name", "business info", "business profile",
        "my grant", "my tracker", "grant track", "tracking grant", "what grant",
        "which grant", "grant appli", "program appli", "grants i track",
        "zoom", "fly to", "map", "navigate", "field", "precision", "[page:",
    )
    _prefetch_needed = any(k in _lum_for_prefetch for k in _biz_relevant_kw)
    # Also pre-fetch when page context is clearly business-oriented
    _page_ctx = ""
    for _h in reversed(history[-4:] if history else []):
        if "[Page:" in _h:
            _page_ctx = _h.lower()
            break
    _biz_page_kw = (
        "seller", "marketplace", "orders", "inventory", "cold chain", "animals",
        "livestock", "blog", "services", "certifications", "business profile", "ranch",
        "farmer settlement", "csa", "aggregator",
    )
    if not _prefetch_needed and _page_ctx:
        _prefetch_needed = any(k in _page_ctx for k in _biz_page_kw)

    if _bid_prefetch and BUSINESS_DATA_AVAILABLE and _prefetch_needed:
        try:
            _profile_raw = get_business_profile_tool.invoke({"business_id": int(_bid_prefetch)})
            _counts_raw  = count_my_animals_tool.invoke({"business_id": int(_bid_prefetch)})
            business_snapshot = (
                "CURRENT BUSINESS CONTEXT (live from database — use this to answer questions "
                "about the farm without calling additional tools unless the user needs detail):\n"
                + _profile_raw
                + "\n\n"
                + _counts_raw
            )
            print(f"[Advisory Agent] Business snapshot pre-fetched for BusinessID={_bid_prefetch}")
        except Exception as _pf_err:
            print(f"[Advisory Agent] Business pre-fetch failed: {_pf_err}")
    elif _bid_prefetch and not _prefetch_needed:
        print(f"[Advisory Agent] Business pre-fetch skipped (query not business-data-related)")

    # 3. Construct Full Prompt
    rag_section = f"RELEVANT KNOWLEDGE BASE:\n{rag_context}" if rag_context else (
        "RELEVANT KNOWLEDGE BASE:\n(No retrieved documents. Do not invent sources or citations; "
        "say when you lack KB evidence and rely on general agronomy caution.)"
    )
    if rag_context:
        rag_section += (
            "\n\nGROUNDING: When you use knowledge-base facts, reference chunk ids in brackets "
            "when helpful. Do not fabricate document titles or URLs."
        )

    # Community learnings from data flywheel (skip for tool-only intents)
    _community_section = ""
    if not (_INTENT_MAP or _INTENT_PRECISION_AG or _INTENT_ACCOUNTING or _INTENT_BUSINESS):
        try:
            from learning import get_community_context as _get_community_ctx
            _community_section = _get_community_ctx(latest_user_message, n=3)
        except Exception as _lrn_err:
            pass  # flywheel unavailable — degrade silently
    else:
        print("[Advisory Agent] Community learnings skipped (tool-only intent)")

    _people_id_ctx = state.get("people_id") or ""
    _business_id_ctx = state.get("business_id") or ""
    _user_name_ctx = (state.get("user_name") or "").strip()
    _business_name_ctx = ""
    if _business_id_ctx:
        try:
            from user_profile import get_business_name as _get_bname_ctx
            _business_name_ctx = _get_bname_ctx(_business_id_ctx) or ""
        except Exception:
            pass
    _biz_label = (
        f"{_business_name_ctx} (ID {_business_id_ctx})" if _business_name_ctx
        else (_business_id_ctx or "unknown")
    )
    identity_section = (
        f"AUTHENTICATED IDENTITY (already known — do NOT ask the user for these):\n"
        + (f"- Name: {_user_name_ctx}\n" if _user_name_ctx else "")
        + f"- PeopleID: {_people_id_ctx or 'unknown'}\n"
        f"- Business: {_biz_label}\n"
        "Every tool that needs people_id or business_id receives them automatically from "
        "this session. Call the tool directly — never ask the user to 'link their account' "
        "or provide these IDs. If a tool returns no data, say so plainly; do not blame "
        "missing authentication.\n"
        + (f"Address this farmer by their first name ({_user_name_ctx.split()[0]}) naturally "
           "when it fits the tone — not on every message, just when it adds warmth."
           if _user_name_ctx else "")
    )

    ltm = state.get("long_term_memory") or {}
    memory_section = ""
    if ltm and any(ltm.values()):
        parts = ["LONG-TERM MEMORY (facts from prior conversations with this farmer):"]
        if ltm.get("locations"):
            parts.append(f"- Known locations: {', '.join(ltm['locations'][:5])}")
        if ltm.get("crops"):
            parts.append(f"- Previously discussed crops/livestock: {', '.join(ltm['crops'][:10])}")
        if ltm.get("farm_sizes"):
            parts.append(f"- Farm size(s) shared: {', '.join(ltm['farm_sizes'][:3])}")
        if ltm.get("recent_topics"):
            parts.append("- Recent concerns they've raised:")
            for t in ltm["recent_topics"]:
                parts.append(f"  • {(t or '')[:140]}")
        if ltm.get("known_issues"):
            parts.append("- Recurring problems on this farm:")
            for issue in ltm["known_issues"][:5]:
                parts.append(f"  • {(issue or '')[:120]}")
        if ltm.get("recent_solutions"):
            parts.append("- Solutions Saige has previously recommended to this farmer:")
            for sol in ltm["recent_solutions"][:4]:
                parts.append(f"  • {(sol or '')[:150]}")
        parts.append(
            "Use these facts naturally — don't re-ask for location/crops you already know. "
            "Build on past recommendations rather than starting from scratch each time. "
            "If the current message references something previously discussed, carry it forward."
        )
        memory_section = "\n".join(parts)

    # Org-level shared memory (aggregated from all team members + Cassia onboarding profile)
    org_mem = state.get("org_memory") or {}
    org_memory_section = ""
    if org_mem and any(org_mem.values()):
        oparts = ["ORG MEMORY (what Saige knows about this farm/organisation from all team members):"]
        if org_mem.get("locations"):
            oparts.append(f"- Farm location(s): {', '.join(org_mem['locations'][:4])}")
        if org_mem.get("crops"):
            oparts.append(f"- Crops/livestock this farm works with: {', '.join(org_mem['crops'][:12])}")
        if org_mem.get("farm_sizes"):
            oparts.append(f"- Farm size(s): {', '.join(org_mem['farm_sizes'][:2])}")
        # Structured fields seeded by Cassia onboarding
        if org_mem.get("channels"):
            ch = org_mem["channels"]
            oparts.append(f"- Sales channels: {', '.join(ch) if isinstance(ch, list) else ch}")
        if org_mem.get("headache"):
            oparts.append(f"- Stated top operational challenge: {org_mem['headache'][:200]}")
        if org_mem.get("plan_tier"):
            oparts.append(f"- Subscription tier: {org_mem['plan_tier']}")
        if org_mem.get("revenue_model"):
            oparts.append(f"- Revenue model: {org_mem['revenue_model']}")
        if org_mem.get("uses_agronomist") is not None:
            agro_str = "works with outside agronomists" if org_mem["uses_agronomist"] else "manages agronomy in-house"
            oparts.append(f"- Agronomy approach: {agro_str}")
        if org_mem.get("business_type"):
            oparts.append(f"- Business type: {org_mem['business_type']}")
        if org_mem.get("known_org_issues"):
            oparts.append("- Issues other team members have raised about this farm:")
            for issue in org_mem["known_org_issues"][:5]:
                oparts.append(f"  • {(issue or '')[:120]}")
        if org_mem.get("org_solutions"):
            oparts.append("- Solutions that have been recommended to this team:")
            for sol in org_mem["org_solutions"][:4]:
                oparts.append(f"  • {(sol or '')[:150]}")
        if org_mem.get("recent_topics"):
            oparts.append("- Recent topics the team has asked Saige about:")
            for t in org_mem["recent_topics"][:4]:
                oparts.append(f"  • {(t or '')[:120]}")
        oparts.append(
            "Use org memory to avoid re-asking about the farm's basic setup. "
            "If a team member's colleague already established a fact (location, crop list, etc.), "
            "treat it as known. Keep individual team members' personal contexts separate."
        )
        org_memory_section = "\n".join(oparts)

    # Onboarding context from Cassia post-checkout discovery interview
    onboarding_section = ""
    _onboarding_ctx = ltm.get("onboarding_context", "") if ltm else ""
    if _onboarding_ctx:
        onboarding_section = (
            "ONBOARDING PROFILE (captured when this farmer set up their account — "
            "treat these facts as already established; do not ask the farmer to re-explain "
            "their crops, fields, channels, or main challenge):\n"
            + _onboarding_ctx
        )

    # Build a query-specific directive when the user is asking about their own data
    # so the LLM calls the right tool instead of guessing from training knowledge.
    _lum = latest_user_message.lower()
    _tool_directive = ""
    _vehicle_kw = ("vehicle", "truck", "van", "trailer", "fleet", "cold chain", "refrigerat")
    _profile_kw = ("business profile", "business info", "my profile", "my account info", "business details")
    _inventory_kw = ("produce inventory", "meat inventory", "processed food", "my listings", "my inventory", "what do i sell", "what am i selling")
    _order_kw = ("my order", "incoming order", "pending order", "orders i have", "orders to ship", "what orders")
    _service_kw = ("my service", "services i offer", "service listing", "service price")
    _blog_kw = ("my blog", "blog post", "my articles", "my posts")
    _cert_kw = ("my certification", "my cert", "certifications i have", "organic cert", "cert expir")
    _reading_kw = ("temperature reading", "temp reading", "cold chain reading", "vehicle reading")
    _map_kw = ("zoom to", "zoom in on", "zoom in to", "zoom into", "zoom the map", "zoom map",
               "zoom over to", "zoom over", "zoom out",
               "go to zip", "fly to", "center on", "center map", "navigate to",
               "show me on the map", "pan to", "jump to", "move map to", "focus on zip", "show zip",
               "zoom in zip", "take me to zip", "go to the zip",
               "take me to", "bring the map", "show me where",
               "move over to", "move the map", "move to the")
    if any(k in _lum for k in _vehicle_kw):
        _tool_directive = (
            "\n⚠ TOOL REQUIRED: The user is asking about their cold chain fleet. "
            "You MUST call list_cold_chain_vehicles_tool() immediately. "
            "Do NOT describe or list vehicles from memory — only report what the tool returns.\n"
        )
    elif any(k in _lum for k in _profile_kw):
        _tool_directive = (
            "\n⚠ TOOL REQUIRED: Call get_business_profile_tool() to fetch the current business profile. "
            "Never invent or assume profile details — only report what the tool returns.\n"
        )
    elif any(k in _lum for k in _order_kw):
        _tool_directive = (
            "\n⚠ TOOL REQUIRED: Call list_seller_orders_tool() to fetch real order data. "
            "Never invent order details — only report what the tool returns.\n"
        )
    elif any(k in _lum for k in _inventory_kw):
        _tool_directive = (
            "\n⚠ TOOL REQUIRED: Call the appropriate inventory tool "
            "(list_produce_inventory_tool / list_meat_inventory_tool / list_processed_food_tool / list_my_listings_tool) "
            "before answering. Never invent inventory data.\n"
        )
    elif any(k in _lum for k in _service_kw):
        _tool_directive = (
            "\n⚠ TOOL REQUIRED: Call list_my_services_tool() to fetch service listings. "
            "Never invent service details.\n"
        )
    elif any(k in _lum for k in _blog_kw):
        _tool_directive = (
            "\n⚠ TOOL REQUIRED: Call list_my_blog_posts_tool() to fetch blog posts. "
            "Never invent blog content.\n"
        )
    elif any(k in _lum for k in _cert_kw):
        _tool_directive = (
            "\n⚠ TOOL REQUIRED: Call list_my_certifications_tool() to fetch certifications. "
            "Never invent certification details.\n"
        )
    elif any(k in _lum for k in _reading_kw):
        _tool_directive = (
            "\n⚠ TOOL REQUIRED: Call list_cold_chain_readings_tool() to fetch temperature readings. "
            "Never invent temperature data.\n"
        )
    elif any(k in _lum for k in _map_kw):
        _tool_directive = (
            "\n⚠ TOOL REQUIRED: The user wants the map to zoom/navigate to a location. "
            "You MUST call geocode_location_tool(query=<the location>) immediately. "
            "Do NOT explain coordinates or describe the process — just call the tool and confirm the place name. "
            "The [MAP_CMD] in the tool result will move the map automatically.\n"
        )

    _image_note = (
        "\n[IMAGE ATTACHED]: The farmer has shared a photo with this message. "
        "The image is included as a multimodal attachment — analyze it directly and incorporate "
        "your visual observations into your response (identify the plant/animal/symptom/condition visible).\n"
        if _image_data else ""
    )

    full_prompt = f"""{_SAIGE_PERSONA}

{role_prompt}

{identity_section}
{business_snapshot}
{_tool_directive}
{onboarding_section}
{memory_section}
{org_memory_section}
{_image_note}
Farmer's latest message: {latest_user_message}
Farmer's tracked issues: {', '.join(issues) if issues else 'General inquiry'}
Current Context:
- Crops/Livestock: {', '.join(crops) if crops else 'Not specified'}
- Location: {location}
{soil_section}

Recent conversation turns:
{recent_turns}

{rag_section}

{_community_section}

You have access to a weather tool. Use it if weather conditions are critical for the advice
(e.g., sowing time, heat stress in animals, pest humidity thresholds).

You also have companion-planting tools: companion_planting_tool(crop) returns friends/foes for
one crop; check_companion_pair_tool(crop_a, crop_b) tells you if two crops get along. Use them
whenever the user asks about planting layouts, polycultures, Three Sisters, "can I plant X with Y",
bed planning, or rotation companions.

Additional tools available:
- crop_name_tool(name): translate a crop name across languages/regions (e.g., 'brinjal', 'melongene', 'courgette', 'Solanum lycopersicum'). Use when a farmer uses an unfamiliar crop name.
- weather_mitigation_tool(hazard, phase): concrete step-by-step plan for weather extremes (frost/drought/heat/flood/hail/wind/wildfire_smoke/cold_snap) at a given phase (planning/imminent/active/recovery). Use for "what do I do about [weather event]".
- region_crops_tool(climate, zone, lat, lon): what to grow in a region. Pass ONE of climate (tropical/subtropical/temperate/continental/mediterranean/arid/highland/boreal), USDA zone number, or lat/lon. Use for "what should I grow here".
- soil_challenge_tool(ph, organic_matter_pct, nitrogen_ppm, phosphorus_ppm, potassium_ppm, cec_meq, salinity_dsm, moisture_pct, bulk_density_gcc, sodium_pct_cec, crop): analyze a soil test and recommend remediation. Use when the user shares soil numbers or asks "what's wrong with my soil".
- price_forecast_tool(commodity, months_ahead): short-horizon US commodity price forecast (corn/soy/wheat/cotton/rice/cattle/hog/milk/egg/hay/etc.). Use for marketing, selling-timing, or revenue planning questions.
- subsidies_tool(category, keyword): US federal farm subsidy / cost-share / grant / loan programs (EQIP, CSP, CRP, ARC/PLC, WFRP, BFRDP, VAPG, REAP, SARE). Use when user asks about government funding or assistance.
- insurance_tool(crop): US federal crop-insurance products (RP/YP/APH/WFRP/MP/PRF/LRP/LGM/DRP/NAP) for a specific crop or livestock class. Use when user asks about insurance or risk management.
PRECISION AG — Field Data (resolve names before asking for IDs):
- list_my_fields_tool(): list satellite-monitored fields (field ID, name, crop, size, planting date).
- resolve_field_by_name_tool(name): map a field name like "test field 4" to FieldID. ALWAYS call this when the user names a field instead of giving a numeric ID. NEVER ask the user for a field ID if a name is present — resolve it.
- get_field_analysis_tool(field_id): latest NDVI/EVI analysis. Call after resolving the name to an ID.
- get_field_analysis_tool(field_id): latest NDVI/EVI/SAVI vegetation indices + trend. Use for "how is field X doing", "is my crop healthy", NDVI questions.
- get_field_history_tool(field_id, months): NDVI time series over last N months. Use for trend, improvement/decline questions.
- get_field_alerts_tool(field_id): precision-ag alerts across fields (field_id=0 = all fields). Use for "any issues", "what needs attention", "are there problems".
- get_field_soil_samples_tool(field_id): soil test results — pH, organic matter, NPK with deficiency/excess flags and amendment recommendations. Use for "soil health", "fertilizer", "what nutrients does my field need", soil questions.
- get_field_scouting_tool(field_id): in-field scout observations — pests, disease, weeds, nutrient deficiency symptoms with severity. Use for "what's been found in the field", "any pest issues", "scouting reports".
- add_scout_observation_tool(field_id, category, severity, notes): LOG a new scouting observation on behalf of the user. Use when the user tells you they found something in the field and wants it recorded. Confirm before calling.
- get_field_activity_log_tool(field_id): recent field operations — sprays, fertilizer, tillage, irrigation, harvest. Use for "what was applied", "field operation history", before giving input recommendations to avoid double-applying.
- log_field_activity_tool(field_id, activity_type, activity_date, product, rate, rate_unit, notes): LOG a new field operation. Use when user says they did something and wants it recorded. Confirm with user before calling.
- add_soil_sample_tool(field_id, sample_label, ph, organic_matter, nitrogen, phosphorus, potassium, sample_date): SAVE soil test results the user provides. Use when user shares soil test numbers. Confirm before calling.
- get_field_gdd_tool(field_id, days): accumulated Growing Degree Days + current crop development stage. Use for "what growth stage is my crop", "how many GDD", "when will it flower/mature", stage-specific advice.
- get_field_irrigation_tool(field_id, days): irrigation recommendation from ET₀ vs precipitation — "irrigate now / soon / not needed" + water deficit in inches. Use for "should I irrigate", "when to water", "water stress", irrigation scheduling.
- get_field_yield_forecast_tool(field_id): NDVI-based yield estimate vs crop-type baseline with trend. Use for "expected yield", "will this be a good harvest", "am I above or below average yield".
- get_field_carbon_tool(field_id): soil OM trends, SOC stock estimates, cover crop history, rotation diversity, sustainability score. Use for "carbon sequestration", "soil health trend", "regenerative ag score", "how sustainable is my farm".
- get_farm_benchmark_tool(): compare all fields by NDVI/health/trend — ranks best-to-worst. Use for "which field is doing best", "farm overview", "compare my fields", "which field needs most attention".
- get_field_weather_tool(field_id, days): recent temp/precipitation/ET₀ at the field location. Use for "recent weather on my farm", "how much rain", when weather context helps agronomic advice.
- get_field_biomass_tool(field_id): current dry-matter biomass estimate (kg DM/ha) for a field with confidence and capture date. If confidence is low, the response automatically explains WHY and how to fix it. Use for "what's my biomass", "how much forage", "what does this biomass number mean", or any biomass / dry-matter question. ALSO use whenever the user asks why biomass confidence is low.
- improve_field_biomass_confidence_tool(field_id): trigger a fresh satellite biomass run and average it with recent passes to raise confidence. Use when the user asks to "improve confidence", "fix the biomass confidence", "average the biomass passes", or follows up on a low-confidence biomass result. PROACTIVELY OFFER this any time get_field_biomass_tool returns confidence < 0.4.
- get_field_maturity_tool(field_id): peak-antioxidant harvest prediction for berry/fruit fields. Returns the latest Brix/anthocyanin/firmness sample, the trend fit, the predicted peak date with confidence, and (when set) the buyer's shelf-target alignment. Use for "when should I harvest", "when is peak ripeness", "is my fruit ready", "when do I pick", or any harvest-timing question on a fruit/berry field. If the response says "no samples logged yet", proactively offer log_maturity_sample_tool.
- log_maturity_sample_tool(field_id, sample_date, brix, anthocyanin_mg_g, firmness_kgf, notes): log a new ripeness/quality reading the user just took. Use when the user says "I measured Brix on the blueberries", "log a sample", "record an anthocyanin reading", or shares a refractometer/NIR/penetrometer number. Always confirm the field and number before calling. Each new sample sharpens the maturity prediction.
- get_field_climate_forecast_tool(field_id, hours): predictive 72h+ climate-stress forecast — detects upcoming heatwaves, frost, high-VPD drought stress, saturating rainfall, and damaging wind BEFORE they hit, with concrete mitigation actions tailored to the crop (open tunnel side-walls, schedule pre-cool irrigation, fire frost sprinklers, secure plastic, emergency pick before fruit-split rain, etc.). Use when the user asks "what's the forecast", "is there a heatwave coming", "should I worry about frost tonight", "do I need to ventilate the tunnel", or any forward-looking weather/crop-stress question. Default hours=72, max 168 (7 days).
- get_field_assessment_history_tool(field_id, limit): your own previously-generated Field Assessment Reports — past consultant snapshots with executive summary, overall health, confidence, and open recommendations. Use when the user asks "what did the last assessment say", "have we written a report on this field", "compare to the previous assessment", "what was your recommendation last time", or whenever you want to reference your prior advice instead of repeating it. Default limit=3, max 10.
- get_field_water_use_tool(field_id): real-world crop water use (actual evapotranspiration, ETa) from FAO WaPOR / OpenET satellite data — latest snapshot plus a 12-period series. Use for "how much water is my crop actually using", "is ET matching what I'm irrigating", or "is water use normal for the season". Pair with get_field_irrigation_tool to compare actual ET to the modeled deficit.
- get_field_agronomy_tool(field_id): full per-field snapshot from the satellite crop-monitoring service — current weather + 7-day forecast + GDD + predicted growth stage + latest vegetation indices + irrigation signal + per-product spray decision (herbicide/fungicide/insecticide) + crop-specific named pest & disease alerts (Gray Leaf Spot, Fusarium Head Blight, European Corn Borer, etc.) + concrete operational recommendations. Use for "should I spray today", "any disease pressure", "give me the full picture on this field", "what should I do this week".
- get_field_zones_tool(field_id, num_zones, index): k-means stress zones for a field — clusters the latest vegetation-index raster into 2–6 management zones (default 4) sorted lowest=stress to highest=best, with per-zone area % + mean. Use for "where are the stressed parts", "show me management zones", "is this field uniform", "should I do variable-rate".
BUSINESS OPS — Accounting + Event hosting (only call when business_id is known or list_my_fields_tool exposed it; otherwise ask):
- get_accounting_snapshot_tool(business_id): AR/AP, customer/vendor counts, last-30-day revenue + spend, recent invoices. Use for "how are the books", "money summary", "what's outstanding".
- list_open_invoices_tool(business_id, limit): unpaid invoices sorted by due date. Use for "what's overdue", "who hasn't paid".
- find_customer_tool(business_id, query): search customers by name/company/email substring (contact info masked). Use for "find a customer", "look up John Doe".
- get_recent_payments_tool(business_id, days): payments received in last N days with totals. Use for "recent payments", "what came in this month", "cash flow".
- get_event_registrations_tool(event_id): host-side roster for an event the user owns — registrations, payment status, masked attendee contact. Use for "who's registered", "event roster", "how many paid for event 42".
- get_event_sponsorship_summary_tool(event_id): sponsorship revenue + per-tier breakdown (slots taken, revenue collected). Use for "how are sponsorship tiers selling", "how much in sponsorship revenue", "is my Gold tier full".
- list_event_sponsors_tool(event_id, status?): list of sponsors for an event with tier + paid status. Optional status filter (pending/confirmed/declined). Use for "who are my sponsors", "any unpaid sponsors", "show me confirmed sponsors".
- get_my_event_leads_summary_tool(event_id, business_id): exhibitor's lead-capture summary at a specific event — total scans + by-status + by-rating. Use for "how many leads did I get at event X", "what's my lead pipeline".
- list_my_event_leads_tool(event_id, business_id, status?, rating_min?): list of my exhibitor lead scans with masked contact info. Use for "show me my hot leads", "qualified leads from event 12", "who haven't I followed up with".
- get_event_floor_plan_summary_tool(event_id): floor plan booth-sales status — total booths, available count, by-status (available/reserved/sold/blocked), by-tier. Use for "how many booths sold", "is the floor plan filling up", "what's left for vendors".
- get_event_booth_services_revenue_tool(event_id): booth services revenue from à la carte add-ons (electrical/water/internet/AV/etc). Use for "how much in services revenue", "what add-ons are selling", "is anyone ordering electrical".
- get_event_coi_summary_tool(event_id): Certificate of Insurance status counts (pending/approved/rejected/expired) + count expiring in next 30 days. Use for "any COIs to review", "are sponsors compliant", "any insurance expiring".
- list_event_pending_cois_tool(event_id): COI review queue — list of pending and recently expired uploads needing organizer attention.

WHEN GIVING PRECISION AG ADVICE: Always interpret the numbers, don't just report them. Examples:
- NDVI 0.72 = "your canopy is dense and healthy — likely at or near peak biomass"
- NDVI 0.35 = "moderate stress — could be drought, nutrient deficiency, or disease pressure"
- pH 5.4 = "too acidic for most crops — apply lime at 2–3 tons/ac to raise to 6.0–6.5"
- Irrigation urgency high = "apply 1–1.5 inches of water within 24–48 hours to prevent yield loss"
- GDD 850 (corn) = "your corn is at or approaching silking — critical period, protect from stress"
After fetching data, always give a SPECIFIC, ACTIONABLE recommendation — never just report the number.
- list_my_animals_tool(studs_only): animals on the current business (for-sale by default; set studs_only=true for stud listings). Use for "my animals", "what's for sale on my ranch".
- list_my_listings_tool(): unified marketplace inventory (produce + meat + processed food) for the current business. Use for "my inventory", "my marketplace listings".
- count_my_animals_tool(): quick count of for-sale vs at-stud animals on the current business. Use for "how many animals do I have".

COLD CHAIN & LOGISTICS — Vehicle fleet (ALWAYS call the tool; NEVER guess vehicle names or specs):
- list_cold_chain_vehicles_tool(): REQUIRED for any question about the user's vehicles, fleet, truck, van, trailer, cold chain, or refrigerated transport. Returns the exact vehicles, temperature ranges, drivers, and latest readings from the database. Do NOT describe vehicles from memory — call this tool first, then report what it returns.
- geocode_location_tool(query): resolve any zip code, city, address, or landmark to GPS coordinates so the map zooms there. ALWAYS call this tool when the user says "zoom to", "go to", "center on", "fly to", "show me", "navigate to", or "pan to" any location. The tool returns a [MAP_CMD] marker that the widget uses to move the map — you do not need to explain the coordinates, just confirm the place name.
- list_cold_chain_readings_tool(vehicle_id?, limit?): recent temperature readings across all vehicles (or one vehicle). Use for "show temperature readings", "any temp violations", "what temps have been logged". vehicle_id=0 = all vehicles.
- log_cold_chain_reading_tool(vehicle_id, temp_c, notes?): log a new temperature reading. Confirm vehicle + temp before calling. Use when user says "log a reading of -2°C on truck A".
- list_cold_chain_shipments_tool(status?): active or historical shipments with origin, destination, vehicle, driver. Use for "show my shipments", "deliveries in transit", "shipment history".
- get_animal_detail_tool(animal_id): FULL animal profile — name, breed/category, sex, DOB, colors, sale/stud price, embryo/semen price, registration numbers, fiber stats (micron, CV, comfort factor), co-owners. Use when the user asks about a SPECIFIC animal by ID: "tell me about animal #42", "what's the stud fee for that alpaca", "show me the fiber data". Access-controlled to the user's business.

BUSINESS PROFILE — read and update the business account:
- get_business_profile_tool(): read the full business profile (name, description, slogan, phone, email, website, address, type, active status, social links). Use for "show my business profile", "what is my business info", "what fields does my account have".
- update_business_profile_tool(business_name?, description?, slogan?, phone?, email?, website?): update public profile fields. Leave fields blank to keep them unchanged. Confirm name changes first. Use for "update our website", "change our phone number", "fix our description", "update our slogan".

ANIMALS — full management (list details, update price/status):
- list_my_animals_detail_tool(): list ALL animals with editable fields — name, sex, DOB, sale price, stud price, for-sale/stud status, website visibility. Use for "show all my animals", "what are my animal prices", "which animals are not listed for sale".
- update_animal_tool(animal_id, price?, stud_price?, for_sale?, for_stud?, description?, show_on_website?): update one animal. for_sale=1 to list / 0 to remove. Pass -1 for fields not being changed. Confirm price/status changes. Use for "change price on animal #42 to $1500", "take my llama off the market", "list my alpaca for stud".

MARKETPLACE INVENTORY — produce, meat, processed food:
- list_produce_inventory_tool(): full produce/crop inventory with qty, unit, prices, available date, active status (ShowProduce). Use for "show my produce", "what crops am I selling", "produce listings with prices".
- update_produce_listing_tool(produce_id, quantity?, retail_price?, wholesale_price?, show_produce?, available_date?): update one produce listing. Pass -1 for fields not changing. Confirm price changes. Use for "change tomato price to $4/lb", "hide the apple listing", "update corn quantity".
- list_meat_inventory_tool(): full meat inventory with ingredient, cut, qty, weight unit, prices, active status. Use for "show my meat inventory", "what cuts am I selling", "beef listings with prices".
- update_meat_listing_tool(meat_id, quantity?, retail_price?, wholesale_price?, show_meat?, available_date?, notes?): update one meat listing. Use for "change beef price to $8/lb", "hide pork listing", "update lamb quantity".
- list_processed_food_tool(): all processed/artisan food products with qty, prices, organic/local flags, active status. Use for "show my processed food", "what artisan products do I have", "food product listings".
- update_processed_food_tool(food_id, quantity?, retail_price?, wholesale_price?, show_product?, notes?): update one processed food listing. Use for "change jam price to $6", "hide cheese listing", "update bread quantity".

BLOG — view and create posts:
- list_my_blog_posts_tool(): list blog posts with title, category, date, published/draft status and visibility (directory vs website). Use for "show my blog posts", "what articles have I written", "are my posts published".
- create_blog_post_tool(title, content, category?, publish?): create a new blog post. publish=1 to publish immediately, 0 for draft. ALWAYS confirm title+content with user before calling. Use for "write a blog post about X", "publish an article on our process", "draft a post".

SERVICES — view and add service listings:
- list_my_services_tool(): list service listings with title, category, price, availability, description. Use for "what services do I offer", "show my service listings", "what is my shearing service price".
- add_service_listing_tool(title, description?, price?, contact_for_price?, available?, phone?, website?): add a new service listing. Confirm details before calling. Use for "add a shearing service at $15/head", "create a boarding service listing".

SELLER MARKETPLACE ORDERS — view and manage incoming orders:
- list_seller_orders_tool(status?): incoming orders from buyers. status filter: 'pending'/'confirmed'/'shipped'/'rejected'; empty = active (pending+confirmed). Use for "what orders do I have", "pending orders", "orders I need to ship".
- confirm_seller_order_tool(order_item_id, estimated_delivery_date?): accept a pending order. Confirm with user first. Use for "accept order #123", "confirm the tomato order".
- reject_seller_order_tool(order_item_id, reason): reject pending order + restore inventory. Reason required (buyer sees it). Confirm first. Use for "reject order #123 — out of stock".
- ship_seller_order_tool(order_item_id, tracking_number?, estimated_delivery_date?): mark confirmed order as shipped. Use for "order #123 shipped, tracking 1Z999".

CERTIFICATIONS — track credentials and compliance:
- list_my_certifications_tool(): list certifications with type, issuing body, cert number, issue/expiry dates, status. Use for "show my certifications", "when does my organic cert expire", "any certs expiring soon".
- add_certification_tool(certification_type, issuing_body?, certification_number?, issue_date?, expiry_date?, notes?): add a new cert record. Confirm details first. Use for "add my USDA organic cert", "record my food safety certification".

PLANT & INGREDIENT KNOWLEDGE BASE — agronomic reference data for 3,000+ plant varieties and all food ingredient groups:
- search_plants_tool(query, plant_type): find plants by name or type (Vegetable/Herb/Fruit/Legume/Nut/Grain/Mushroom/Root/Tubers/Leafy Green). Returns plant IDs + variety counts. Use first when the user asks about a plant type or specific plant name: "what tomato varieties are in the system", "show me all grain plants", "find herb plants named basil".
- get_plant_detail_tool(plant_id): FULL agronomic profile for all varieties of one plant — ideal soil texture, pH range (e.g., "6.1–6.5 Slightly Acidic"), organic matter level, salinity tolerance, USDA hardiness zone with temperature range, humidity classification, water requirement in inches/week, and primary nutrient need. Use for growing-condition questions: "what soil does kale need", "what's the water requirement for corn", "what pH does garlic prefer", "is this plant cold-hardy in my zone", "what nutrient is most important for this crop".
- search_ingredients_tool(query, category): find food ingredients by name or category (Vegetable/Fruit/Herb/Meat/Grain/Dairy/Legume/Nut/Mushroom/Seafood/etc.). Returns ingredient IDs + variety counts. Use when user asks about the ingredient catalog: "what vegetable ingredients are in the system", "find garlic as an ingredient", "what meat categories do you have".
- get_ingredient_detail_tool(ingredient_id): FULL ingredient profile — all varieties and their descriptions, nutrient associations. Use after search to get varieties: "what varieties of heirloom tomato do you have", "list the varieties of black angus in the ingredient system".

WHEN GIVING PLANT/INGREDIENT ADVICE: Always translate lookup data into practical guidance. Examples:
- pH range "6.1–6.5 Slightly Acidic" = "ideal for most crops — if your soil test shows 5.8, apply 1–2 tons lime/ac before planting"
- Salinity "Non-Saline (< 2 dS/m)" = "this crop is salt-sensitive — avoid fields with irrigation water above 1.5 dS/m"
- Hardiness Zone 7A (0°F to 5°F) = "this variety can handle light frost but will die below 0°F — plant after last frost in spring"
- Water need 1.0–1.5 in/week with NDVI stress = "this crop wants more water than it's getting — match irrigation to the GDD stage"
- Organic matter "Moderate (2–4%)" = "your field's OM is adequate; adding cover crops can push it toward the High range and improve yields"
- draft_produce_listing_tool(ingredient_name, quantity, measurement, retail_price, wholesale_price, available_date): DRAFT a new produce listing — saves a pending draft for the farmer to approve, never publishes directly. Use for "list my tomatoes at $3/lb", "put 10 dozen eggs on the marketplace". Always confirm the draft with the user before calling.
- draft_meat_listing_tool(ingredient_name, cut, quantity, weight_unit, retail_price, wholesale_price, available_date): DRAFT a new meat inventory listing. Use for "list 50 lbs of ground beef at $8/lb", "add lamb chops to the marketplace", "put pork loin on sale". Saves pending draft — does not publish.
- draft_processed_food_listing_tool(name, quantity, retail_price, wholesale_price, is_organic, is_local, notes): DRAFT a new processed/artisan food product listing. Use for "list my strawberry jam at $7 a jar", "add sourdough bread to the marketplace", "put goat cheese on sale". Saves pending draft — does not publish.
- draft_event_tool(event_name, description, start_date, end_date, location_name, city, state, is_free, registration_required): DRAFT a new farm event. Use for "plan a farm tour", "create an open-ranch day". Saves pending — does not publish.
- draft_blog_post_tool(title, content, category): DRAFT a new blog post for the business. Use for "write a blog post about…", "draft an article". Saves pending — does not publish.
- planting_calendar_tool(crop, zone, lat, lon): when/how to plant a specific crop (earliest safe plant-out date, soil-temp target, seed depth, direct-sow vs transplant, days to maturity). Use for "when should I plant X", "is it too early for Y".
- irrigation_schedule_tool(crop, stage, soil_type, climate, days_since_rain): how much and how often to water. stage='initial'|'mid'|'late'; soil_type sandy/loam/clay/silty; climate tropical/subtropical/temperate/continental/mediterranean/arid/highland/boreal. Use for "how often do I water X", "am I overwatering".
- manure_pairing_tool(crop, available_manures): rank manures for a given crop by N-P-K fit + composting caveats. available_manures is an optional comma list (e.g., "goat,chicken") to restrict to what's on hand. Use for "what manure works best for X", "can I use my goat manure on tomatoes".
- save_recipe_tool(name, items_json, portion_yield, menu_price): save a kitchen recipe so it can be costed later. items_json is a JSON array like [{{"ingredient":"ground beef","qty":0.33,"unit":"lb"}}]. Use for "save my summer salad recipe", "let me track the burger plate".
- cost_recipe_tool(recipe_name): live plate-cost calculation for a saved recipe using current OFN marketplace prices. Use for "cost my burger", "what does the salad run now", "update my plate costs".
- seasonal_menu_tool(state, category): what's actively in season on OFN right now in the chef's state (defaults to the chef's own state). Use for "what's local right now", "seasonal menu ideas", "what's in season near me". category optional (Vegetable/Fruit/Herb/Meat).
- set_par_tool(ingredient_name, unit, on_hand, par_level, reorder_at, preferred_business_id): set or update a par level for an ingredient in the restaurant's inventory. Use for "set par for ground beef at 20 lb", "reorder tomatoes at 5 lb".
- check_par_levels_tool(): list ingredients currently at/below their reorder threshold. Use for "what's running low", "check my pars".
- draft_restock_order_tool(): build a multi-farm restock cart from below-par items, with live OFN pricing and totals, grouped by farm. Use for "draft my order", "restock what's low", "what should I buy this week".
- provenance_cards_tool(ingredient_names): "meet your farmers" provenance cards (markdown) for a comma-separated ingredient list — farm name, location, slogan, description. Use for "make provenance cards for my menu", "who grew these tomatoes".

PERSONAL HISTORY & ALERTS — read-only / opt-in helpers tied to the user's account:
- get_recent_pest_detections_tool(limit): the user's last `limit` pest/disease/deficiency diagnoses from photos they uploaded (default 3, max 10). Use for "what did my last photo show", "what was that pest you found", "remind me what the AI said about my plant photo".
- get_my_recent_history_tool(entry_type, limit): broader recall of past Saige features. entry_type optional — "soil", "price", or empty for all types interleaved (default 5, max 20). Use for "what did Saige tell me last time about my soil/prices", "show my past assessments". For pest photos prefer the dedicated tool above.
- check_my_weather_alerts_tool(days_ahead): scan the user's saved push-notification locations against the next 1–5 day forecast (default 2) and return any hazards (frost, hard freeze, heat, flood, hail, wind, wildfire smoke). Read-only — does NOT send a push. Use for "any weather risks coming", "is frost in the forecast for my farm", "should I worry about weather this week".
- send_push_notification_tool(title, body, url): send a real push notification to the user's subscribed devices. Use ONLY when the user explicitly asks to be pinged ("notify me when…", "remind me about…") or for an immediate, time-sensitive alert (incoming frost, irrigation overdue). ALWAYS confirm wording before calling. title ≤60 chars, body ≤160 chars, url is the in-app deep link.

GRANTS & PROGRAMS — personal tracker:
- get_tracked_grants_tool(business_id, people_id): list grants and programs the business is tracking, including title, agency, status (interested/in_progress/submitted/awarded/declined/not_eligible), applied date, result date, amount received, and notes. Use for "what grants am I tracking", "show my grant applications", "what programs am I applying for", "grant tracker".

COLD-CHAIN — predictive shelf life:
- calculate_shelf_life_tool(vehicle_id, product_type, original_shelf_life_days, lookback_hours, business_id, people_id): compute adjusted shelf life for cargo using Q10 degradation model applied to actual vehicle temperature logs. Returns remaining days, degradation %, excursion time, and recommended action (Normal/Expedite/Express Sale/Discard). Use for "how fresh is my cargo", "did the temperature excursion hurt the lettuce", "what's the shelf life impact", "is the shipment still viable", "how many days does the produce have left".

FUN:
- tell_joke_tool(): tell the user a random farm or ranch joke they haven't heard before. Tracks history per user so jokes never repeat. Use whenever the user asks for a joke, wants to laugh, or says "tell me something funny". Deliver it in Saige's voice — maybe a short setup like "Alright, here's one:" or "Oh I got one for y'all."

Prioritize the latest user message and any newly provided measurements over older generic context.
If soil-test values are present, reference them explicitly and avoid repeating unchanged advice.

Provide a concise response (3-4 sentences) with:
1. Direct answer to their question
2. 2-3 specific, actionable recommendations

Keep it conversational — Saige's voice, not a textbook. NO markdown formatting, NO asterisks, NO headers.
If the farmer seems worried, acknowledge it briefly before diving into solutions. If the answer is simple, keep it short."""

    # 4. Bind Tools
    bound_tools = []
    if WEATHER_AVAILABLE:
        bound_tools.extend(weather_tools)
    if COMPANION_AVAILABLE:
        bound_tools.extend(companion_tools)
    if CROP_NAMES_AVAILABLE:
        bound_tools.extend(crop_name_tools)
    if WEATHER_MITIGATION_AVAILABLE:
        bound_tools.extend(weather_mitigation_tools)
    if REGION_CROPS_AVAILABLE:
        bound_tools.extend(region_crops_tools)
    if SOIL_CHALLENGE_AVAILABLE:
        bound_tools.extend(soil_challenge_tools)
    if PRICE_FORECAST_AVAILABLE:
        bound_tools.extend(price_forecast_tools)
    if SUBSIDIES_AVAILABLE:
        bound_tools.extend(subsidies_tools)
    if INSURANCE_AVAILABLE:
        bound_tools.extend(insurance_tools)
    if EVENTS_AVAILABLE:
        bound_tools.extend(event_tools)
    if PRECISION_AG_AVAILABLE:
        bound_tools.extend(precision_ag_tools)
    if BUSINESS_OPS_AVAILABLE:
        bound_tools.extend(business_ops_tools)
    if FARM_DATA_AVAILABLE:
        bound_tools.extend(farm_data_tools)
    if BUSINESS_DATA_AVAILABLE:
        bound_tools.extend(business_data_tools)
    if KNOWLEDGE_BASE_AVAILABLE:
        bound_tools.extend(knowledge_base_tools)
    if ACTIONS_AVAILABLE:
        bound_tools.extend(actions_tools)
    if AGRONOMY_AVAILABLE:
        bound_tools.extend(agronomy_tools)
    if CHEF_AVAILABLE:
        bound_tools.extend(chef_tools)
    if PEST_DETECTION_AVAILABLE:
        bound_tools.extend(pest_detection_tools)
    if PUSH_NOTIFICATIONS_AVAILABLE:
        bound_tools.extend(push_notification_tools)
    if WEATHER_ALERTS_AVAILABLE:
        bound_tools.extend(weather_alert_tools)
    if HISTORY_STORE_AVAILABLE:
        bound_tools.extend(history_tools)
    if JOKES_AVAILABLE:
        bound_tools.extend(joke_tools)

    # ── Intent-based tool pruning ────────────────────────────────────────────
    # After assembling the full tool list, restrict it to only the tools
    # relevant to the detected intent.  This stops the LLM from wandering into
    # unrelated tool calls (e.g., querying all 5 RAG systems for a map zoom).
    if _INTENT_MAP:
        _map_tool_names = {"geocode_location_tool"}
        bound_tools = [t for t in bound_tools if t.name in _map_tool_names]
        print(f"[Intent Router] Tool list pruned to map tools: {[t.name for t in bound_tools]}")
    elif _INTENT_BUSINESS:
        _biz_tool_names = (
            {t.name for t in farm_data_tools if FARM_DATA_AVAILABLE}
            | {t.name for t in business_data_tools if BUSINESS_DATA_AVAILABLE}
            | {t.name for t in business_ops_tools if BUSINESS_OPS_AVAILABLE}
        )
        bound_tools = [t for t in bound_tools if t.name in _biz_tool_names]
        print(f"[Intent Router] Tool list pruned to business tools ({len(bound_tools)} tools)")
    elif _INTENT_PRECISION_AG:
        _precag_tool_names = {t.name for t in precision_ag_tools if PRECISION_AG_AVAILABLE}
        bound_tools = [t for t in bound_tools if t.name in _precag_tool_names]
        print(f"[Intent Router] Tool list pruned to precision-ag tools ({len(bound_tools)} tools)")
    elif _INTENT_ACCOUNTING:
        _acct_tool_names = {t.name for t in business_ops_tools if BUSINESS_OPS_AVAILABLE}
        bound_tools = [t for t in bound_tools if t.name in _acct_tool_names]
        print(f"[Intent Router] Tool list pruned to accounting/events tools ({len(bound_tools)} tools)")
    # _INTENT_KNOWLEDGE_ONLY: full tool list kept as-is
    # ── end tool pruning ──────────────────────────────────────────────────────

    # Production: specialists are read-only — writes only via HITL → Execute
    from tool_policy import filter_read_only_tools, is_write_tool, write_tool_refusal

    before = len(bound_tools)
    bound_tools = filter_read_only_tools(bound_tools)
    if before != len(bound_tools):
        print(f"[Advisory Agent] Stripped {before - len(bound_tools)} write tools (HITL-only)")

    llm_with_tools = llm.bind_tools(bound_tools) if bound_tools else llm

    # 5. Tool Execution Loop (ReAct Pattern)
    weather_data = None
    weather_context = ""
    companion_context = ""
    crop_name_context = ""
    mitigation_context = ""
    region_context = ""
    soil_context = ""
    price_context = ""
    subsidies_context = ""
    insurance_context = ""
    events_context = ""
    precision_ag_context = ""
    farm_data_context = ""
    knowledge_base_context = ""
    actions_context = ""
    agronomy_context = ""
    chef_context = ""
    pest_history_context = ""
    push_context = ""
    weather_alerts_context = ""
    history_context = ""
    grants_context = ""
    max_iterations = 3
    final_response = ""
    _map_cmd_collected = ""  # [MAP_CMD: ...] extracted from geocode tool result
    people_id_for_tools = state.get("people_id") or ""
    business_id_for_tools = 0
    try:
        business_id_for_tools = int(state.get("business_id") or 0)
    except (TypeError, ValueError):
        business_id_for_tools = 0

    try:
        for iteration in range(max_iterations):
            current_input = full_prompt
            if weather_context:
                current_input += f"\n\n[Weather Update]: {weather_context}"
            if companion_context:
                current_input += f"\n\n[Companion Planting Data]: {companion_context}"
            if crop_name_context:
                current_input += f"\n\n[Crop Name Translation]: {crop_name_context}"
            if mitigation_context:
                current_input += f"\n\n[Weather Mitigation Plan]: {mitigation_context}"
            if region_context:
                current_input += f"\n\n[Region-Specific Crops]: {region_context}"
            if soil_context:
                current_input += f"\n\n[Soil Assessment]: {soil_context}"
            if price_context:
                current_input += f"\n\n[Price Forecast]: {price_context}"
            if subsidies_context:
                current_input += f"\n\n[Subsidies / Grants]: {subsidies_context}"
            if insurance_context:
                current_input += f"\n\n[Crop Insurance]: {insurance_context}"
            if events_context:
                current_input += f"\n\n[Farm Events]: {events_context}"
            if precision_ag_context:
                current_input += f"\n\n[Precision Ag]: {precision_ag_context}"
            if farm_data_context:
                current_input += f"\n\n[Farm Data]: {farm_data_context}"
            if knowledge_base_context:
                current_input += f"\n\n[Knowledge Base]: {knowledge_base_context}"
            if actions_context:
                current_input += f"\n\n[Draft Saved]: {actions_context}"
            if agronomy_context:
                current_input += f"\n\n[Agronomy]: {agronomy_context}"
            if chef_context:
                current_input += f"\n\n[Chef]: {chef_context}"
            if pest_history_context:
                current_input += f"\n\n[Pest Detection History]: {pest_history_context}"
            if push_context:
                current_input += f"\n\n[Push Notification]: {push_context}"
            if weather_alerts_context:
                current_input += f"\n\n[Weather Alerts]: {weather_alerts_context}"
            if history_context:
                current_input += f"\n\n[Saige History]: {history_context}"
            if grants_context:
                current_input += f"\n\n[Grant Tracker]: {grants_context}"
            # If map tool already ran, override the directive so the LLM doesn't call it again
            if _map_cmd_collected:
                current_input += (
                    "\n\n⚠ MAP ALREADY UPDATED — geocode_location_tool has already run and the "
                    "map has moved. Do NOT call it again. Respond in one short sentence confirming "
                    "the place name shown in [Farm Data] above."
                )
            _thread_id = state.get("thread_id", "")
            _stream_q = _get_stream_queue(_thread_id) if _thread_id else None

            # Build LLM input — multimodal on first iteration when an image was attached
            if iteration == 0 and _image_data:
                try:
                    from langchain_core.messages import HumanMessage as _HumanMessage
                    # Detect MIME type from base64 magic bytes
                    _mime = "image/jpeg"
                    try:
                        import base64 as _b64
                        _hdr = _b64.b64decode(_image_data[:16] + "==")[:4]
                        if _hdr[:4] == b"\x89PNG":
                            _mime = "image/png"
                        elif _hdr[:4] == b"RIFF" or _hdr[:4] == b"WEBP":
                            _mime = "image/webp"
                    except Exception:
                        pass
                    _llm_input = _HumanMessage(content=[
                        {"type": "image_url", "image_url": {"url": f"data:{_mime};base64,{_image_data}"}},
                        {"type": "text", "text": current_input},
                    ])
                    print(f"[Advisory Agent] Sending multimodal message (mime={_mime})")
                except Exception as _img_err:
                    print(f"[Advisory Agent] Multimodal build failed, falling back to text: {_img_err}")
                    _llm_input = current_input
            else:
                _llm_input = current_input

            if _stream_q is not None:
                # Streaming mode: accumulate chunks and forward text tokens to the queue
                _accumulated = None
                try:
                    for _chunk in llm_with_tools.stream(_llm_input):
                        if _accumulated is None:
                            _accumulated = _chunk
                        else:
                            _accumulated = _accumulated + _chunk
                        _tok = getattr(_chunk, "content", None)
                        if _tok:
                            _stream_q.put(_tok)
                except Exception as _se:
                    print(f"[Advisory Agent] Streaming error, falling back to invoke: {_se}")
                    _accumulated = llm_with_tools.invoke(_llm_input)
                response = _accumulated if _accumulated is not None else llm_with_tools.invoke(_llm_input)
            else:
                response = llm_with_tools.invoke(_llm_input)

            # Check for tool calls
            if hasattr(response, 'tool_calls') and response.tool_calls and iteration < max_iterations - 1:
                print(f"[Advisory Agent] Tool call detected: {len(response.tool_calls)}")
                for tool_call in response.tool_calls:
                    tc_name = tool_call.get('name')
                    tc_args = tool_call.get('args', {}) or {}
                    if is_write_tool(str(tc_name or "")):
                        tool_result = write_tool_refusal(str(tc_name))
                        print(f"[Advisory Agent] BLOCKED write tool: {tc_name}")
                        messages.append(response)
                        try:
                            from langchain_core.messages import ToolMessage
                            messages.append(ToolMessage(content=tool_result, tool_call_id=tool_call.get("id") or str(tc_name)))
                        except Exception:
                            messages.append({"role": "tool", "content": tool_result})
                        continue
                    if tc_name == 'get_weather_tool':
                        loc = tc_args.get('location', location)
                        print(f"[Advisory Agent] Executing Weather Tool for: {loc}")

                        tool_result = get_weather_tool.invoke({"location": loc})
                        weather_context = f"Weather Information:\n{tool_result}"

                        try:
                            weather_data = weather_service.get_weather(loc)
                        except:
                            pass
                    elif tc_name == 'companion_planting_tool' and COMPANION_AVAILABLE:
                        crop = tc_args.get('crop', '')
                        print(f"[Advisory Agent] Executing Companion Planting Tool for: {crop}")
                        tool_result = companion_planting_tool.invoke({"crop": crop})
                        companion_context = (companion_context + "\n\n" if companion_context else "") + tool_result
                    elif tc_name == 'check_companion_pair_tool' and COMPANION_AVAILABLE:
                        a = tc_args.get('crop_a', '')
                        b = tc_args.get('crop_b', '')
                        print(f"[Advisory Agent] Executing Companion Pair Check: {a} + {b}")
                        tool_result = check_companion_pair_tool.invoke({"crop_a": a, "crop_b": b})
                        companion_context = (companion_context + "\n\n" if companion_context else "") + tool_result
                    elif tc_name == 'crop_name_tool' and CROP_NAMES_AVAILABLE:
                        name = tc_args.get('name', '')
                        print(f"[Advisory Agent] Executing Crop Name Tool for: {name}")
                        tool_result = crop_name_tool.invoke({"name": name})
                        crop_name_context = (crop_name_context + "\n\n" if crop_name_context else "") + tool_result
                    elif tc_name == 'weather_mitigation_tool' and WEATHER_MITIGATION_AVAILABLE:
                        hazard = tc_args.get('hazard', '')
                        phase = tc_args.get('phase', 'imminent')
                        print(f"[Advisory Agent] Executing Weather Mitigation Tool: {hazard}/{phase}")
                        tool_result = weather_mitigation_tool.invoke({"hazard": hazard, "phase": phase})
                        mitigation_context = (mitigation_context + "\n\n" if mitigation_context else "") + tool_result
                    elif tc_name == 'region_crops_tool' and REGION_CROPS_AVAILABLE:
                        args = {
                            "climate": tc_args.get('climate', ''),
                            "zone": tc_args.get('zone', ''),
                            "lat": float(tc_args.get('lat', 0) or 0),
                            "lon": float(tc_args.get('lon', 0) or 0),
                        }
                        print(f"[Advisory Agent] Executing Region Crops Tool: {args}")
                        tool_result = region_crops_tool.invoke(args)
                        region_context = (region_context + "\n\n" if region_context else "") + tool_result
                    elif tc_name == 'soil_challenge_tool' and SOIL_CHALLENGE_AVAILABLE:
                        soil_args = {k: tc_args.get(k, -1.0) for k in [
                            "ph", "organic_matter_pct", "nitrogen_ppm", "phosphorus_ppm",
                            "potassium_ppm", "cec_meq", "salinity_dsm", "moisture_pct",
                            "bulk_density_gcc", "sodium_pct_cec"
                        ]}
                        soil_args["crop"] = tc_args.get("crop", "")
                        print(f"[Advisory Agent] Executing Soil Challenge Tool: {soil_args}")
                        tool_result = soil_challenge_tool.invoke(soil_args)
                        soil_context = (soil_context + "\n\n" if soil_context else "") + tool_result
                    elif tc_name == 'price_forecast_tool' and PRICE_FORECAST_AVAILABLE:
                        commodity = tc_args.get('commodity', '')
                        months_ahead = int(tc_args.get('months_ahead', 6) or 6)
                        print(f"[Advisory Agent] Executing Price Forecast Tool: {commodity}/{months_ahead}mo")
                        tool_result = price_forecast_tool.invoke({"commodity": commodity, "months_ahead": months_ahead})
                        price_context = (price_context + "\n\n" if price_context else "") + tool_result
                    elif tc_name == 'subsidies_tool' and SUBSIDIES_AVAILABLE:
                        args = {
                            "category": tc_args.get('category', ''),
                            "keyword": tc_args.get('keyword', ''),
                        }
                        print(f"[Advisory Agent] Executing Subsidies Tool: {args}")
                        tool_result = subsidies_tool.invoke(args)
                        subsidies_context = (subsidies_context + "\n\n" if subsidies_context else "") + tool_result
                    elif tc_name == 'insurance_tool' and INSURANCE_AVAILABLE:
                        crop = tc_args.get('crop', '')
                        print(f"[Advisory Agent] Executing Insurance Tool: {crop}")
                        tool_result = insurance_tool.invoke({"crop": crop})
                        insurance_context = (insurance_context + "\n\n" if insurance_context else "") + tool_result
                    elif tc_name == 'list_upcoming_events_tool' and EVENTS_AVAILABLE:
                        args = {
                            "business_id": int(tc_args.get('business_id', 0) or 0),
                            "limit": int(tc_args.get('limit', 10) or 10),
                        }
                        print(f"[Advisory Agent] Executing List Upcoming Events Tool: {args}")
                        tool_result = list_upcoming_events_tool.invoke(args)
                        events_context = (events_context + "\n\n" if events_context else "") + tool_result
                    elif tc_name == 'get_event_details_tool' and EVENTS_AVAILABLE:
                        eid = int(tc_args.get('event_id', 0) or 0)
                        print(f"[Advisory Agent] Executing Get Event Details Tool: {eid}")
                        tool_result = get_event_details_tool.invoke({"event_id": eid})
                        events_context = (events_context + "\n\n" if events_context else "") + tool_result
                    elif tc_name == 'event_attendee_count_tool' and EVENTS_AVAILABLE:
                        eid = int(tc_args.get('event_id', 0) or 0)
                        print(f"[Advisory Agent] Executing Event Attendee Count Tool: {eid}")
                        tool_result = event_attendee_count_tool.invoke({"event_id": eid})
                        events_context = (events_context + "\n\n" if events_context else "") + tool_result
                    elif tc_name == 'list_my_fields_tool' and PRECISION_AG_AVAILABLE:
                        print(f"[Advisory Agent] Executing List My Fields Tool (people_id from state)")
                        tool_result = list_my_fields_tool.invoke({"people_id": people_id_for_tools})
                        precision_ag_context = (precision_ag_context + "\n\n" if precision_ag_context else "") + tool_result
                    elif tc_name == 'resolve_field_by_name_tool' and PRECISION_AG_AVAILABLE:
                        fname = str(tc_args.get('name') or tc_args.get('field_name') or latest_user_message or "")
                        print(f"[Advisory Agent] Executing Resolve Field By Name: {fname!r}")
                        tool_result = resolve_field_by_name_tool.invoke({
                            "name": fname,
                            "people_id": people_id_for_tools,
                        })
                        precision_ag_context = (precision_ag_context + "\n\n" if precision_ag_context else "") + tool_result
                    elif tc_name == 'get_field_analysis_tool' and PRECISION_AG_AVAILABLE:
                        fid = int(tc_args.get('field_id', 0) or 0)
                        print(f"[Advisory Agent] Executing Get Field Analysis Tool: field_id={fid}")
                        tool_result = get_field_analysis_tool.invoke({
                            "field_id": fid,
                            "people_id": people_id_for_tools,
                        })
                        precision_ag_context = (precision_ag_context + "\n\n" if precision_ag_context else "") + tool_result
                    elif tc_name == 'get_field_history_tool' and PRECISION_AG_AVAILABLE:
                        fid = int(tc_args.get('field_id', 0) or 0)
                        months = int(tc_args.get('months', 6) or 6)
                        print(f"[Advisory Agent] Executing Get Field History Tool: field_id={fid}, months={months}")
                        tool_result = get_field_history_tool.invoke({
                            "field_id": fid,
                            "months": months,
                            "people_id": people_id_for_tools,
                        })
                        precision_ag_context = (precision_ag_context + "\n\n" if precision_ag_context else "") + tool_result
                    elif tc_name == 'get_field_alerts_tool' and PRECISION_AG_AVAILABLE:
                        fid = int(tc_args.get('field_id', 0) or 0)
                        print(f"[Advisory Agent] Executing Get Field Alerts Tool: field_id={fid}")
                        tool_result = get_field_alerts_tool.invoke({
                            "field_id": fid,
                            "people_id": people_id_for_tools,
                        })
                        precision_ag_context = (precision_ag_context + "\n\n" if precision_ag_context else "") + tool_result
                    elif tc_name == 'get_field_soil_samples_tool' and PRECISION_AG_AVAILABLE:
                        fid = int(tc_args.get('field_id', 0) or 0)
                        print(f"[Advisory Agent] Executing Get Soil Samples: field_id={fid}")
                        tool_result = get_field_soil_samples_tool.invoke({"field_id": fid, "people_id": people_id_for_tools})
                        precision_ag_context = (precision_ag_context + "\n\n" if precision_ag_context else "") + tool_result
                    elif tc_name == 'get_field_scouting_tool' and PRECISION_AG_AVAILABLE:
                        fid = int(tc_args.get('field_id', 0) or 0)
                        print(f"[Advisory Agent] Executing Get Scouting: field_id={fid}")
                        tool_result = get_field_scouting_tool.invoke({"field_id": fid, "people_id": people_id_for_tools})
                        precision_ag_context = (precision_ag_context + "\n\n" if precision_ag_context else "") + tool_result
                    elif tc_name == 'add_scout_observation_tool' and PRECISION_AG_AVAILABLE:
                        fid = int(tc_args.get('field_id', 0) or 0)
                        print(f"[Advisory Agent] Executing Add Scout Observation: field_id={fid}")
                        tool_result = add_scout_observation_tool.invoke({
                            "field_id":  fid,
                            "category":  tc_args.get('category', 'General'),
                            "severity":  tc_args.get('severity', 'Low'),
                            "notes":     tc_args.get('notes', ''),
                            "people_id": people_id_for_tools,
                        })
                        precision_ag_context = (precision_ag_context + "\n\n" if precision_ag_context else "") + tool_result
                    elif tc_name == 'get_field_activity_log_tool' and PRECISION_AG_AVAILABLE:
                        fid = int(tc_args.get('field_id', 0) or 0)
                        print(f"[Advisory Agent] Executing Get Activity Log: field_id={fid}")
                        tool_result = get_field_activity_log_tool.invoke({"field_id": fid, "people_id": people_id_for_tools})
                        precision_ag_context = (precision_ag_context + "\n\n" if precision_ag_context else "") + tool_result
                    elif tc_name == 'log_field_activity_tool' and PRECISION_AG_AVAILABLE:
                        fid = int(tc_args.get('field_id', 0) or 0)
                        print(f"[Advisory Agent] Executing Log Field Activity: field_id={fid}")
                        tool_result = log_field_activity_tool.invoke({
                            "field_id":       fid,
                            "activity_type":  tc_args.get('activity_type', 'Other'),
                            "activity_date":  tc_args.get('activity_date', ''),
                            "product":        tc_args.get('product', ''),
                            "rate":           float(tc_args.get('rate', 0) or 0) or None,
                            "rate_unit":      tc_args.get('rate_unit', ''),
                            "operator_name":  tc_args.get('operator_name', ''),
                            "notes":          tc_args.get('notes', ''),
                            "people_id":      people_id_for_tools,
                        })
                        precision_ag_context = (precision_ag_context + "\n\n" if precision_ag_context else "") + tool_result
                    elif tc_name == 'add_soil_sample_tool' and PRECISION_AG_AVAILABLE:
                        fid = int(tc_args.get('field_id', 0) or 0)
                        print(f"[Advisory Agent] Executing Add Soil Sample: field_id={fid}")
                        tool_result = add_soil_sample_tool.invoke({
                            "field_id":       fid,
                            "sample_label":   tc_args.get('sample_label', 'Sample'),
                            "ph":             float(tc_args.get('ph', 0) or 0) or None,
                            "organic_matter": float(tc_args.get('organic_matter', 0) or 0) or None,
                            "nitrogen":       float(tc_args.get('nitrogen', 0) or 0) or None,
                            "phosphorus":     float(tc_args.get('phosphorus', 0) or 0) or None,
                            "potassium":      float(tc_args.get('potassium', 0) or 0) or None,
                            "sample_date":    tc_args.get('sample_date', ''),
                            "depth_cm":       int(tc_args.get('depth_cm', 30) or 30),
                            "notes":          tc_args.get('notes', ''),
                            "people_id":      people_id_for_tools,
                        })
                        precision_ag_context = (precision_ag_context + "\n\n" if precision_ag_context else "") + tool_result
                    elif tc_name == 'get_field_gdd_tool' and PRECISION_AG_AVAILABLE:
                        fid = int(tc_args.get('field_id', 0) or 0)
                        days = int(tc_args.get('days', 180) or 180)
                        print(f"[Advisory Agent] Executing Get GDD: field_id={fid}, days={days}")
                        tool_result = get_field_gdd_tool.invoke({"field_id": fid, "days": days, "people_id": people_id_for_tools})
                        precision_ag_context = (precision_ag_context + "\n\n" if precision_ag_context else "") + tool_result
                    elif tc_name == 'get_field_irrigation_tool' and PRECISION_AG_AVAILABLE:
                        fid = int(tc_args.get('field_id', 0) or 0)
                        days = int(tc_args.get('days', 30) or 30)
                        print(f"[Advisory Agent] Executing Get Irrigation: field_id={fid}, days={days}")
                        tool_result = get_field_irrigation_tool.invoke({"field_id": fid, "days": days, "people_id": people_id_for_tools})
                        precision_ag_context = (precision_ag_context + "\n\n" if precision_ag_context else "") + tool_result
                    elif tc_name == 'get_field_yield_forecast_tool' and PRECISION_AG_AVAILABLE:
                        fid = int(tc_args.get('field_id', 0) or 0)
                        print(f"[Advisory Agent] Executing Get Yield Forecast: field_id={fid}")
                        tool_result = get_field_yield_forecast_tool.invoke({"field_id": fid, "people_id": people_id_for_tools})
                        precision_ag_context = (precision_ag_context + "\n\n" if precision_ag_context else "") + tool_result
                    elif tc_name == 'get_field_carbon_tool' and PRECISION_AG_AVAILABLE:
                        fid = int(tc_args.get('field_id', 0) or 0)
                        print(f"[Advisory Agent] Executing Get Carbon: field_id={fid}")
                        tool_result = get_field_carbon_tool.invoke({"field_id": fid, "people_id": people_id_for_tools})
                        precision_ag_context = (precision_ag_context + "\n\n" if precision_ag_context else "") + tool_result
                    elif tc_name == 'get_farm_benchmark_tool' and PRECISION_AG_AVAILABLE:
                        print(f"[Advisory Agent] Executing Farm Benchmark")
                        tool_result = get_farm_benchmark_tool.invoke({"people_id": people_id_for_tools})
                        precision_ag_context = (precision_ag_context + "\n\n" if precision_ag_context else "") + tool_result
                    elif tc_name == 'get_field_weather_tool' and PRECISION_AG_AVAILABLE:
                        fid = int(tc_args.get('field_id', 0) or 0)
                        days = int(tc_args.get('days', 14) or 14)
                        print(f"[Advisory Agent] Executing Get Field Weather: field_id={fid}, days={days}")
                        tool_result = get_field_weather_tool.invoke({"field_id": fid, "days": days, "people_id": people_id_for_tools})
                        precision_ag_context = (precision_ag_context + "\n\n" if precision_ag_context else "") + tool_result
                    elif tc_name == 'get_field_biomass_tool' and PRECISION_AG_AVAILABLE:
                        fid = int(tc_args.get('field_id', 0) or 0)
                        print(f"[Advisory Agent] Executing Get Field Biomass: field_id={fid}")
                        tool_result = get_field_biomass_tool.invoke({"field_id": fid, "people_id": people_id_for_tools})
                        precision_ag_context = (precision_ag_context + "\n\n" if precision_ag_context else "") + tool_result
                    elif tc_name == 'improve_field_biomass_confidence_tool' and PRECISION_AG_AVAILABLE:
                        fid = int(tc_args.get('field_id', 0) or 0)
                        print(f"[Advisory Agent] Executing Improve Biomass Confidence: field_id={fid}")
                        tool_result = improve_field_biomass_confidence_tool.invoke({"field_id": fid, "people_id": people_id_for_tools})
                        precision_ag_context = (precision_ag_context + "\n\n" if precision_ag_context else "") + tool_result
                    elif tc_name == 'get_field_maturity_tool' and PRECISION_AG_AVAILABLE:
                        fid = int(tc_args.get('field_id', 0) or 0)
                        print(f"[Advisory Agent] Executing Get Field Maturity: field_id={fid}")
                        tool_result = get_field_maturity_tool.invoke({"field_id": fid, "people_id": people_id_for_tools})
                        precision_ag_context = (precision_ag_context + "\n\n" if precision_ag_context else "") + tool_result
                    elif tc_name == 'log_maturity_sample_tool' and PRECISION_AG_AVAILABLE:
                        fid = int(tc_args.get('field_id', 0) or 0)
                        print(f"[Advisory Agent] Executing Log Maturity Sample: field_id={fid}")
                        tool_result = log_maturity_sample_tool.invoke({
                            "field_id":         fid,
                            "sample_date":      str(tc_args.get('sample_date', '') or ''),
                            "brix":             tc_args.get('brix'),
                            "anthocyanin_mg_g": tc_args.get('anthocyanin_mg_g'),
                            "firmness_kgf":     tc_args.get('firmness_kgf'),
                            "notes":            str(tc_args.get('notes', '') or ''),
                            "people_id":        people_id_for_tools,
                        })
                        precision_ag_context = (precision_ag_context + "\n\n" if precision_ag_context else "") + tool_result
                    elif tc_name == 'get_field_climate_forecast_tool' and PRECISION_AG_AVAILABLE:
                        fid = int(tc_args.get('field_id', 0) or 0)
                        hrs = int(tc_args.get('hours', 72) or 72)
                        print(f"[Advisory Agent] Executing Get Climate Forecast: field_id={fid}, hours={hrs}")
                        tool_result = get_field_climate_forecast_tool.invoke({
                            "field_id":  fid,
                            "hours":     hrs,
                            "people_id": people_id_for_tools,
                        })
                        precision_ag_context = (precision_ag_context + "\n\n" if precision_ag_context else "") + tool_result
                    elif tc_name == 'get_field_water_use_tool' and PRECISION_AG_AVAILABLE:
                        fid = int(tc_args.get('field_id', 0) or 0)
                        print(f"[Advisory Agent] Executing Get Water Use: field_id={fid}")
                        tool_result = get_field_water_use_tool.invoke({
                            "field_id":  fid,
                            "people_id": people_id_for_tools,
                        })
                        precision_ag_context = (precision_ag_context + "\n\n" if precision_ag_context else "") + tool_result
                    elif tc_name == 'get_field_agronomy_tool' and PRECISION_AG_AVAILABLE:
                        fid = int(tc_args.get('field_id', 0) or 0)
                        print(f"[Advisory Agent] Executing Get Agronomy Snapshot: field_id={fid}")
                        tool_result = get_field_agronomy_tool.invoke({
                            "field_id":  fid,
                            "people_id": people_id_for_tools,
                        })
                        precision_ag_context = (precision_ag_context + "\n\n" if precision_ag_context else "") + tool_result
                    elif tc_name == 'get_field_assessment_history_tool' and PRECISION_AG_AVAILABLE:
                        fid = int(tc_args.get('field_id', 0) or 0)
                        lim = int(tc_args.get('limit', 3) or 3)
                        print(f"[Advisory Agent] Executing Get Assessment History: field_id={fid}, limit={lim}")
                        tool_result = get_field_assessment_history_tool.invoke({
                            "field_id":  fid,
                            "limit":     lim,
                            "people_id": people_id_for_tools,
                        })
                        precision_ag_context = (precision_ag_context + "\n\n" if precision_ag_context else "") + tool_result
                    elif tc_name == 'list_my_animals_tool' and FARM_DATA_AVAILABLE:
                        bid = business_id_for_tools or int(tc_args.get('business_id', 0) or 0)
                        studs_only = bool(tc_args.get('studs_only', False))
                        page = int(tc_args.get('page', 1) or 1)
                        print(f"[Advisory Agent] Executing List My Animals Tool: business_id={bid}, studs_only={studs_only}")
                        tool_result = list_my_animals_tool.invoke({
                            "business_id": bid,
                            "studs_only": studs_only,
                            "page": page,
                        })
                        farm_data_context = (farm_data_context + "\n\n" if farm_data_context else "") + tool_result
                    elif tc_name == 'list_my_listings_tool' and FARM_DATA_AVAILABLE:
                        bid = business_id_for_tools or int(tc_args.get('business_id', 0) or 0)
                        print(f"[Advisory Agent] Executing List My Listings Tool: business_id={bid}")
                        tool_result = list_my_listings_tool.invoke({"business_id": bid})
                        farm_data_context = (farm_data_context + "\n\n" if farm_data_context else "") + tool_result
                    elif tc_name == 'count_my_animals_tool' and FARM_DATA_AVAILABLE:
                        bid = business_id_for_tools or int(tc_args.get('business_id', 0) or 0)
                        print(f"[Advisory Agent] Executing Count My Animals Tool: business_id={bid}")
                        tool_result = count_my_animals_tool.invoke({"business_id": bid})
                        farm_data_context = (farm_data_context + "\n\n" if farm_data_context else "") + tool_result
                    elif tc_name == 'list_cold_chain_vehicles_tool' and FARM_DATA_AVAILABLE:
                        bid = business_id_for_tools or int(tc_args.get('business_id', 0) or 0)
                        print(f"[Advisory Agent] Executing List Cold Chain Vehicles Tool: business_id={bid}")
                        tool_result = list_cold_chain_vehicles_tool.invoke({"business_id": bid})
                        farm_data_context = (farm_data_context + "\n\n" if farm_data_context else "") + tool_result
                    elif tc_name == 'geocode_location_tool' and FARM_DATA_AVAILABLE:
                        query = tc_args.get('query', '')
                        print(f"[Advisory Agent] Executing Geocode Location: query={query!r}")
                        tool_result = geocode_location_tool.invoke({"query": query})
                        farm_data_context = (farm_data_context + "\n\n" if farm_data_context else "") + tool_result
                        # Capture [MAP_CMD] so we can append it to final_response later
                        _mc = re.search(r'\[MAP_CMD:[^\]]+\]', tool_result)
                        if _mc:
                            _map_cmd_collected = _mc.group(0)
                    # ── business_data tools ───────────────────────────────────
                    elif tc_name == 'get_business_profile_tool' and BUSINESS_DATA_AVAILABLE:
                        bid = business_id_for_tools or int(tc_args.get('business_id', 0) or 0)
                        print(f"[Advisory Agent] Executing Get Business Profile: business_id={bid}")
                        tool_result = get_business_profile_tool.invoke({"business_id": bid})
                        farm_data_context = (farm_data_context + "\n\n" if farm_data_context else "") + tool_result
                    elif tc_name == 'update_business_profile_tool' and BUSINESS_DATA_AVAILABLE:
                        bid = business_id_for_tools or int(tc_args.get('business_id', 0) or 0)
                        print(f"[Advisory Agent] Executing Update Business Profile: business_id={bid}")
                        tool_result = update_business_profile_tool.invoke({
                            "business_id":   bid,
                            "business_name": tc_args.get('business_name', ''),
                            "description":   tc_args.get('description', ''),
                            "slogan":        tc_args.get('slogan', ''),
                            "phone":         tc_args.get('phone', ''),
                            "email":         tc_args.get('email', ''),
                            "website":       tc_args.get('website', ''),
                        })
                        farm_data_context = (farm_data_context + "\n\n" if farm_data_context else "") + tool_result
                    elif tc_name == 'list_my_animals_detail_tool' and BUSINESS_DATA_AVAILABLE:
                        bid = business_id_for_tools or int(tc_args.get('business_id', 0) or 0)
                        print(f"[Advisory Agent] Executing List Animals Detail: business_id={bid}")
                        tool_result = list_my_animals_detail_tool.invoke({"business_id": bid})
                        farm_data_context = (farm_data_context + "\n\n" if farm_data_context else "") + tool_result
                    elif tc_name == 'update_animal_tool' and BUSINESS_DATA_AVAILABLE:
                        bid = business_id_for_tools or int(tc_args.get('business_id', 0) or 0)
                        print(f"[Advisory Agent] Executing Update Animal: animal_id={tc_args.get('animal_id')}")
                        tool_result = update_animal_tool.invoke({
                            "animal_id":       int(tc_args.get('animal_id', 0) or 0),
                            "business_id":     bid,
                            "price":           float(tc_args.get('price', -1) if tc_args.get('price') is not None else -1),
                            "stud_price":      float(tc_args.get('stud_price', -1) if tc_args.get('stud_price') is not None else -1),
                            "for_sale":        int(tc_args.get('for_sale', -1) if tc_args.get('for_sale') is not None else -1),
                            "for_stud":        int(tc_args.get('for_stud', -1) if tc_args.get('for_stud') is not None else -1),
                            "description":     tc_args.get('description', ''),
                            "show_on_website": int(tc_args.get('show_on_website', -1) if tc_args.get('show_on_website') is not None else -1),
                        })
                        farm_data_context = (farm_data_context + "\n\n" if farm_data_context else "") + tool_result
                    elif tc_name == 'list_produce_inventory_tool' and BUSINESS_DATA_AVAILABLE:
                        bid = business_id_for_tools or int(tc_args.get('business_id', 0) or 0)
                        print(f"[Advisory Agent] Executing List Produce Inventory: business_id={bid}")
                        tool_result = list_produce_inventory_tool.invoke({"business_id": bid})
                        farm_data_context = (farm_data_context + "\n\n" if farm_data_context else "") + tool_result
                    elif tc_name == 'update_produce_listing_tool' and BUSINESS_DATA_AVAILABLE:
                        bid = business_id_for_tools or int(tc_args.get('business_id', 0) or 0)
                        print(f"[Advisory Agent] Executing Update Produce Listing: produce_id={tc_args.get('produce_id')}")
                        tool_result = update_produce_listing_tool.invoke({
                            "produce_id":       int(tc_args.get('produce_id', 0) or 0),
                            "business_id":      bid,
                            "quantity":         float(tc_args.get('quantity', -1) if tc_args.get('quantity') is not None else -1),
                            "retail_price":     float(tc_args.get('retail_price', -1) if tc_args.get('retail_price') is not None else -1),
                            "wholesale_price":  float(tc_args.get('wholesale_price', -1) if tc_args.get('wholesale_price') is not None else -1),
                            "show_produce":     int(tc_args.get('show_produce', -1) if tc_args.get('show_produce') is not None else -1),
                            "available_date":   tc_args.get('available_date', ''),
                        })
                        farm_data_context = (farm_data_context + "\n\n" if farm_data_context else "") + tool_result
                    elif tc_name == 'list_meat_inventory_tool' and BUSINESS_DATA_AVAILABLE:
                        bid = business_id_for_tools or int(tc_args.get('business_id', 0) or 0)
                        print(f"[Advisory Agent] Executing List Meat Inventory: business_id={bid}")
                        tool_result = list_meat_inventory_tool.invoke({"business_id": bid})
                        farm_data_context = (farm_data_context + "\n\n" if farm_data_context else "") + tool_result
                    elif tc_name == 'update_meat_listing_tool' and BUSINESS_DATA_AVAILABLE:
                        bid = business_id_for_tools or int(tc_args.get('business_id', 0) or 0)
                        print(f"[Advisory Agent] Executing Update Meat Listing: meat_id={tc_args.get('meat_id')}")
                        tool_result = update_meat_listing_tool.invoke({
                            "meat_id":          int(tc_args.get('meat_id', 0) or 0),
                            "business_id":      bid,
                            "quantity":         float(tc_args.get('quantity', -1) if tc_args.get('quantity') is not None else -1),
                            "retail_price":     float(tc_args.get('retail_price', -1) if tc_args.get('retail_price') is not None else -1),
                            "wholesale_price":  float(tc_args.get('wholesale_price', -1) if tc_args.get('wholesale_price') is not None else -1),
                            "show_meat":        int(tc_args.get('show_meat', -1) if tc_args.get('show_meat') is not None else -1),
                            "available_date":   tc_args.get('available_date', ''),
                            "notes":            tc_args.get('notes', ''),
                        })
                        farm_data_context = (farm_data_context + "\n\n" if farm_data_context else "") + tool_result
                    elif tc_name == 'list_processed_food_tool' and BUSINESS_DATA_AVAILABLE:
                        bid = business_id_for_tools or int(tc_args.get('business_id', 0) or 0)
                        print(f"[Advisory Agent] Executing List Processed Food: business_id={bid}")
                        tool_result = list_processed_food_tool.invoke({"business_id": bid})
                        farm_data_context = (farm_data_context + "\n\n" if farm_data_context else "") + tool_result
                    elif tc_name == 'update_processed_food_tool' and BUSINESS_DATA_AVAILABLE:
                        bid = business_id_for_tools or int(tc_args.get('business_id', 0) or 0)
                        print(f"[Advisory Agent] Executing Update Processed Food: food_id={tc_args.get('food_id')}")
                        tool_result = update_processed_food_tool.invoke({
                            "food_id":          int(tc_args.get('food_id', 0) or 0),
                            "business_id":      bid,
                            "quantity":         float(tc_args.get('quantity', -1) if tc_args.get('quantity') is not None else -1),
                            "retail_price":     float(tc_args.get('retail_price', -1) if tc_args.get('retail_price') is not None else -1),
                            "wholesale_price":  float(tc_args.get('wholesale_price', -1) if tc_args.get('wholesale_price') is not None else -1),
                            "show_product":     int(tc_args.get('show_product', -1) if tc_args.get('show_product') is not None else -1),
                            "notes":            tc_args.get('notes', ''),
                        })
                        farm_data_context = (farm_data_context + "\n\n" if farm_data_context else "") + tool_result
                    elif tc_name == 'list_my_blog_posts_tool' and BUSINESS_DATA_AVAILABLE:
                        bid = business_id_for_tools or int(tc_args.get('business_id', 0) or 0)
                        print(f"[Advisory Agent] Executing List Blog Posts: business_id={bid}")
                        tool_result = list_my_blog_posts_tool.invoke({"business_id": bid})
                        farm_data_context = (farm_data_context + "\n\n" if farm_data_context else "") + tool_result
                    elif tc_name == 'create_blog_post_tool' and BUSINESS_DATA_AVAILABLE:
                        bid = business_id_for_tools or int(tc_args.get('business_id', 0) or 0)
                        print(f"[Advisory Agent] Executing Create Blog Post: business_id={bid}")
                        tool_result = create_blog_post_tool.invoke({
                            "business_id": bid,
                            "title":       tc_args.get('title', ''),
                            "content":     tc_args.get('content', ''),
                            "category":    tc_args.get('category', ''),
                            "publish":     int(tc_args.get('publish', 0) or 0),
                        })
                        farm_data_context = (farm_data_context + "\n\n" if farm_data_context else "") + tool_result
                    elif tc_name == 'list_my_services_tool' and BUSINESS_DATA_AVAILABLE:
                        bid = business_id_for_tools or int(tc_args.get('business_id', 0) or 0)
                        print(f"[Advisory Agent] Executing List Services: business_id={bid}")
                        tool_result = list_my_services_tool.invoke({"business_id": bid})
                        farm_data_context = (farm_data_context + "\n\n" if farm_data_context else "") + tool_result
                    elif tc_name == 'add_service_listing_tool' and BUSINESS_DATA_AVAILABLE:
                        bid = business_id_for_tools or int(tc_args.get('business_id', 0) or 0)
                        print(f"[Advisory Agent] Executing Add Service: business_id={bid}")
                        tool_result = add_service_listing_tool.invoke({
                            "business_id":       bid,
                            "title":             tc_args.get('title', ''),
                            "description":       tc_args.get('description', ''),
                            "price":             float(tc_args.get('price', -1) if tc_args.get('price') is not None else -1),
                            "contact_for_price": int(tc_args.get('contact_for_price', 0) or 0),
                            "available":         int(tc_args.get('available', 1) if tc_args.get('available') is not None else 1),
                            "phone":             tc_args.get('phone', ''),
                            "website":           tc_args.get('website', ''),
                        })
                        farm_data_context = (farm_data_context + "\n\n" if farm_data_context else "") + tool_result
                    elif tc_name == 'list_seller_orders_tool' and BUSINESS_DATA_AVAILABLE:
                        bid = business_id_for_tools or int(tc_args.get('business_id', 0) or 0)
                        print(f"[Advisory Agent] Executing List Seller Orders: business_id={bid}")
                        tool_result = list_seller_orders_tool.invoke({
                            "business_id": bid,
                            "status":      tc_args.get('status', ''),
                        })
                        farm_data_context = (farm_data_context + "\n\n" if farm_data_context else "") + tool_result
                    elif tc_name == 'confirm_seller_order_tool' and BUSINESS_DATA_AVAILABLE:
                        bid = business_id_for_tools or int(tc_args.get('business_id', 0) or 0)
                        print(f"[Advisory Agent] Executing Confirm Order: order_item_id={tc_args.get('order_item_id')}")
                        tool_result = confirm_seller_order_tool.invoke({
                            "order_item_id":           int(tc_args.get('order_item_id', 0) or 0),
                            "business_id":             bid,
                            "estimated_delivery_date": tc_args.get('estimated_delivery_date', ''),
                        })
                        farm_data_context = (farm_data_context + "\n\n" if farm_data_context else "") + tool_result
                    elif tc_name == 'reject_seller_order_tool' and BUSINESS_DATA_AVAILABLE:
                        bid = business_id_for_tools or int(tc_args.get('business_id', 0) or 0)
                        print(f"[Advisory Agent] Executing Reject Order: order_item_id={tc_args.get('order_item_id')}")
                        tool_result = reject_seller_order_tool.invoke({
                            "order_item_id": int(tc_args.get('order_item_id', 0) or 0),
                            "business_id":   bid,
                            "reason":        tc_args.get('reason', ''),
                        })
                        farm_data_context = (farm_data_context + "\n\n" if farm_data_context else "") + tool_result
                    elif tc_name == 'ship_seller_order_tool' and BUSINESS_DATA_AVAILABLE:
                        bid = business_id_for_tools or int(tc_args.get('business_id', 0) or 0)
                        print(f"[Advisory Agent] Executing Ship Order: order_item_id={tc_args.get('order_item_id')}")
                        tool_result = ship_seller_order_tool.invoke({
                            "order_item_id":           int(tc_args.get('order_item_id', 0) or 0),
                            "business_id":             bid,
                            "tracking_number":         tc_args.get('tracking_number', ''),
                            "estimated_delivery_date": tc_args.get('estimated_delivery_date', ''),
                        })
                        farm_data_context = (farm_data_context + "\n\n" if farm_data_context else "") + tool_result
                    elif tc_name == 'list_cold_chain_readings_tool' and BUSINESS_DATA_AVAILABLE:
                        bid = business_id_for_tools or int(tc_args.get('business_id', 0) or 0)
                        print(f"[Advisory Agent] Executing List Cold Chain Readings: business_id={bid}")
                        tool_result = list_cold_chain_readings_tool.invoke({
                            "business_id": bid,
                            "vehicle_id":  int(tc_args.get('vehicle_id', 0) or 0),
                            "limit":       int(tc_args.get('limit', 20) or 20),
                        })
                        farm_data_context = (farm_data_context + "\n\n" if farm_data_context else "") + tool_result
                    elif tc_name == 'log_cold_chain_reading_tool' and BUSINESS_DATA_AVAILABLE:
                        bid = business_id_for_tools or int(tc_args.get('business_id', 0) or 0)
                        print(f"[Advisory Agent] Executing Log Cold Chain Reading: vehicle_id={tc_args.get('vehicle_id')}")
                        tool_result = log_cold_chain_reading_tool.invoke({
                            "vehicle_id":  int(tc_args.get('vehicle_id', 0) or 0),
                            "business_id": bid,
                            "temp_c":      float(tc_args.get('temp_c', 0) or 0),
                            "notes":       tc_args.get('notes', ''),
                        })
                        farm_data_context = (farm_data_context + "\n\n" if farm_data_context else "") + tool_result
                    elif tc_name == 'list_cold_chain_shipments_tool' and BUSINESS_DATA_AVAILABLE:
                        bid = business_id_for_tools or int(tc_args.get('business_id', 0) or 0)
                        print(f"[Advisory Agent] Executing List Cold Chain Shipments: business_id={bid}")
                        tool_result = list_cold_chain_shipments_tool.invoke({
                            "business_id": bid,
                            "status":      tc_args.get('status', ''),
                        })
                        farm_data_context = (farm_data_context + "\n\n" if farm_data_context else "") + tool_result
                    elif tc_name == 'list_my_certifications_tool' and BUSINESS_DATA_AVAILABLE:
                        bid = business_id_for_tools or int(tc_args.get('business_id', 0) or 0)
                        print(f"[Advisory Agent] Executing List Certifications: business_id={bid}")
                        tool_result = list_my_certifications_tool.invoke({"business_id": bid})
                        farm_data_context = (farm_data_context + "\n\n" if farm_data_context else "") + tool_result
                    elif tc_name == 'add_certification_tool' and BUSINESS_DATA_AVAILABLE:
                        bid = business_id_for_tools or int(tc_args.get('business_id', 0) or 0)
                        print(f"[Advisory Agent] Executing Add Certification: business_id={bid}")
                        tool_result = add_certification_tool.invoke({
                            "business_id":          bid,
                            "certification_type":   tc_args.get('certification_type', ''),
                            "issuing_body":         tc_args.get('issuing_body', ''),
                            "certification_number": tc_args.get('certification_number', ''),
                            "issue_date":           tc_args.get('issue_date', ''),
                            "expiry_date":          tc_args.get('expiry_date', ''),
                            "notes":                tc_args.get('notes', ''),
                        })
                        farm_data_context = (farm_data_context + "\n\n" if farm_data_context else "") + tool_result
                    elif tc_name == 'search_plants_tool' and KNOWLEDGE_BASE_AVAILABLE:
                        query = tc_args.get('query', '')
                        ptype = tc_args.get('plant_type', '')
                        print(f"[Advisory Agent] Executing Search Plants: query='{query}', type='{ptype}'")
                        tool_result = search_plants_tool.invoke({"query": query, "plant_type": ptype})
                        knowledge_base_context = (knowledge_base_context + "\n\n" if knowledge_base_context else "") + tool_result
                    elif tc_name == 'get_plant_detail_tool' and KNOWLEDGE_BASE_AVAILABLE:
                        pid = int(tc_args.get('plant_id', 0) or 0)
                        print(f"[Advisory Agent] Executing Get Plant Detail: plant_id={pid}")
                        tool_result = get_plant_detail_tool.invoke({"plant_id": pid})
                        knowledge_base_context = (knowledge_base_context + "\n\n" if knowledge_base_context else "") + tool_result
                    elif tc_name == 'search_ingredients_tool' and KNOWLEDGE_BASE_AVAILABLE:
                        query = tc_args.get('query', '')
                        cat = tc_args.get('category', '')
                        print(f"[Advisory Agent] Executing Search Ingredients: query='{query}', category='{cat}'")
                        tool_result = search_ingredients_tool.invoke({"query": query, "category": cat})
                        knowledge_base_context = (knowledge_base_context + "\n\n" if knowledge_base_context else "") + tool_result
                    elif tc_name == 'get_ingredient_detail_tool' and KNOWLEDGE_BASE_AVAILABLE:
                        iid = int(tc_args.get('ingredient_id', 0) or 0)
                        print(f"[Advisory Agent] Executing Get Ingredient Detail: ingredient_id={iid}")
                        tool_result = get_ingredient_detail_tool.invoke({"ingredient_id": iid})
                        knowledge_base_context = (knowledge_base_context + "\n\n" if knowledge_base_context else "") + tool_result
                    elif tc_name == 'get_animal_detail_tool' and KNOWLEDGE_BASE_AVAILABLE:
                        aid = int(tc_args.get('animal_id', 0) or 0)
                        print(f"[Advisory Agent] Executing Get Animal Detail: animal_id={aid}")
                        tool_result = get_animal_detail_tool.invoke({
                            "animal_id": aid,
                            "people_id": people_id_for_tools,
                        })
                        farm_data_context = (farm_data_context + "\n\n" if farm_data_context else "") + tool_result
                    elif tc_name == 'draft_produce_listing_tool' and ACTIONS_AVAILABLE:
                        bid = business_id_for_tools or int(tc_args.get('business_id', 0) or 0)
                        print(f"[Advisory Agent] Executing Draft Produce Listing: business_id={bid}")
                        tool_result = draft_produce_listing_tool.invoke({
                            "ingredient_name":  tc_args.get('ingredient_name', ''),
                            "quantity":         float(tc_args.get('quantity', 0) or 0),
                            "measurement":      tc_args.get('measurement', ''),
                            "retail_price":     float(tc_args.get('retail_price', 0) or 0),
                            "wholesale_price":  float(tc_args.get('wholesale_price', 0) or 0),
                            "available_date":   tc_args.get('available_date', ''),
                            "people_id":        people_id_for_tools,
                            "business_id":      bid,
                        })
                        actions_context = (actions_context + "\n\n" if actions_context else "") + tool_result
                    elif tc_name == 'draft_event_tool' and ACTIONS_AVAILABLE:
                        bid = business_id_for_tools or int(tc_args.get('business_id', 0) or 0)
                        print(f"[Advisory Agent] Executing Draft Event: business_id={bid}")
                        tool_result = draft_event_tool.invoke({
                            "event_name":             tc_args.get('event_name', ''),
                            "description":            tc_args.get('description', ''),
                            "start_date":             tc_args.get('start_date', ''),
                            "end_date":               tc_args.get('end_date', ''),
                            "location_name":          tc_args.get('location_name', ''),
                            "city":                   tc_args.get('city', ''),
                            "state":                  tc_args.get('state', ''),
                            "is_free":                bool(tc_args.get('is_free', True)),
                            "registration_required":  bool(tc_args.get('registration_required', False)),
                            "people_id":              people_id_for_tools,
                            "business_id":            bid,
                        })
                        actions_context = (actions_context + "\n\n" if actions_context else "") + tool_result
                    elif tc_name == 'draft_blog_post_tool' and ACTIONS_AVAILABLE:
                        bid = business_id_for_tools or int(tc_args.get('business_id', 0) or 0)
                        print(f"[Advisory Agent] Executing Draft Blog Post: business_id={bid}")
                        tool_result = draft_blog_post_tool.invoke({
                            "title":       tc_args.get('title', ''),
                            "content":     tc_args.get('content', ''),
                            "category":    tc_args.get('category', ''),
                            "people_id":   people_id_for_tools,
                            "business_id": bid,
                        })
                        actions_context = (actions_context + "\n\n" if actions_context else "") + tool_result
                    elif tc_name == 'planting_calendar_tool' and AGRONOMY_AVAILABLE:
                        print(f"[Advisory Agent] Executing Planting Calendar: {tc_args.get('crop', '')}")
                        tool_result = planting_calendar_tool.invoke({
                            "crop": tc_args.get('crop', ''),
                            "zone": int(tc_args.get('zone', 0) or 0),
                            "lat":  float(tc_args.get('lat', 0) or 0),
                            "lon":  float(tc_args.get('lon', 0) or 0),
                        })
                        agronomy_context = (agronomy_context + "\n\n" if agronomy_context else "") + tool_result
                    elif tc_name == 'irrigation_schedule_tool' and AGRONOMY_AVAILABLE:
                        print(f"[Advisory Agent] Executing Irrigation Schedule: {tc_args.get('crop', '')}")
                        tool_result = irrigation_schedule_tool.invoke({
                            "crop":            tc_args.get('crop', ''),
                            "stage":           tc_args.get('stage', 'mid'),
                            "soil_type":       tc_args.get('soil_type', 'loam'),
                            "climate":         tc_args.get('climate', 'temperate'),
                            "days_since_rain": int(tc_args.get('days_since_rain', 0) or 0),
                        })
                        agronomy_context = (agronomy_context + "\n\n" if agronomy_context else "") + tool_result
                    elif tc_name == 'manure_pairing_tool' and AGRONOMY_AVAILABLE:
                        print(f"[Advisory Agent] Executing Manure Pairing: {tc_args.get('crop', '')}")
                        tool_result = manure_pairing_tool.invoke({
                            "crop":              tc_args.get('crop', ''),
                            "available_manures": tc_args.get('available_manures', ''),
                        })
                        agronomy_context = (agronomy_context + "\n\n" if agronomy_context else "") + tool_result
                    elif tc_name == 'save_recipe_tool' and CHEF_AVAILABLE:
                        bid = business_id_for_tools or int(tc_args.get('business_id', 0) or 0)
                        print(f"[Advisory Agent] Executing Save Recipe: business_id={bid}")
                        tool_result = save_recipe_tool.invoke({
                            "name":          tc_args.get('name', ''),
                            "items_json":    tc_args.get('items_json', ''),
                            "portion_yield": int(tc_args.get('portion_yield', 1) or 1),
                            "menu_price":    float(tc_args.get('menu_price', 0) or 0),
                            "business_id":   bid,
                        })
                        chef_context = (chef_context + "\n\n" if chef_context else "") + tool_result
                    elif tc_name == 'cost_recipe_tool' and CHEF_AVAILABLE:
                        bid = business_id_for_tools or int(tc_args.get('business_id', 0) or 0)
                        print(f"[Advisory Agent] Executing Cost Recipe: business_id={bid}")
                        tool_result = cost_recipe_tool.invoke({
                            "recipe_name": tc_args.get('recipe_name', ''),
                            "business_id": bid,
                        })
                        chef_context = (chef_context + "\n\n" if chef_context else "") + tool_result
                    elif tc_name == 'seasonal_menu_tool' and CHEF_AVAILABLE:
                        bid = business_id_for_tools or int(tc_args.get('business_id', 0) or 0)
                        print(f"[Advisory Agent] Executing Seasonal Menu: business_id={bid}")
                        tool_result = seasonal_menu_tool.invoke({
                            "state":       tc_args.get('state', ''),
                            "category":    tc_args.get('category', ''),
                            "business_id": bid,
                            "limit":       int(tc_args.get('limit', 20) or 20),
                        })
                        chef_context = (chef_context + "\n\n" if chef_context else "") + tool_result
                    elif tc_name == 'set_par_tool' and CHEF_AVAILABLE:
                        bid = business_id_for_tools or int(tc_args.get('business_id', 0) or 0)
                        print(f"[Advisory Agent] Executing Set Par: business_id={bid}")
                        tool_result = set_par_tool.invoke({
                            "ingredient_name":       tc_args.get('ingredient_name', ''),
                            "unit":                  tc_args.get('unit', ''),
                            "on_hand":               float(tc_args.get('on_hand', 0) or 0),
                            "par_level":             float(tc_args.get('par_level', 0) or 0),
                            "reorder_at":            float(tc_args.get('reorder_at', 0) or 0),
                            "preferred_business_id": int(tc_args.get('preferred_business_id', 0) or 0),
                            "business_id":           bid,
                        })
                        chef_context = (chef_context + "\n\n" if chef_context else "") + tool_result
                    elif tc_name == 'check_par_levels_tool' and CHEF_AVAILABLE:
                        bid = business_id_for_tools or int(tc_args.get('business_id', 0) or 0)
                        print(f"[Advisory Agent] Executing Check Par Levels: business_id={bid}")
                        tool_result = check_par_levels_tool.invoke({
                            "business_id": bid,
                        })
                        chef_context = (chef_context + "\n\n" if chef_context else "") + tool_result
                    elif tc_name == 'draft_restock_order_tool' and CHEF_AVAILABLE:
                        bid = business_id_for_tools or int(tc_args.get('business_id', 0) or 0)
                        print(f"[Advisory Agent] Executing Draft Restock Order: business_id={bid}")
                        tool_result = draft_restock_order_tool.invoke({
                            "business_id": bid,
                        })
                        chef_context = (chef_context + "\n\n" if chef_context else "") + tool_result
                    elif tc_name == 'provenance_cards_tool' and CHEF_AVAILABLE:
                        print(f"[Advisory Agent] Executing Provenance Cards: {tc_args.get('ingredient_names', '')}")
                        tool_result = provenance_cards_tool.invoke({
                            "ingredient_names": tc_args.get('ingredient_names', ''),
                        })
                        chef_context = (chef_context + "\n\n" if chef_context else "") + tool_result
                    elif tc_name == 'get_recent_pest_detections_tool' and PEST_DETECTION_AVAILABLE:
                        limit = int(tc_args.get('limit', 3) or 3)
                        print(f"[Advisory Agent] Executing Recent Pest Detections: limit={limit}")
                        tool_result = get_recent_pest_detections_tool.invoke({
                            "limit": limit,
                            "people_id": str(people_id_for_tools or ""),
                        })
                        pest_history_context = (pest_history_context + "\n\n" if pest_history_context else "") + tool_result
                    elif tc_name == 'send_push_notification_tool' and PUSH_NOTIFICATIONS_AVAILABLE:
                        print(f"[Advisory Agent] Executing Send Push: title={tc_args.get('title', '')[:40]}")
                        tool_result = send_push_notification_tool.invoke({
                            "title":     tc_args.get('title', ''),
                            "body":      tc_args.get('body', ''),
                            "url":       tc_args.get('url', '/'),
                            "people_id": str(people_id_for_tools or ""),
                        })
                        push_context = (push_context + "\n\n" if push_context else "") + tool_result
                    elif tc_name == 'check_my_weather_alerts_tool' and WEATHER_ALERTS_AVAILABLE:
                        days = int(tc_args.get('days_ahead', 2) or 2)
                        print(f"[Advisory Agent] Executing Check Weather Alerts: days={days}")
                        tool_result = check_my_weather_alerts_tool.invoke({
                            "days_ahead": days,
                            "people_id":  str(people_id_for_tools or ""),
                        })
                        weather_alerts_context = (weather_alerts_context + "\n\n" if weather_alerts_context else "") + tool_result
                    elif tc_name == 'get_my_recent_history_tool' and HISTORY_STORE_AVAILABLE:
                        et = tc_args.get('entry_type', '') or ''
                        limit = int(tc_args.get('limit', 5) or 5)
                        print(f"[Advisory Agent] Executing Recent History: type={et} limit={limit}")
                        tool_result = get_my_recent_history_tool.invoke({
                            "entry_type": et,
                            "limit":      limit,
                            "people_id":  str(people_id_for_tools or ""),
                        })
                        history_context = (history_context + "\n\n" if history_context else "") + tool_result
                    elif tc_name == 'get_tracked_grants_tool' and BUSINESS_OPS_AVAILABLE:
                        bid = business_id_for_tools or int(tc_args.get('business_id', 0) or 0)
                        print(f"[Advisory Agent] Executing Get Tracked Grants: business_id={bid}")
                        tool_result = get_tracked_grants_tool.invoke({
                            "business_id": bid,
                            "people_id": str(people_id_for_tools or ""),
                        })
                        grants_context = (grants_context + "\n\n" if grants_context else "") + tool_result
                    elif tc_name == 'calculate_shelf_life_tool' and BUSINESS_OPS_AVAILABLE:
                        vid = int(tc_args.get('vehicle_id', 0) or 0)
                        bid = business_id_for_tools or int(tc_args.get('business_id', 0) or 0)
                        print(f"[Advisory Agent] Executing Shelf Life Calc: vehicle_id={vid} product={tc_args.get('product_type')}")
                        tool_result = calculate_shelf_life_tool.invoke({
                            "vehicle_id":              vid,
                            "product_type":            tc_args.get('product_type', 'general'),
                            "original_shelf_life_days": int(tc_args.get('original_shelf_life_days', 7) or 7),
                            "lookback_hours":          int(tc_args.get('lookback_hours', 48) or 48),
                            "business_id":             bid,
                            "people_id":               str(people_id_for_tools or ""),
                        })
                        grants_context = (grants_context + "\n\n" if grants_context else "") + tool_result
                    elif tc_name == 'tell_joke_tool' and JOKES_AVAILABLE:
                        print(f"[Advisory Agent] Executing Tell Joke Tool for people_id={people_id_for_tools}")
                        tool_result = tell_joke_tool.invoke({
                            "people_id": str(people_id_for_tools or ""),
                        })
                        # Joke is the final response — short-circuit the loop
                        final_response = tool_result
                        break
                continue  # Loop back to LLM with new context

            # No tool calls - we have our answer
            final_response = response.content if hasattr(response, 'content') else str(response)
            break
        else:
            final_response = response.content if hasattr(response, 'content') else str(response)

    except Exception as e:
        print(f"[Advisory Agent] Error: {e}")
        return {
            "diagnosis": "I'm having trouble generating advice right now. Please try again.",
            "recommendations": ["Consult a local expert"]
        }

    # Append any captured [MAP_CMD] marker so the widget can fire the map event.
    # If final_response is empty (all iterations consumed by tool calls), supply a
    # default confirmation so the widget never shows "No response received."
    if _map_cmd_collected:
        if not final_response or not final_response.strip():
            final_response = "Map updated."
        if _map_cmd_collected not in final_response:
            final_response = final_response + "\n" + _map_cmd_collected

    if not final_response or not final_response.strip():
        final_response = (
            "I'm not quite sure I caught what y'all are asking about — could you give me a bit more detail? "
            "Are you asking about a specific field, your livestock, crop conditions, or the weather? "
            "Holler at me with a little more context and I'll get you sorted right out."
        )

    # 6. Parse Recommendations (Simple Heuristic)
    recommendations = []
    for line in final_response.split('\n'):
        line = line.strip()
        if line and any(kw in line.lower() for kw in ['recommend', 'consider', 'try', 'ensure', 'avoid', 'use', 'apply']):
            clean_line = line.replace('**', '').replace('*', '').replace('#', '').strip('- ')
            if clean_line and len(clean_line) > 15:
                recommendations.append(clean_line)

    result = {
        "diagnosis": final_response,
        "recommendations": recommendations[:5] if recommendations else ["Consider consulting a local expert"],
        "citations": rag_citations[:12],
        "timings": rag_timings,
    }

    if weather_data:
        result["weather_conditions"] = weather_data

    # Stream final tokens if a queue is registered
    try:
        _tid = state.get("thread_id") or ""
        _q = _get_stream_queue(_tid) if _tid else None
        if _q is not None and final_response:
            # Chunk into ~40-char pieces for progressive UI
            step = 48
            for i in range(0, len(final_response), step):
                _q.put({"type": "token", "content": final_response[i : i + step]})
    except Exception:
        pass

    return result


# ============================================================================
# ADVISORY NODES (Declarative - using unified engine)
# ============================================================================

def livestock_advisory_node(state: FarmState):
    """Livestock advisory with RAG (livestock_knowledge) and weather tool."""
    return run_advisory_agent(
        state,
        role_prompt="You are Saige — an expert livestock veterinarian and breed specialist with deep practical experience on farms and ranches. Give straight-talking advice on animal health, breed selection, and herd management. When an animal is sick or off, help the farmer stay calm and work through it step by step.",
        rag_systems=[rag_livestock]
    )


def crop_advisory_node(state: FarmState):
    """Crop advisory with RAG (plant_knowledge) and weather tool."""
    return run_advisory_agent(
        state,
        role_prompt="You are Saige — an expert agronomist who has worked fields from Texas Hill Country to the Salinas Valley. You specialize in crop pathology, soil health, and practical sustainable farming. Give grounded, actionable advice — what actually works in the field, not just what the textbook says.",
        rag_systems=[rag_plant]
    )


def bakasura_advisory_node(state: FarmState):
    """Bakasura docs advisory with RAG (bakasura-docs). Refuse mythology when KB empty."""
    query = (
        _latest_user_text(state)
        or " ".join(state.get("current_issues") or [])
        or state.get("assessment_summary")
        or ""
    )
    hits = []
    try:
        if rag_bakasura:
            rag_bakasura.initialize()
            hits = rag_bakasura.search(query) or []
    except Exception as e:
        print(f"[Bakasura] RAG probe failed: {e}")
        hits = []

    if not hits:
        return {
            "diagnosis": (
                "I don't have matching Oatmeal Farm Network documentation for that right now. "
                "In OFN, Bakasura is our product knowledge base for how Saige and the platform work "
                "(features, workflows, and how-tos) — not a mythological reference. "
                "Try asking about Saige capabilities, precision ag, marketplace, accounts, or a specific OFN page."
            ),
            "recommendations": [
                "Ask how Saige helps on OFN",
                "Ask about precision ag, marketplace, or account features",
            ],
            "citations": [],
        }

    return run_advisory_agent(
        state,
        role_prompt=(
            "You are Saige — OFN's farm AI advisor answering from the Bakasura product documentation. "
            "Bakasura = Oatmeal Farm Network / Saige platform docs (features, how-tos, product behavior). "
            "NEVER interpret Bakasura as Hindu mythology, demons, or folklore. "
            "Only use retrieved documentation; if docs are thin, say what is missing instead of inventing."
        ),
        rag_systems=[rag_bakasura],
    )


def news_advisory_node(state: FarmState):
    """News articles advisory with RAG (news_articles) and weather tool."""
    return run_advisory_agent(
        state,
        role_prompt="You are Saige — an agricultural news analyst and market-savvy farm advisor. Translate the latest farming news and market trends into plain, practical takeaways that help farmers make smarter decisions. Skip the fluff and get to what actually matters for their operation.",
        rag_systems=[rag_news]
    )


def joke_node(state: FarmState):
    """Dedicated joke node — calls tell_joke_tool directly, zero LLM involvement."""
    people_id = str(state.get("people_id") or "")
    print(f"[Joke Node] Serving joke for people_id={people_id or '(anonymous)'}")
    if not JOKES_AVAILABLE or not tell_joke_tool:
        return {"diagnosis": "Sorry, my joke book seems to have gone missing — try again in a bit!", "recommendations": []}
    joke = tell_joke_tool.invoke({"people_id": people_id})
    return {"diagnosis": joke, "recommendations": []}




def weather_advisory_node(state: FarmState):
    """Dedicated weather advisory for pure weather queries."""
    print("\n[Weather Advisory] Processing...")
    print(f"[Weather Advisory] Providing weather information")

    location = state.get("location")
    issues = state.get("current_issues") or []
    assessment = state.get("assessment_summary", "")
    history = state.get("history") or []
    
    # Build user query from multiple sources
    user_query = ' '.join(issues) if issues else assessment
    if not user_query or len(user_query.strip()) < 5:
        # Try to get from history
        for msg in reversed(history):
            if msg.startswith("User:"):
                user_query = msg.replace("User:", "").strip()
                break
    
    print(f"[Weather Advisory] User query: {user_query[:100] if user_query else 'None'}...")
    print(f"[Weather Advisory] Location from state: {location}")
    print(f"[Weather Advisory] Current issues: {issues}")

    # Use LLM to parse weather query if location or forecast info is missing
    forecast_days = None

    # Quick check for existing forecast tag in assessment
    forecast_match = re.search(r'\[forecast:(\d+)days\]', assessment)
    if forecast_match:
        forecast_days = int(forecast_match.group(1))
        print(f"[Weather Advisory] Forecast from assessment: {forecast_days} days")

    # If location missing or no forecast info, try structured extraction first, then fallback parsing.
    if not location or location == "Unknown" or not forecast_days:
        print(f"[Weather Advisory] Extracting location and forecast from query: {user_query[:50]}...")

        # STEP 1: Structured extraction first (LLM). Regex stays fallback.
        llm_confidence = 0.0
        parsed_query = None
        try:
            import threading
            parsed_query_result = [None]
            exception_result = [None]

            def llm_call_primary():
                try:
                    weather_parser = llm.with_structured_output(WeatherQueryParsed)
                    parse_prompt = f"""Extract weather query information from this query: "{user_query}"

Extract:
- Whether this is primarily a weather query
- Location (city, state/country) if mentioned
- Whether it's asking for a forecast (future weather)
- Number of days for forecast if mentioned (convert months to days: 1 month = 30 days)
- Whether the query has farming context (crops, livestock, etc.)
- Confidence score between 0.0 and 1.0

Examples:
- "weather in Hayward, California" -> is_weather_query: true, location: "Hayward, California", is_forecast: false, forecast_days: null, confidence: 0.95
- "150 day forecast for New York" -> is_weather_query: true, location: "New York", is_forecast: true, forecast_days: 150, confidence: 0.93
- "weather for my tomato farm in Boston" -> is_weather_query: true, location: "Boston", is_forecast: false, has_farm_context: true, confidence: 0.90
- "im in sanjose, can you check the weather in the coming days" -> is_weather_query: true, location: "Sanjose", is_forecast: true, forecast_days: 7, confidence: 0.90"""
                    parsed_query_result[0] = weather_parser.invoke(parse_prompt)
                except Exception as e:
                    exception_result[0] = e

            thread = threading.Thread(target=llm_call_primary)
            thread.daemon = True
            thread.start()
            thread.join(timeout=10)

            if thread.is_alive():
                print(f"[Weather Advisory] Primary LLM extraction timed out after 10 seconds")
            elif exception_result[0]:
                raise exception_result[0]
            else:
                parsed_query = parsed_query_result[0]
        except Exception as e:
            print(f"[Weather Advisory] Primary LLM extraction error: {e}")

        if parsed_query:
            llm_confidence = max(0.0, min(1.0, float(getattr(parsed_query, "confidence", 0.0) or 0.0)))
            parsed_location = re.sub(r'\s+', ' ', (parsed_query.location or '')).strip(" ,.;:!?")
            parsed_location = re.sub(r'^(?:in|at|near)\s+', '', parsed_location, flags=re.IGNORECASE)

            print(
                f"[Weather Advisory] Primary parse - location: {parsed_query.location}, "
                f"is_forecast: {parsed_query.is_forecast}, days: {parsed_query.forecast_days}, confidence: {llm_confidence:.2f}"
            )

            if parsed_query.is_weather_query and parsed_location and (not location or location == "Unknown") and llm_confidence >= 0.55:
                location = parsed_location
                print(f"[Weather Advisory] Accepted LLM location: {location}")

            if not forecast_days:
                if parsed_query.is_forecast and parsed_query.forecast_days and parsed_query.forecast_days > 0:
                    forecast_days = int(parsed_query.forecast_days)
                    print(f"[Weather Advisory] Accepted LLM forecast days: {forecast_days}")
                elif parsed_query.is_forecast:
                    forecast_days = 7
                    print(f"[Weather Advisory] Forecast requested, defaulting to 7 days")

        # STEP 2: Extract forecast days with regex fallback
        if not forecast_days:
            # Look for forecast patterns: "for one week", "for 7 days", "next week", etc.
            forecast_patterns = [
                r'for\s+(?:one|1)\s+week',  # "for one week" or "for 1 week"
                r'for\s+(\d+)\s+days?',  # "for 7 days" or "for 7 day"
                r'for\s+(\d+)\s+weeks?',  # "for 2 weeks"
                r'for\s+(\d+)\s+months?',  # "for 1 month"
                r'next\s+week',  # "next week"
                r'(\d+)\s+day\s+forecast',  # "7 day forecast"
                r'(?:in\s+the\s+)?coming\s+days?',  # "in the coming days"
                r'next\s+few\s+days?',  # "next few days"
            ]
            for pattern in forecast_patterns:
                match = re.search(pattern, user_query, re.IGNORECASE)
                if match:
                    if 'week' in pattern.lower() and 'one' in match.group(0).lower():
                        forecast_days = 7
                    elif 'week' in pattern.lower() and match.groups():
                        forecast_days = int(match.group(1)) * 7
                    elif 'month' in pattern.lower() and match.groups():
                        forecast_days = int(match.group(1)) * 30
                    elif match.groups():
                        forecast_days = int(match.group(1))
                    else:
                        forecast_days = 7  # Default for "next week" or "for one week"
                    print(f"[Weather Advisory] Extracted forecast days: {forecast_days}")
                    break

        # STEP 2: Extract location (stop before time-related words)
        if not location or location == "Unknown":
            # Remove forecast phrases from query to avoid capturing them
            query_for_location = user_query
            # Remove common forecast phrases
            query_for_location = re.sub(r'\s+for\s+(?:one|1|\d+)\s+(?:week|weeks?|days?|months?)', '', query_for_location, flags=re.IGNORECASE)
            query_for_location = re.sub(r'\s+next\s+week', '', query_for_location, flags=re.IGNORECASE)
            query_for_location = re.sub(r'\s+\d+\s+day\s+forecast', '', query_for_location, flags=re.IGNORECASE)
            
            # Look for location patterns (case-insensitive, stop before intent/time words)
            # Prefer "I'm in <location>" phrasing, then fall back to generic "in <location>".
            location_patterns = [
                r"\b(?:i\s+am|i'm|im)\s+in\s+([A-Za-z]+(?:\s+[A-Za-z]+){0,3})\b(?=\s*(?:,|\bcan\b|\bcould\b|\bplease\b|\bcheck\b|\bwhat\b|\bhow\b|$))",
                r'\bin\s+([A-Za-z]+(?:\s+[A-Za-z]+)*),\s*([A-Za-z]{2,}(?:\s+[A-Za-z]+)?)\b(?=\s*(?:$|[?.!]|for|next|forecast|weather|temperature|rain|climate))',
                r'\bin\s+([A-Za-z]+(?:\s+[A-Za-z]+){0,3})\b(?=\s*(?:,|for|next|will|can|could|please|check|weather|forecast|temperature|rain|climate|$|[?.!]))',
            ]
            conversational_words = {"can", "could", "will", "would", "please", "you", "check"}
            invalid_location_tokens = {
                "weather", "forecast", "temperature", "rain", "climate",
                "coming", "days", "day", "week", "weeks", "month", "months",
                "advise", "careful", "check", "please", "can", "you",
            }

            for pattern in location_patterns:
                match = re.search(pattern, query_for_location, re.IGNORECASE)
                if match:
                    groups = match.groups()
                    candidate_location = None
                    if len(groups) == 2 and groups[1]:
                        if groups[1].strip().lower() in conversational_words:
                            continue
                        candidate_location = f"{groups[0].title()}, {groups[1].title()}"
                    else:
                        candidate_location = groups[0].title()

                    # Clean up: remove any trailing time-related words
                    time_words = ['for', 'next', 'will', 'week', 'weeks', 'day', 'days', 'month', 'months']
                    location_parts = candidate_location.split()
                    # Remove trailing time words
                    while location_parts and location_parts[-1].lower() in time_words:
                        location_parts.pop()
                    candidate_location = ' '.join(location_parts).strip()

                    location_tokens = re.findall(r"[A-Za-z]+", candidate_location.lower())
                    if (
                        not location_tokens
                        or len(location_tokens) > 4
                        or location_tokens[0] in {"the", "a", "an", "my", "our", "your"}
                        or any(tok in invalid_location_tokens for tok in location_tokens)
                    ):
                        continue

                    location = candidate_location
                    print(f"[Weather Advisory] Extracted location via regex: {location}")
                    break
            

        # STEP 3: Secondary LLM fallback if regex did not resolve location.
        if not location or location == "Unknown":

            try:
                # Try LLM extraction with timeout using threading.
                import threading
                parsed_query_result = [None]
                exception_result = [None]
                
                def llm_call():
                    try:
                        weather_parser = llm.with_structured_output(WeatherQueryParsed)
                        parse_prompt = f"""Extract weather query information from this query: "{user_query}"

Extract:
- Location (city, state/country) if mentioned
- Whether it's asking for a forecast (future weather)
- Number of days for forecast if mentioned (convert months to days: 1 month = 30 days)
- Whether the query has farming context (crops, livestock, etc.)
- Confidence score between 0.0 and 1.0

Examples:
- "weather in Hayward, California" → location: "Hayward, California", is_forecast: false, forecast_days: null
- "150 day forecast for New York" → location: "New York", is_forecast: true, forecast_days: 150
- "weather for my tomato farm in Boston" → location: "Boston", is_forecast: false, has_farm_context: true"""
                        parsed_query_result[0] = weather_parser.invoke(parse_prompt)
                    except Exception as e:
                        exception_result[0] = e
                
                thread = threading.Thread(target=llm_call)
                thread.daemon = True
                thread.start()
                thread.join(timeout=10)  # 10 second timeout
                
                if thread.is_alive():
                    print(f"[Weather Advisory] LLM extraction timed out after 10 seconds, skipping")
                elif exception_result[0]:
                    raise exception_result[0]
                elif parsed_query_result[0]:
                    parsed_query = parsed_query_result[0]
                    fallback_confidence = max(0.0, min(1.0, float(getattr(parsed_query, "confidence", 0.0) or 0.0)))
                    parsed_location = re.sub(r'\s+', ' ', (parsed_query.location or '')).strip(" ,.;:!?")
                    parsed_location = re.sub(r'^(?:in|at|near)\s+', '', parsed_location, flags=re.IGNORECASE)
                    print(
                        f"[Weather Advisory] Parsed query - location: {parsed_query.location}, "
                        f"is_weather: {parsed_query.is_weather_query}, confidence: {fallback_confidence:.2f}"
                    )

                    # Update location if extracted and confidence is sufficient
                    if (
                        parsed_location
                        and parsed_query.is_weather_query
                        and (not location or location == "Unknown")
                        and fallback_confidence >= 0.55
                    ):
                        location = parsed_location
                        print(f"[Weather Advisory] Extracted location: {location}")

                    # Update forecast_days if extracted
                    if parsed_query.is_forecast and parsed_query.forecast_days and not forecast_days:
                        forecast_days = int(parsed_query.forecast_days)
                        print(f"[Weather Advisory] Extracted forecast days: {forecast_days}")
                    elif parsed_query.is_forecast and not forecast_days:
                        # If forecast requested but days not specified, default to 7
                        forecast_days = 7
                        print(f"[Weather Advisory] Forecast requested but days not specified, defaulting to 7 days")

            except Exception as e:
                print(f"[Weather Advisory] LLM extraction error: {e}")

    # Resolve location via geocoding before fetching weather to avoid bad parses.
    if location and location != "Unknown":
        try:
            resolution = weather_service.resolve_location(location, user_query)
            if resolution and resolution.get("status") == "resolved":
                canonical_location = resolution.get("canonical_location")
                confidence = resolution.get("confidence", 0.0)
                if canonical_location:
                    print(
                        f"[Weather Advisory] Location resolved: {location} -> {canonical_location} "
                        f"(confidence={confidence})"
                    )
                    location = canonical_location
            elif resolution and resolution.get("status") == "ambiguous":
                candidates = resolution.get("candidates", [])[:3]
                options = [c.get("display_name") for c in candidates if c.get("display_name")]
                pretty_options = ", ".join(options) if options else "a more specific city/region"
                return {
                    "diagnosis": (
                        f"I found multiple location matches for '{location}'. "
                        f"Please clarify the exact place (for example: {pretty_options})."
                    ),
                    "recommendations": options if options else [
                        "Add state/province and country (e.g., 'San Jose, California, US')"
                    ],
                }
            elif resolution and resolution.get("status") == "not_found":
                return {
                    "diagnosis": (
                        f"I couldn't confidently identify the location '{location}'. "
                        "Please provide city plus state/country (e.g., 'San Jose, California, US')."
                    ),
                    "recommendations": [
                        "Include city + state/province + country",
                        "Avoid abbreviations in location names",
                    ],
                }
        except Exception as e:
            print(f"[Weather Advisory] Location resolution error (continuing with raw location): {e}")

    # Fetch weather data
    if location and location != "Unknown":
        try:
            print(f"[Weather Advisory] Attempting to fetch weather for: {location}")
            weather_data = None
            
            if forecast_days and forecast_days > 1:
                print(f"[Weather Advisory] Fetching {forecast_days}-day forecast for {location}")
                weather_data = weather_service.get_forecast(location, forecast_days)

                if weather_data:
                    formatted_weather = weather_service.format_forecast_for_llm(weather_data)
                    response = f"Here's the {forecast_days}-day weather forecast for {weather_data.get('location', location)}:\n\n{formatted_weather}"
                    print(f"[Weather Advisory] Successfully fetched forecast, response length: {len(response)}")

                    return {
                        "diagnosis": response,
                        "recommendations": [],
                        "weather_conditions": weather_data
                    }
                else:
                    print(f"[Weather Advisory] Forecast failed, falling back to current weather")
                    weather_data = weather_service.get_weather(location)
            else:
                print(f"[Weather Advisory] Fetching current weather for {location}")
                weather_data = weather_service.get_weather(location)

            if weather_data:
                formatted_weather = weather_service.format_for_llm(weather_data)
                response = f"Here's the current weather for {weather_data.get('location', location)}:\n\n{formatted_weather}"
                print(f"[Weather Advisory] Successfully fetched weather, response length: {len(response)}")

                return {
                    "diagnosis": response,
                    "recommendations": [],
                    "weather_conditions": weather_data
                }
            else:
                error_msg = f"I couldn't fetch weather data for '{location}'. Please check the location name and try again."
                print(f"[Weather Advisory] Weather fetch returned None, using error message")
                return {
                    "diagnosis": error_msg,
                    "recommendations": ["Make sure the location name is spelled correctly", "Try using a city name or region"]
                }
        except Exception as e:
            print(f"[Weather Advisory] Exception while fetching weather: {e}")
            import traceback
            traceback.print_exc()
            error_msg = f"Sorry, I encountered an error while fetching weather data: {str(e)}. Please try again later."
            return {
                "diagnosis": error_msg,
                "recommendations": []
            }
    else:
        error_msg = f"I need a location to provide weather information. Your query was: '{user_query}'. Please tell me which city or region you'd like to know about."
        print(f"[Weather Advisory] No location available, user_query: {user_query}")
        return {
            "diagnosis": error_msg,
            "recommendations": ["Provide a city name (e.g., 'Boston', 'New York')", "Or provide a region (e.g., 'North region', 'Central region')"]
        }

# ============================================================================
# SUPERVISOR ORCHESTRATION (User Agent → Supervisor → Specialists → HITL)
# ============================================================================

PASSWORD_REFUSAL = (
    "I can't change or reset passwords - I don't have access to password data. "
    "Please update your password in the **Account** section of the app "
    "(Account settings / forgot-password flow)."
)


# ── helpers ──────────────────────────────────────────────────────────────────

def _latest_user_text(state: SaigeState) -> str:
    if state.get("user_message"):
        return str(state["user_message"]).strip()
    history = state.get("history") or []
    for msg in reversed(history):
        if isinstance(msg, str) and msg.startswith("User:"):
            return msg.replace("User:", "", 1).strip()
    issues = state.get("current_issues") or []
    if issues:
        return str(issues[-1]).strip()
    return ""


def _as_farm_state(state: SaigeState) -> Dict[str, Any]:
    """Project SaigeState into a FarmState-like dict for advisory leaf nodes."""
    text = _latest_user_text(state)
    history = list(state.get("history") or [])
    if text and (not history or history[-1] != f"User: {text}"):
        history = (history + [f"User: {text}"])[-40:]
    return {
        "people_id": state.get("people_id"),
        "business_id": state.get("business_id"),
        "thread_id": state.get("thread_id"),
        "user_name": state.get("user_name"),
        "location": state.get("location"),
        "farm_size": state.get("farm_size"),
        "crops": state.get("crops") or [],
        "current_issues": [text] if text else (state.get("current_issues") or []),
        "history": history,
        "assessment_summary": text or state.get("assessment_summary") or "",
        "long_term_memory": state.get("long_term_memory") or {},
        "org_memory": state.get("org_memory") or {},
        "image_data": state.get("image_data"),
        "soil_info": state.get("soil_info") or {},
        "weather_conditions": state.get("weather_conditions") or {},
        "diagnosis": None,
        "recommendations": [],
    }


def _packet_from_advisory(result: Dict[str, Any], source: str) -> Dict[str, Any]:
    return {
        "source": source,
        "text": (result or {}).get("diagnosis") or "",
        "recommendations": list((result or {}).get("recommendations") or []),
        "citations": list((result or {}).get("citations") or []),
        "latency_ms": (result or {}).get("latency_ms"),
        "meta": {
            k: (result or {}).get(k)
            for k in ("weather_conditions", "advisory_type", "soil_info", "timings")
            if (result or {}).get(k) is not None
        },
    }


def _is_account_identity_query(text: str) -> bool:
    """True for short account/profile identity asks (email, name, ids) — not farm ops."""
    t = (text or "").lower().strip()
    if not t:
        return False
    phrases = (
        "my email", "what is my email", "what's my email", "whats my email",
        "email address", "email on this account", "email on my account",
        "my name", "what is my name", "what's my name", "whats my name",
        "my phone", "what is my phone", "what's my phone",
        "people id", "peopleid", "people_id", "user id", "userid", "my id", "what is my id",
        "business id", "businessid", "business_id", "my business id", "what is my business",
        "my account", "my profile", "show my account", "business profile",
        "who am i", "what account", "which account", "signed in with",
    )
    if not any(p in t for p in phrases):
        return False
    # Long farm questions that casually mention "my name" stay on farm routes
    farmish = ("weather", "frost", "forecast", "crop", "field", "cattle", "ndvi", "soil", "irrigat", "spray", "pest")
    if len(t.split()) > 12 and any(f in t for f in farmish):
        return False
    return True


def _format_account_answer(
    text: str,
    *,
    people_id: str = "",
    business_id: Any = None,
    user_name: str = "",
    profile: Optional[Dict[str, Any]] = None,
) -> str:
    """Build a grounded account answer from profile/state — never invent contact info."""
    profile = dict(profile or {})
    lower = (text or "").lower()
    name = (user_name or "").strip() or (
        f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip()
    )
    email = (profile.get("email") or "").strip()
    phone = (profile.get("phone") or "").strip()
    bid = str(business_id or profile.get("business_id") or "").strip()
    bname = (profile.get("business_name") or "").strip()
    pid = str(people_id or profile.get("people_id") or "").strip()

    parts: List[str] = []
    wants_email = "email" in lower
    wants_phone = "phone" in lower
    wants_name = ("name" in lower or "who am i" in lower) and "business" not in lower
    wants_people = any(k in lower for k in ("people id", "peopleid", "people_id", "user id", "userid", "my id"))
    wants_biz = any(k in lower for k in ("business id", "businessid", "business_id", "my business", "which account", "what account", "signed in"))

    if wants_email:
        parts.append(f"Your email is {email}." if email else "I don't have an email on file for your account.")
    if wants_phone:
        parts.append(f"Your phone number is {phone}." if phone else "I don't have a phone number on file for your account.")
    if wants_name:
        parts.append(f"Your name is {name}." if name else "I don't have your name on file.")
    if wants_people:
        parts.append(f"Your PeopleID is {pid}." if pid else "Your PeopleID is not available in this session.")
    if wants_biz:
        if bid and bname:
            parts.append(f"You're signed in with \"{bname}\" (BusinessID {bid}).")
        elif bid:
            parts.append(f"You're signed in with BusinessID {bid}.")
        else:
            parts.append(
                "No business account is linked to this session. "
                "Select a business in Accounts (or open Saige from a business page) and ask again."
            )

    if parts:
        return " ".join(parts)

    # Generic "my account / my profile"
    lines = []
    if name:
        lines.append(f"name: {name}")
    if email:
        lines.append(f"email: {email}")
    if phone:
        lines.append(f"phone: {phone}")
    if pid:
        lines.append(f"people_id: {pid}")
    if bid:
        lines.append(f"business_id: {bid}" + (f" ({bname})" if bname else ""))
    if lines:
        return "Here is your account information (password is never shown):\n" + "\n".join(lines)
    return (
        "I couldn't load your account profile right now. "
        "Make sure you're logged in, then try asking for your name, email, PeopleID, or business ID."
    )


def _keyword_routes(text: str) -> List[str]:
    t = (text or "").lower()
    routes: List[str] = []
    if _is_account_identity_query(t):
        return ["user"]
    if any(k in t for k in ("joke", "funny", "make me laugh")):
        routes.append("joke")
    if any(k in t for k in (
        "bakasura", "how does saige", "what is saige", "oatmeal farm network",
        "ofn docs", "documentation", "how does ofn", "what is ofn",
    )):
        routes.append("bakasura")
    if any(k in t for k in ("news", "market price", "commodity", "headline", "market takeaway")):
        routes.append("news")
    if any(k in t for k in (
        "weather", "forecast", "frost", "rain", "temperature", "climate",
        "mitigation", "playbook", "protect cattle", "protect livestock",
    )):
        routes.append("weather")
    if any(k in t for k in ("cattle", "cow", "sheep", "goat", "pig", "chicken", "livestock", "herd", "breed", "animal")):
        routes.append("livestock")
    if any(k in t for k in ("crop", "plant", "soil", "tomato", "corn", "wheat", "pest", "disease", "irrigat", "spray")):
        routes.append("crop")
    if any(k in t for k in (
        "plan my week", "weekly plan", "seasonal plan", "what should i do this week",
        "schedule", "weekly farm", "planning checklist", "spring checklist", "farm planning",
    )):
        routes.append("plan")
    if any(k in t for k in (
        "ndvi", "monitor", "satellite", "zone", "precision", "field health", "got worse",
        "how is my", "how's my", "how is field", "field doing", "my field", "test field",
    )):
        routes.append("monitoring")
    if any(k in t for k in (
        "my account", "my profile", "my email", "my phone", "my name", "business profile",
        "password", "change my name", "people id", "user id", "business id",
    )):
        routes.append("user")
    if any(k in t for k in (
        "create a field", "create field", "add a field", "add field",
        "new field", "edit field", "rename field", "manage field", "enable monitoring",
    )):
        routes.append("monitoring")
        routes.append("crop")
    # de-dupe preserve order
    seen = set()
    out = []
    for r in routes:
        if r not in seen:
            seen.add(r)
            out.append(r)
    return out or ["crop"]


# ── User Agent ───────────────────────────────────────────────────────────────

def user_agent_node(state: SaigeState) -> Dict[str, Any]:
    """Identity, ACL context, account read, propose profile/field writes (no password)."""
    print("[UserAgent] start")
    people_id = str(state.get("people_id") or "")
    business_id = state.get("business_id")
    text = _latest_user_text(state)
    updates: Dict[str, Any] = {
        "user_message": text,
        "proposals": list(state.get("proposals") or []),
        "policy_violations": [],
        "mode": state.get("mode") or "farm",
    }

    # Account profile (never password)
    account_profile: Dict[str, Any] = {}
    try:
        from user_profile import get_account_profile, get_user_name, get_primary_business_id

        if people_id and not state.get("user_name"):
            updates["user_name"] = get_user_name(people_id)
        if people_id and not business_id:
            business_id = get_primary_business_id(people_id)
            updates["business_id"] = business_id
        if people_id:
            account_profile = get_account_profile(people_id, business_id) or {}
            updates["account_profile"] = account_profile
    except Exception as e:
        logger.debug("[UserAgent] profile load failed: %s", e)

    # Farm profile snapshot (business)
    if business_id:
        try:
            from business_data import get_business_profile_tool

            farm_txt = get_business_profile_tool.invoke({"business_id": int(business_id)})
            updates["farm_profile"] = {"summary": farm_txt}
        except Exception as e:
            logger.debug("[UserAgent] farm profile failed: %s", e)

    # Intent: password / account update / field manage
    intent = AccountIntent()
    lower = text.lower()
    if any(k in lower for k in ("password", "reset password", "change password", "forgot password")):
        intent.wants_password_change = True
    if _is_account_identity_query(text) or any(k in lower for k in (
        "my account", "my profile", "what is my email", "my email", "my phone",
        "business profile", "show my account", "what is my name", "my name",
        "business id", "people id", "user id",
    )):
        intent.wants_account_read = True
    if any(k in lower for k in ("update my", "change my", "edit my", "set my phone", "set my email", "change business")):
        intent.wants_account_update = True
    if any(k in lower for k in (
        "create a field", "create field", "add a field", "add field", "new field",
        "edit field", "rename field", "update field", "enable monitoring", "disable monitoring",
    )):
        intent.wants_field_manage = True

    # Optional LLM refinement when text is ambiguous (skip for clear identity reads)
    if text and not _is_account_identity_query(text) and (
        intent.wants_account_update or intent.wants_field_manage or "account" in lower
    ):
        try:
            llm = get_llm_farm()
            extractor = llm.with_structured_output(AccountIntent)
            intent = extractor.invoke(
                f'User message: "{text[:500]}"\n'
                "Detect account read/update, password change, or field manage intents. "
                "Never put password values in update_fields."
            )
        except Exception as e:
            logger.debug("[UserAgent] intent LLM failed: %s", e)

    proposals = list(updates["proposals"])

    if intent.wants_password_change:
        updates["user_packet"] = {
            "source": "user",
            "text": PASSWORD_REFUSAL,
            "recommendations": ["Open Account -> change password there."],
        }
        print("[UserAgent] password change refused")

    if intent.wants_account_read and not intent.wants_password_change:
        answer = _format_account_answer(
            text,
            people_id=people_id,
            business_id=business_id or updates.get("business_id") or state.get("business_id"),
            user_name=str(updates.get("user_name") or state.get("user_name") or ""),
            profile=account_profile,
        )
        safe = {
            k: v for k, v in (account_profile or {}).items()
            if "password" not in k.lower() and "hash" not in k.lower()
        }
        updates["user_packet"] = {
            "source": "user",
            "text": answer,
            "recommendations": [],
            "account": safe,
        }
        print(f"[UserAgent] account_read answer_len={len(answer)}")

    if intent.wants_account_update and not intent.wants_password_change:
        raw_fields = dict(intent.update_fields or {})
        # Normalize common LLM key aliases → tool args
        alias = {
            "businessphone": "phone",
            "phone_number": "phone",
            "phonenumber": "phone",
            "businessemail": "email",
            "email_address": "email",
            "businesswebsite": "website",
            "businessname": "business_name",
            "name": "business_name",
        }
        args: Dict[str, Any] = {}
        for k, v in raw_fields.items():
            if not v or "password" in str(k).lower():
                continue
            key = alias.get(str(k).lower().replace(" ", "").replace("_", ""), str(k).lower())
            args[key] = str(v).strip()
        if not args:
            # Heuristic: "update my business phone to 555-0199"
            m = re.search(
                r"(?:business\s+)?(?:phone|email|website|name)\s+(?:number\s+)?(?:to|is|=)\s+(.+)$",
                text,
                re.I,
            )
            if m:
                field = "phone" if "phone" in text.lower() else (
                    "email" if "email" in text.lower() else (
                        "website" if "website" in text.lower() else "business_name"
                    )
                )
                args = {field: m.group(1).strip()}
        if args:
            proposals.append(
                {
                    "tool": "update_business_profile",
                    "args": {"business_id": business_id, **args},
                    "risk": "low_write",
                    "domain": "account",
                    "summary": f"Update account/business profile: {', '.join(k for k in args.keys() if k != 'business_id')}",
                }
            )

    if intent.wants_field_manage:
        action = (intent.field_action or "").strip().lower()
        payload = dict(intent.field_payload or {})
        if not action or action in {"none", "update_field"}:
            if any(k in text.lower() for k in ("create", "add a field", "add field", "new field")):
                action = "create_field"
            elif any(k in text.lower() for k in ("enable monitoring", "disable monitoring", "toggle monitoring")):
                action = "toggle_monitoring"
            else:
                action = "update_field"

        try:
            bid_int = int(business_id) if business_id not in (None, "", 0, "0") else 0
        except Exception:
            bid_int = 0

        if bid_int <= 0:
            updates["user_packet"] = {
                "source": "user",
                "text": (
                    "I can create precision-ag fields once a business is linked to this session. "
                    "Select a business in your account (or open Saige from a business page), "
                    "then ask me again — for example: “Create a field named North 40, 10 acres of corn.”"
                ),
                "recommendations": [
                    "Open Accounts and select a business",
                    "Or open Precision Ag / Saige with a BusinessID",
                ],
            }
            print("[UserAgent] field manage blocked — no business_id")
        else:
            if not payload:
                payload = {"raw_request": text}
            from field_ops import parse_field_create_args

            if action == "create_field":
                parsed = parse_field_create_args({
                    **payload,
                    "business_id": bid_int,
                    "people_id": people_id,
                    "raw_request": text,
                    "monitoring_enabled": payload.get("monitoring_enabled", True),
                })
                payload = parsed
            proposals.append(
                {
                    "tool": action if action in {"create_field", "update_field", "toggle_monitoring"} else "create_field",
                    "args": {"business_id": bid_int, "people_id": people_id, **payload},
                    "risk": "low_write",
                    "domain": "precision_ag",
                    "summary": f"Precision-ag field action ({action}): {text[:120]}",
                }
            )

    updates["proposals"] = proposals
    print(f"[UserAgent] proposals={len(proposals)} password_refuse={intent.wants_password_change}")
    return updates


# ── Supervisor ───────────────────────────────────────────────────────────────

def supervisor_node(state: SaigeState) -> Dict[str, Any]:
    """Classify intent -> route 1..N specialists (incl. bakasura/news/joke)."""
    print("[Supervisor] start")
    t0 = time.perf_counter()
    text = _latest_user_text(state)
    routes = _keyword_routes(text)
    reasoning = "keyword-heuristic"
    handoff = "none"

    # Pure account/identity asks — never let the router LLM send these to weather/crop
    if _is_account_identity_query(text) or (
        state.get("user_packet")
        and not any(k in text.lower() for k in ("weather", "crop", "cattle", "field", "news", "joke", "frost", "soil", "ndvi"))
    ):
        routes = ["user"]
        reasoning = "account-identity"
        route_ms = (time.perf_counter() - t0) * 1000
        print(f"[Supervisor] routes={routes} handoff=none route_ms={route_ms:.0f} (identity)")
        return {
            "route": routes,
            "supervisor_reasoning": reasoning,
            "handoff": "none",
            "advisory_type": "user",
            "route_ms": route_ms,
        }

    # If user packet already answered password/account fully and no farm ask, keep user route
    if state.get("user_packet") and not any(
        k in text.lower() for k in ("weather", "crop", "cattle", "field", "news", "joke", "frost", "soil")
    ):
        if "user" not in routes:
            routes = ["user"] + routes

    try:
        llm = get_llm_farm()
        router = llm.with_structured_output(SupervisorRouteDecision)
        decision = router.invoke(
            "You are Saige Supervisor for an agricultural assistant.\n"
            f'User: "{text[:400]}"\n'
            "Return at most 2 routes from: crop, livestock, weather, plan, monitoring, bakasura, news, joke, user.\n"
            "Prefer the single best route when possible.\n"
            "Prefer route=user ONLY for account/profile/identity questions "
            "(my name, my email, PeopleID, BusinessID, my account). Never route those to weather.\n"
            "Use bakasura for OFN/Saige product/docs questions.\n"
            "Use news for market/ag news.\n"
            "Use joke only for joke requests.\n"
            "Use user for account/profile questions.\n"
            "handoff=none unless clearly asking for onboarding(cassia)/artisan(rosemarie)/chef pantry(pairsley)/restaurant(chef)."
        )
        cleaned = []
        for r in decision.routes or []:
            r = (r or "").strip().lower()
            if r == "account":
                r = "user"
            if r in VALID_ROUTES and r not in cleaned:
                cleaned.append(r)
        if cleaned:
            routes = cleaned[:2]
            reasoning = decision.reasoning or reasoning
            handoff = (decision.handoff or "none").lower()
    except Exception as e:
        logger.warning("[Supervisor] LLM route failed (%s); using keywords %s", e, routes)

    # Always include user route if we already have user_packet / proposals from User Agent
    if (state.get("user_packet") or state.get("proposals")) and "user" not in routes:
        routes = ["user"] + routes

    route_ms = (time.perf_counter() - t0) * 1000
    print(f"[Supervisor] routes={routes} handoff={handoff} route_ms={route_ms:.0f}")
    return {
        "route": routes,
        "supervisor_reasoning": reasoning,
        "handoff": handoff,
        "advisory_type": ",".join(routes),
        "route_ms": route_ms,
    }


def joke_route_node(state: SaigeState) -> Dict[str, Any]:
    result = joke_node(_as_farm_state(state))
    joke = (result or {}).get("diagnosis") or "Why did the scarecrow win an award? Because he was outstanding in his field!"
    history = list(state.get("history") or [])
    history.append(f"AI: {joke}")
    return {
        "joke_text": joke,
        "diagnosis": joke,
        "recommendations": [],
        "assessment_summary": _latest_user_text(state),
        "history": history[-40:],
        "advisory_type": "joke",
    }


# ── Specialist dispatch (parallel fan-out with hard wall-clock deadline) ─────

def specialist_dispatch_node(state: SaigeState) -> Dict[str, Any]:
    """Run selected specialists concurrently; accumulate packets. Does not write to farm DB."""
    import concurrent.futures
    from config import SPECIALIST_TIMEOUT_SECONDS

    print("[Specialists] start (parallel)")
    routes = [r for r in (state.get("route") or []) if r != "joke"]
    knowledge = [r for r in routes if r in ("weather", "livestock", "crop", "bakasura", "news")]
    farm = _as_farm_state(state)
    updates: Dict[str, Any] = {}
    t0 = time.perf_counter()
    deadline = SPECIALIST_TIMEOUT_SECONDS

    def _safe(name: str, fn):
        try:
            print(f"[Specialists] -> {name}")
            return fn(farm)
        except Exception as e:
            logger.exception("[Specialists] %s failed", name)
            return {"diagnosis": f"({name} unavailable: {e})", "recommendations": [], "citations": []}

    jobs = []
    if "weather" in knowledge:
        jobs.append(("weather_packet", "weather", lambda: _packet_from_advisory(_safe("weather", weather_advisory_node), "weather")))
    if "livestock" in knowledge:
        jobs.append(("livestock_packet", "livestock", lambda: _packet_from_advisory(_safe("livestock", livestock_advisory_node), "livestock")))
    if "crop" in knowledge:
        jobs.append(("crop_packet", "crop", lambda: _packet_from_advisory(_safe("crop", crop_advisory_node), "crop")))
    if "bakasura" in knowledge:
        jobs.append(("bakasura_packet", "bakasura", lambda: _packet_from_advisory(_safe("bakasura", bakasura_advisory_node), "bakasura")))
    if "news" in knowledge:
        jobs.append(("news_packet", "news", lambda: _packet_from_advisory(_safe("news", news_advisory_node), "news")))

    if jobs:
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, len(jobs))) as pool:
            future_map = {pool.submit(fn): (key, name) for key, name, fn in jobs}
            done, not_done = concurrent.futures.wait(
                future_map.keys(),
                timeout=deadline,
                return_when=concurrent.futures.ALL_COMPLETED,
            )
            for fut in done:
                key, name = future_map[fut]
                try:
                    updates[key] = fut.result(timeout=0)
                except Exception as e:
                    logger.exception("[Specialists] %s failed", name)
                    updates[key] = {
                        "source": name,
                        "text": f"({name} unavailable: {e})",
                        "recommendations": [],
                        "citations": [],
                    }
            for fut in not_done:
                key, name = future_map[fut]
                fut.cancel()
                updates[key] = {
                    "source": name,
                    "text": (
                        f"I started looking into {name}, but need a moment more for a full answer. "
                        f"Ask again focused on {name} only, or give me a narrower question."
                    ),
                    "recommendations": [f"Retry with a focused {name} question"],
                    "citations": [],
                }

    if "user" in routes and state.get("user_packet"):
        updates["user_packet"] = state.get("user_packet")

    # Monitoring / plan — lightweight only when requested
    if "monitoring" in routes:
        updates["monitoring_packet"] = _run_monitoring_agent(state)
    if "plan" in routes:
        updates["plan_packet"] = _run_plan_advisory(state, updates)

    # Always inject concrete weather-mitigation playbook when asked (don't rely on LLM tool call)
    text_lower = (_latest_user_text(state) or "").lower()
    if any(k in text_lower for k in ("mitigation", "playbook", "protect cattle", "protect livestock")) or (
        "frost" in text_lower and any(k in text_lower for k in ("protect", "plan", "livestock", "cattle"))
    ):
        try:
            from weather_mitigation import format_for_llm, resolve_hazard
            hazard = resolve_hazard(text_lower) or "frost"
            phase = "imminent"
            if any(k in text_lower for k in ("planning", "prepare", "before")):
                phase = "planning"
            elif any(k in text_lower for k in ("recovery", "after")):
                phase = "recovery"
            elif any(k in text_lower for k in ("during", "active", "tonight")):
                phase = "imminent"
            playbook = format_for_llm(hazard, phase)
            wp = updates.get("weather_packet") or {
                "source": "weather",
                "text": "",
                "recommendations": [],
                "citations": [],
            }
            existing = (wp.get("text") or "").strip()
            wp["text"] = (playbook + ("\n\n" + existing if existing else "")).strip()
            wp["recommendations"] = list(wp.get("recommendations") or []) + [
                f"Follow {hazard} {phase} mitigation steps",
            ]
            updates["weather_packet"] = wp
            if "plan" not in routes and "plan_packet" not in updates:
                updates["plan_packet"] = _run_plan_advisory(state, updates)
        except Exception as e:
            logger.debug("[Specialists] mitigation inject failed: %s", e)

    elapsed = (time.perf_counter() - t0) * 1000
    print(f"[Specialists] packets={[k for k in updates if k.endswith('_packet')]} specialist_ms={elapsed:.0f}")
    updates["specialist_ms"] = elapsed
    return updates


def _run_monitoring_agent(state: SaigeState) -> Dict[str, Any]:
    """Multi-step field investigation using precision_ag read tools; persist findings."""
    people_id = str(state.get("people_id") or "")
    business_id = str(state.get("business_id") or "")
    findings: List[Dict[str, Any]] = []
    lines = ["Crop Monitoring Agent investigation:"]
    text_q = _latest_user_text(state)

    try:
        from precision_ag import (
            list_my_fields_tool,
            get_field_alerts_tool,
            get_field_analysis_tool,
            resolve_field_by_name,
        )

        fields_txt = list_my_fields_tool.invoke({"people_id": people_id}) if people_id else "No people_id"
        lines.append(str(fields_txt)[:2000])
        alerts_txt = get_field_alerts_tool.invoke({"field_id": 0, "people_id": people_id}) if people_id else ""
        if alerts_txt:
            lines.append("Alerts:\n" + str(alerts_txt)[:1500])
            findings.append({"rank": 1, "text": str(alerts_txt)[:500], "field_id": None})

        # Resolve named field from the user question and pull latest analysis
        resolved = resolve_field_by_name(text_q, people_id) if people_id else None
        if resolved:
            fid = int(resolved.get("fieldid") or resolved.get("FieldID") or 0)
            fname = resolved.get("name") or resolved.get("Name") or f"#{fid}"
            if fid:
                analysis = get_field_analysis_tool.invoke({
                    "field_id": fid,
                    "people_id": people_id,
                })
                lines.append(f"Resolved field '{fname}' → analysis:\n{analysis}")
                findings.append({"rank": 0, "text": str(analysis)[:800], "field_id": fid})
            else:
                lines.append(f"Matched field name '{fname}' but could not read FieldID.")
        elif any(k in text_q.lower() for k in ("how is", "how's", "doing", "status", "health")):
            lines.append(
                "No field name matched the question. Use a name from the field list above "
                "(never ask the farmer for a raw FieldID if a name is available)."
            )
    except Exception as e:
        lines.append(f"Field list failed: {e}")

    # Ranked investigation hint
    if "worse" in text_q.lower() or "ndvi" in text_q.lower() or "monitor" in text_q.lower():
        findings.append({
            "rank": 2,
            "text": "Compare recent NDVI / zone maps in Precision Ag for fields with declining health.",
            "field_id": state.get("active_field_id"),
        })
        lines.append("- Priority: review declining NDVI fields and scouting notes.")

    summary = "\n".join(lines)
    try:
        from monitoring_store import save_run

        save_run(
            business_id=business_id,
            people_id=people_id,
            thread_id=str(state.get("thread_id") or ""),
            summary=summary[:4000],
            findings=findings,
        )
    except Exception as e:
        logger.debug("[Monitoring] persist failed: %s", e)

    recs = []
    if findings and findings[0].get("field_id"):
        recs.append("Open Precision Ag for this field's full NDVI history")
    else:
        recs.append("Open Precision Ag for flagged fields")
    recs.append("Enable monitoring on critical fields")

    return {
        "source": "monitoring",
        "text": summary,
        "recommendations": recs,
        "findings": findings,
    }


def _run_plan_advisory(state: SaigeState, packets: Dict[str, Any]) -> Dict[str, Any]:
    """Build dated checklist from specialist packets + optional weather mitigation."""
    from datetime import date, timedelta

    today = date.today()
    items = []
    text_q = (_latest_user_text(state) or "").lower()
    weather_pkt = packets.get("weather_packet") or state.get("weather_packet") or {}
    crop_pkt = packets.get("crop_packet") or state.get("crop_packet") or {}
    livestock_pkt = packets.get("livestock_packet") or state.get("livestock_packet") or {}
    monitoring_pkt = packets.get("monitoring_packet") or state.get("monitoring_packet") or {}

    # Prefer concrete mitigation steps when the ask is a weather playbook
    mitigation_text = ""
    if any(k in text_q for k in ("mitigation", "playbook", "frost", "drought", "heat", "flood", "hail")):
        try:
            from weather_mitigation import format_for_llm, resolve_hazard
            hazard = resolve_hazard(text_q) or (
                "frost" if "frost" in text_q or "cold" in text_q else
                "drought" if "drought" in text_q else
                "heat" if "heat" in text_q else
                "flood" if "flood" in text_q else
                "hail" if "hail" in text_q else
                "frost"
            )
            phase = "imminent"
            if any(k in text_q for k in ("planning", "prepare", "before season", "spring")):
                phase = "planning"
            elif any(k in text_q for k in ("recovery", "after", "aftermath")):
                phase = "recovery"
            elif any(k in text_q for k in ("during", "active", "happening")):
                phase = "active"
            mitigation_text = format_for_llm(hazard, phase)
            for i, line in enumerate(mitigation_text.splitlines()):
                step = line.strip()
                if step[:1].isdigit() or step.startswith("•") or step.startswith("-"):
                    items.append({
                        "date": str(today + timedelta(days=min(i, 3))),
                        "task": step.lstrip("0123456789.-)• ").strip()[:200],
                        "domain": "weather",
                        "status": "open",
                    })
        except Exception as e:
            logger.debug("[Plan] mitigation inject failed: %s", e)

    if weather_pkt and not mitigation_text:
        items.append({"date": str(today), "task": "Check frost/heat risk and protect vulnerable crops/livestock", "domain": "weather", "status": "open"})
    if crop_pkt:
        items.append({"date": str(today + timedelta(days=1)), "task": "Scout problem fields and note symptoms", "domain": "crop", "status": "open"})
    if livestock_pkt:
        items.append({"date": str(today + timedelta(days=1)), "task": "Walk herd/flock health check; confirm water and bedding", "domain": "livestock", "status": "open"})
    if monitoring_pkt:
        items.append({"date": str(today + timedelta(days=2)), "task": "Review monitoring alerts / NDVI changes", "domain": "monitoring", "status": "open"})

    # Season-aware defaults when packets are thin
    if not items:
        month = today.month
        if month in (3, 4, 5) or "spring" in text_q:
            items = [
                {"date": str(today), "task": "Confirm soil temps and last-frost date before transplanting", "domain": "crop", "status": "open"},
                {"date": str(today + timedelta(days=1)), "task": "Service irrigation and check field moisture", "domain": "crop", "status": "open"},
                {"date": str(today + timedelta(days=2)), "task": "Walk livestock facilities; restock feed and bedding", "domain": "livestock", "status": "open"},
                {"date": str(today + timedelta(days=3)), "task": "Review Precision Ag alerts and mark fields needing scouting", "domain": "monitoring", "status": "open"},
                {"date": str(today + timedelta(days=4)), "task": "Update marketplace listings / inventory for spring demand", "domain": "business", "status": "open"},
            ]
        else:
            items = [
                {"date": str(today), "task": "Walk the farm and note top 3 priorities", "domain": "plan", "status": "open"},
                {"date": str(today + timedelta(days=2)), "task": "Check irrigation / water status", "domain": "crop", "status": "open"},
                {"date": str(today + timedelta(days=4)), "task": "Review marketplace / inventory listings", "domain": "business", "status": "open"},
            ]

    # Deduplicate empty tasks
    items = [i for i in items if (i.get("task") or "").strip()]
    header = "Weather mitigation + weekly plan:" if mitigation_text else "Weekly plan draft:"
    text = header + "\n" + "\n".join(f"- {i['date']}: {i['task']}" for i in items)
    if mitigation_text and "Mitigation plan" in mitigation_text:
        text = mitigation_text + "\n\n" + text
    return {
        "source": "plan",
        "text": text,
        "items": items,
        "recommendations": [i["task"] for i in items][:8],
        "propose_save": True,
    }


# ── Synthesizer ──────────────────────────────────────────────────────────────

def synthesizer_node(state: SaigeState) -> Dict[str, Any]:
    """Merge specialist packets into one farmer-facing answer + citations + plan proposals."""
    print("[Synthesizer] start")
    t0 = time.perf_counter()
    user_q = _latest_user_text(state)
    user_pkt = state.get("user_packet") or {}

    # Account/identity answers must not be overwritten by weather/crop packets
    if user_pkt.get("text") and _is_account_identity_query(user_q):
        diagnosis = str(user_pkt.get("text") or "").strip()
        history = list(state.get("history") or [])
        history.append(f"AI: {diagnosis}")
        synth_ms = (time.perf_counter() - t0) * 1000
        print(f"[Synthesizer] identity short-circuit chars={len(diagnosis)} synth_ms={synth_ms:.0f}")
        return {
            "diagnosis": diagnosis,
            "recommendations": list(user_pkt.get("recommendations") or []),
            "citations": [],
            "history": history,
            "proposals": list(state.get("proposals") or []),
            "assessment_summary": user_q,
            "synth_ms": synth_ms,
            "advisory_type": state.get("advisory_type") or "user",
        }

    packets = []
    citations = []
    for key in (
        "user_packet",
        "weather_packet",
        "crop_packet",
        "livestock_packet",
        "monitoring_packet",
        "plan_packet",
        "bakasura_packet",
        "news_packet",
    ):
        pkt = state.get(key)
        if pkt and pkt.get("text"):
            packets.append(pkt)
            # Prefer document-level RAG citations from specialists
            for c in (pkt.get("citations") or []):
                if isinstance(c, dict) and (c.get("doc_id") or c.get("chunk_id") or c.get("quote")):
                    citations.append(c)
            if not pkt.get("citations"):
                citations.append({"source": pkt.get("source") or key, "snippet": str(pkt.get("text"))[:180]})

    if state.get("joke_text") and not packets:
        return {
            "diagnosis": state["joke_text"],
            "recommendations": [],
            "citations": [],
            "assessment_summary": _latest_user_text(state),
            "synth_ms": (time.perf_counter() - t0) * 1000,
        }

    if not packets:
        diagnosis = (
            "I'm Saige. Tell me about your fields, animals, weather concerns, "
            "or ask for a weekly plan - I can also look up OFN docs, news, or tell a farm joke."
        )
        recs: List[str] = []
    elif len(packets) == 1:
        diagnosis = packets[0]["text"]
        recs = list(packets[0].get("recommendations") or [])
    else:
        blob = "\n\n".join(
            f"### {p.get('source', 'advisor').upper()}\n{p.get('text', '')}" for p in packets
        )
        try:
            llm = get_llm_farm()
            prompt = (
                "You are Saige, an agricultural advisor. Merge the specialist notes below into ONE "
                "coherent, practical answer for the farmer. Keep concrete actions. Cite domains inline "
                "(e.g. Weather:, Crop:). When farm facts come from knowledge base citations, keep claims "
                "grounded — if retrieval was empty, say so rather than inventing sources. "
                f"User asked: {_latest_user_text(state)!r}\n\n{blob}"
            )
            resp = llm.invoke(prompt)
            diagnosis = getattr(resp, "content", None) or str(resp)
        except Exception as e:
            logger.warning("[Synthesizer] merge LLM failed: %s", e)
            diagnosis = "\n\n".join(f"**{p.get('source')}:** {p.get('text')}" for p in packets)
        recs = []
        for p in packets:
            recs.extend(p.get("recommendations") or [])

    seen = set()
    uniq_recs = []
    for r in recs:
        if r and r not in seen:
            seen.add(r)
            uniq_recs.append(r)

    # Dedupe citations by chunk_id/doc_id
    uniq_cites = []
    seen_c = set()
    for c in citations:
        cid = str(c.get("chunk_id") or c.get("doc_id") or c.get("snippet") or "")
        if cid in seen_c:
            continue
        seen_c.add(cid)
        uniq_cites.append(c)

    history = list(state.get("history") or [])
    history.append(f"AI: {diagnosis}")

    proposals = list(state.get("proposals") or [])
    plan_pkt = state.get("plan_packet") or {}
    if plan_pkt.get("propose_save") and plan_pkt.get("items"):
        proposals.append(
            {
                "tool": "save_plan",
                "args": {
                    "business_id": state.get("business_id"),
                    "people_id": state.get("people_id"),
                    "title": f"Weekly plan {plan_pkt.get('items', [{}])[0].get('date', '')}",
                    "items": plan_pkt.get("items"),
                    "status": "approved",
                },
                "risk": "low_write",
                "domain": "plan",
                "summary": f"Save weekly plan ({len(plan_pkt.get('items') or [])} items)",
            }
        )

    synth_ms = (time.perf_counter() - t0) * 1000
    print(f"[Synthesizer] packets={len(packets)} chars={len(diagnosis)} proposals={len(proposals)} synth_ms={synth_ms:.0f}")
    # Progressive token stream for SSE clients
    try:
        _tid = str(state.get("thread_id") or "")
        _q = _get_stream_queue(_tid) if _tid else None
        if _q is not None and diagnosis:
            step = 48
            for i in range(0, len(diagnosis), step):
                _q.put({"type": "token", "content": diagnosis[i : i + step]})
    except Exception:
        pass
    handoff = (state.get("handoff") or "none").strip().lower()
    if handoff and handoff != "none":
        sibling_paths = {
            "cassia": "/cassia (onboarding)",
            "rosemarie": "/rosemarie (artisan / craft)",
            "pairsley": "/pairsley (chef pantry)",
            "chef": "/chef (restaurant kitchen)",
            "thaiyme": "Thaiyme (coming soon)",
            "tarrigon": "Tarrigon (coming soon)",
        }
        label = sibling_paths.get(handoff, handoff)
        diagnosis = (
            f"{diagnosis}\n\n"
            f"— I can also connect you with **{handoff.title()}** ({label}) for this request."
        )
        history = list(history)
        if history and history[-1].startswith("AI:"):
            history[-1] = f"AI: {diagnosis}"
    return {
        "diagnosis": diagnosis,
        "recommendations": uniq_recs[:12],
        "citations": uniq_cites[:20],
        "assessment_summary": _latest_user_text(state),
        "history": history[-40:],
        "confidence": "medium" if len(packets) > 1 else "high",
        "proposals": proposals,
        "handoff": handoff,
        "synth_ms": synth_ms,
        "specialist_ms": state.get("specialist_ms"),
    }


# ── Policy Gate ──────────────────────────────────────────────────────────────

def policy_gate_node(state: SaigeState) -> Dict[str, Any]:
    """Non-LLM hard checks (password, chemicals, organic prefs, risk class)."""
    print("[PolicyGate] start")
    from policy import filter_proposals

    proposals = list(state.get("proposals") or [])
    # Attach user preferences if present for organic_only checks
    prefs = state.get("preferences") or {}
    for p in proposals:
        if prefs:
            p["preferences"] = prefs
    kept, violations = filter_proposals(proposals)
    print(f"[PolicyGate] kept={len(kept)} blocked={len(violations)}")
    return {"proposals": kept, "policy_violations": violations}


# ── HITL Gate ────────────────────────────────────────────────────────────────

def hitl_gate_node(state: SaigeState) -> Dict[str, Any]:
    """Persist proposals and interrupt for human approve/edit/reject."""
    print("[HITL] interrupt")
    drafts = state.get("proposals") or []
    rows = create_proposals(
        people_id=str(state.get("people_id") or ""),
        business_id=state.get("business_id"),
        thread_id=str(state.get("thread_id") or ""),
        drafts=drafts,
    )
    for i, row in enumerate(rows):
        if i < len(drafts):
            drafts[i]["proposal_id"] = row["proposal_id"]
            drafts[i]["status"] = "pending"

    decision = interrupt(
        {
            "type": "hitl_proposals",
            "message": "Please approve, edit, or reject the proposed changes.",
            "proposals": rows,
            "diagnosis": state.get("diagnosis"),
        }
    )
    return {"hitl_decision": decision if isinstance(decision, dict) else {"raw": decision}, "proposals": drafts}


# ── Execute ──────────────────────────────────────────────────────────────────

def execute_node(state: SaigeState) -> Dict[str, Any]:
    """Run only approved tools via execute_registry."""
    print("[Execute] start")
    decision = state.get("hitl_decision") or {}
    proposals = list(state.get("proposals") or [])
    results = []

    decisions = decision.get("decisions")
    if not decisions:
        # Approve all pending if decision=approve without id
        if (decision.get("decision") or "").lower() in {"approve", "approved", "yes", "y"} and not decision.get("proposal_id"):
            decisions = [
                {"proposal_id": p.get("proposal_id"), "decision": "approve", "edits": {}}
                for p in proposals if p.get("proposal_id")
            ]
        else:
            decisions = [
                {
                    "proposal_id": decision.get("proposal_id") or (proposals[0].get("proposal_id") if proposals else None),
                    "decision": decision.get("decision", "reject"),
                    "edits": decision.get("edits") or {},
                }
            ]

    from proposals_store import decide_proposal
    from execute_registry import run_approved_tool

    for d in decisions:
        pid = d.get("proposal_id")
        dec = (d.get("decision") or "reject").lower()
        edits = d.get("edits") or {}
        if not pid:
            continue
        row = decide_proposal(pid, decision=dec, edits=edits, decided_by=str(state.get("people_id") or ""))
        if not row or row.get("status") not in {"approved", "executed"}:
            results.append(f"Proposal {pid}: {dec} (not executed)")
            continue
        ok, msg = run_approved_tool(row.get("tool") or "", row.get("args") or {})
        mark_executed(pid, ok=ok, result=msg)
        results.append(msg)

    extra = ""
    if results:
        extra = "\n\n**Action results:**\n" + "\n".join(f"- {r}" for r in results)
    diagnosis = (state.get("diagnosis") or "") + extra
    history = list(state.get("history") or [])
    if extra:
        history.append(f"AI: {extra.strip()}")
    return {"diagnosis": diagnosis, "history": history[-40:], "hitl_decision": {**decision, "results": results}}


def finalize_skip_hitl_node(state: SaigeState) -> Dict[str, Any]:
    """Passthrough when there are no proposals (read-only turn)."""
    return {
        "assessment_summary": state.get("assessment_summary") or _latest_user_text(state),
        "diagnosis": state.get("diagnosis") or "",
    }

