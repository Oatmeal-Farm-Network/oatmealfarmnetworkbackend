# --- nodes.py --- (All node functions, routing, and advisory engine)
import re
from typing import Dict, Any, List, Optional
from langgraph.types import interrupt

from config import RAG_AVAILABLE, WEATHER_AVAILABLE, MAX_QUESTIONS
from saige_models import FarmState, AssessmentDecision, QueryClassification, QueryTypeClassification, WeatherQueryParsed, FollowUpEntityExtraction
from llm import llm
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
    from business_ops import business_ops_tools
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
    )
    FARM_DATA_AVAILABLE = True
except Exception as _e:
    print(f"[nodes] farm_data unavailable: {_e}")
    farm_data_tools = []
    list_my_animals_tool = None
    list_my_listings_tool = None
    count_my_animals_tool = None
    FARM_DATA_AVAILABLE = False

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
        draft_event_tool,
        draft_blog_post_tool,
    )
    ACTIONS_AVAILABLE = True
except Exception as _e:
    print(f"[nodes] actions unavailable: {_e}")
    actions_tools = []
    draft_produce_listing_tool = None
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

VALID_ADVISORY_TYPES = {"weather", "livestock", "crops", "mixed", "news", "bakasura"}
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
# ASSESSMENT NODE
# ============================================================================

_DIRECTIVE_KEYWORDS = (
    "field", "ndvi", "evi", "savi", "yield", "forecast", "irrigat",
    "soil", "scouting", "pest", "weather", "rain", "gdd", "carbon",
    "benchmark", "alert", "harvest", "plant", "market", "listing",
    "recipe", "par", "breed", "livestock", "animal", "cattle",
    "inventory", "sample",
)
_DIRECTIVE_STARTERS = (
    "look at", "show me", "tell me", "give me", "check", "analyze", "analyse",
    "what is", "what's", "whats", "how is", "how's", "how are",
    "can you", "could you", "please", "pull up", "open",
)


def _looks_like_directive(text: str) -> bool:
    """Detect if a user's quiz response is actually a new request, not an answer."""
    t = (text or "").strip().lower()
    if not t:
        return False
    if "?" in t:
        return True
    if t.startswith(_DIRECTIVE_STARTERS):
        return True
    words = t.split()
    if len(words) >= 4 and any(k in t for k in _DIRECTIVE_KEYWORDS):
        return True
    return False


def _infer_directive_advisory_type(text: str) -> str:
    """Rough routing hint for directive responses — mixed is a safe default."""
    t = (text or "").lower()
    if any(k in t for k in ("weather", "rain", "forecast", "temperature", "climate")):
        return "weather"
    if any(k in t for k in ("cattle", "cow", "sheep", "goat", "pig", "chicken", "livestock", "breed")):
        return "livestock"
    if any(k in t for k in ("field", "ndvi", "evi", "savi", "yield", "irrigat", "soil", "scouting", "gdd", "harvest", "plant", "crop")):
        return "crops"
    return "mixed"


def assessment_node(state: FarmState):
    """User-driven assessment: starts with open question, then contextual follow-ups."""
    
    structured_llm = llm.with_structured_output(AssessmentDecision)

    history = state.get("history") or []
    location = state.get("location")
    farm_size = state.get("farm_size")
    crops = state.get("crops") or []
    current_issues = state.get("current_issues") or []

    if state.get("assessment_summary"):
        return {}

    questions_asked = [h for h in history if h.startswith("AI:")]
    question_count = len(questions_asked)
    is_first_interaction = question_count == 0 and not current_issues

    # Check if user provided a complete question in first message
    print(f"[Assessment] Checking for fast-track - is_first_interaction: {is_first_interaction}, history length: {len(history)}")
    if is_first_interaction and history:
        first_user_message = None
        for msg in history:
            if msg.startswith("User:"):
                first_user_message = msg.replace("User:", "").strip()
                break

        print(f"[Assessment] First user message: {first_user_message[:100] if first_user_message else 'None'}...")

        if first_user_message and len(first_user_message) > 5:
            msg_lower = first_user_message.lower()

            # Use LLM to intelligently classify the query and determine next steps
            print(f"[Assessment] Using LLM for smart query classification...")

            try:
                classifier = llm.with_structured_output(QueryTypeClassification)
                classification_prompt = f"""Analyze this query and classify it. Your job is to decide whether to answer directly or ask clarifying questions.

Query: "{first_user_message}"

CLASSIFICATION RULES:
1. Use query_type='general' for ANY non-farming question: greetings, identity/account questions,
   tech questions, general chat, or anything not about crops/livestock/weather/soil.
2. Default needs_clarification=False. Only set True if the query is completely unintelligible
   without more context (e.g., "help", "something is wrong", "what should I do").
3. Most farming questions can be answered directly — do NOT ask follow-ups just because
   location or farm size isn't mentioned.

Examples:
- "what is my user ID" → query_type: general, is_specific: true, needs_clarification: false
- "what is my people ID" → query_type: general, is_specific: true, needs_clarification: false
- "hello" → query_type: general, is_specific: true, needs_clarification: false
- "weather in California" → query_type: weather, is_specific: true, needs_clarification: false
- "best goat breeds for meat" → query_type: livestock, is_specific: true, needs_clarification: false
- "my tomato leaves are yellow" → query_type: crops, is_specific: true, needs_clarification: false
- "cattle breeds for my farm" → query_type: livestock, is_specific: true, needs_clarification: false
- "what should I plant" → query_type: crops, is_specific: false, needs_clarification: true
- "help with my farm" → query_type: mixed, is_specific: false, needs_clarification: true
- "animal recommendation for maize field" → query_type: mixed, is_specific: true, needs_clarification: false"""

                classification_result = classifier.invoke(classification_prompt)
                
                query_type = normalize_advisory_type(classification_result.query_type)
                is_specific = classification_result.is_specific
                needs_clarification = classification_result.needs_clarification
                detected_items = classification_result.items

                # Handle general (non-farming) queries — answer directly, no quiz
                if classification_result.query_type.lower() == "general":
                    print(f"[Assessment] General (non-farming) query - fast-tracking")
                    return {
                        "assessment_summary": f"General question: {first_user_message}",
                        "current_issues": [first_user_message],
                        "advisory_type": "mixed"
                    }

                print(f"[Assessment] Parsed: type={query_type}, specific={is_specific}, needs_clarification={needs_clarification}, items={detected_items}")

                # Decision logic based on LLM classification
                if query_type == "weather" and not needs_clarification:
                    print(f"[Assessment] Weather query - fast-tracking")
                    return {
                        "assessment_summary": f"Weather query: {first_user_message}",
                        "current_issues": [first_user_message],
                        "advisory_type": "weather"
                    }

                elif query_type and not needs_clarification:
                    print(f"[Assessment] Specific query detected - fast-tracking to {query_type}")
                    return {
                        "assessment_summary": f"Farmer seeks assistance with: {first_user_message}",
                        "current_issues": [first_user_message],
                        "crops": detected_items if detected_items else None,
                        "advisory_type": query_type
                    }

                else:
                    print(f"[Assessment] Query needs clarification - will ask questions")
                    current_issues = [first_user_message]
                    if detected_items:
                        crops = detected_items

            except Exception as e:
                print(f"[Assessment] LLM classification error: {e} - falling back to keyword matching")
                msg_lower = first_user_message.lower()

                weather_keywords = ["weather", "temperature", "forecast", "rain", "climate"]
                specific_crops = ["paddy", "rice", "wheat", "maize", "corn", "cotton", "soybean", "tomato", "potato"]
                specific_livestock = ["cattle", "cow", "buffalo", "sheep", "goat", "pig", "chicken", "duck", "turkey", "horse"]

                if any(kw in msg_lower for kw in weather_keywords):
                    return {
                        "assessment_summary": f"Weather query: {first_user_message}",
                        "current_issues": [first_user_message],
                        "advisory_type": "weather"
                    }

                has_specific_crop = any(crop in msg_lower for crop in specific_crops)
                has_specific_livestock = any(animal in msg_lower for animal in specific_livestock)

                if has_specific_crop or has_specific_livestock:
                    print(f"[Assessment] Specific crop/livestock detected (fallback) - fast-tracking")
                    current_issues = [first_user_message]

                    if has_specific_livestock and not has_specific_crop:
                        advisory_type = "livestock"
                    elif has_specific_crop and not has_specific_livestock:
                        advisory_type = "crops"
                    else:
                        advisory_type = "mixed"

                    return {
                        "assessment_summary": f"Farmer seeks assistance with: {first_user_message}",
                        "current_issues": current_issues,
                        "advisory_type": advisory_type
                    }
                else:
                    print(f"[Assessment] Generic question (fallback) - will ask questions")
                    current_issues = [first_user_message]

    print(f"[Assessment] Not fast-tracking - will ask questions")

    # Update current_issues in state if we captured it from first message
    if is_first_interaction and current_issues and not state.get("current_issues"):
        print(f"[Assessment] Storing user's initial concern: {current_issues}")

    # Determine completion
    should_complete = False
    has_issue = bool(current_issues)
    has_crops_or_livestock = bool(crops)
    has_location = bool(location)

    if question_count >= MAX_QUESTIONS:
        should_complete = True
    elif has_issue and has_crops_or_livestock and has_location and question_count >= 2:
        should_complete = True
    elif has_issue and has_crops_or_livestock and question_count >= 3:
        should_complete = True

    if should_complete:
        summary_parts = [f"Farmer seeks assistance with: {', '.join(current_issues) if current_issues else 'general farm advice'}"]
        if crops:
            summary_parts.append(f"Growing/Raising: {', '.join(crops)}")
        if location:
            summary_parts.append(f"Location: {location}")
        assessment_summary = " | ".join(summary_parts)
        print(f"[Assessment] Complete: {assessment_summary}")
        return {"assessment_summary": assessment_summary}

    # Build prompt
    user_has_concern = bool(current_issues)

    if is_first_interaction and not user_has_concern:
        prompt = """You are a friendly farm advisor. This is your first interaction.

Ask ONE open-ended question to understand what brings them here today.
Be warm and welcoming. Provide 3-4 option suggestions but allow free-text response.
Set is_complete=False."""
    elif is_first_interaction and user_has_concern:
        user_concern = ', '.join(current_issues)
        prompt = f"""You are a friendly farm advisor. The farmer just asked: "{user_concern}"

This is your FIRST follow-up question. Based on their concern, ask ONE specific clarifying question.

For example:
- If they mention "animal/breed for field" -> Ask what type of field/crop
- If they mention a crop -> Ask about their specific issue or goal
- If they mention livestock -> Ask about their farm setup or goal

Provide 3-4 specific, relevant options based on your question.
CRITICAL RULES:
1. Options must be direct answers to the exact question you asked.
   If you ask about goal/purpose, options must be goals (not animal breeds).
   If you ask about location, options must be locations.
   If you ask about crop/animal type, options must be crop/animal types.
2. NEVER ask the user to provide expert/specialist knowledge they came here to learn.
   - BAD: "Which breeds are best for weed control?" (the user is asking US this)
   - BAD: "What specific duck breeds are most effective?" (this is expert knowledge)
   - GOOD: "What is your primary goal?" or "How large is your field?"
   - GOOD: "Where is your farm located?" or "What is your budget?"
3. Only ask about the user's SITUATION: farm size, location, budget, existing setup, goals, problems.
   Do NOT quiz them on agricultural science — that is YOUR job to provide in the final advice.
Set is_complete=False.

DO NOT repeat what they said. Just ask your clarifying question."""
    else:
        history_text = "\n".join(history[-10:])
        prompt = f"""Farm Info: Location {'Y' if location else 'N'}, Crops/Livestock {'Y' if crops else 'N'}

History:
{history_text}

Ask ONE relevant follow-up question. Provide 3-4 specific options (not Yes/No).

CRITICAL RULES:
1. Options must directly answer your question and stay in the same intent category.
2. NEVER ask the user to provide expert/specialist knowledge they came here to learn.
   - BAD: "Which breeds are best for X?" or "What specific variety works best?"
   - GOOD: "How large is your farm?" or "What is your main concern?"
3. Only ask about the user's SITUATION: location, farm size, budget, goals, existing problems, timeline.
   You are the expert — do NOT ask the user to be the expert.

Questions asked: {question_count}/{MAX_QUESTIONS}

Set is_complete=True when you have:
- User's issue/concern
- What they're growing/raising
- Location (if needed)"""

    res = structured_llm.invoke(prompt)

    if not res.is_complete:
        answer_slot = _infer_answer_slot(res.question, has_existing_issue=bool(current_issues))
        options = list(res.options or [])
        if not _options_are_consistent(res.question, options, answer_slot):
            print("[Assessment] Replacing inconsistent options with contextual fallbacks")
            options = _build_fallback_options(res.question, answer_slot)

        ui_schema = {"type": "quiz", "question": res.question, "options": options}
        user_response = interrupt(ui_schema)

        # Escape hatch: if the user ignored the quiz and asked something new,
        # treat the response as a fresh directive and break out of assessment.
        if _looks_like_directive(user_response):
            advisory_type = _infer_directive_advisory_type(user_response)
            print(f"[Assessment] Directive detected on resume → routing to {advisory_type}")
            return {
                "history": history + [f"AI: {res.question}", f"User: {user_response}"],
                "current_issues": [user_response],
                "assessment_summary": f"Farmer asks: {user_response}",
                "advisory_type": advisory_type,
            }

        updates = {"history": history + [f"AI: {res.question}", f"User: {user_response}"]}

        # Preserve any issue already inferred from the first user message.
        if current_issues and not state.get("current_issues"):
            updates["current_issues"] = list(current_issues)

        if answer_slot == "location":
            updates["location"] = user_response
        elif answer_slot == "farm_size":
            updates["farm_size"] = user_response
        elif answer_slot == "crops":
            updated_crops = list(crops)
            if user_response not in updated_crops:
                updated_crops.append(user_response)
            updates["crops"] = updated_crops
        else:
            updated_issues = list(updates.get("current_issues", current_issues))
            if user_response not in updated_issues:
                updated_issues.append(user_response)
            updates["current_issues"] = updated_issues

        return updates

    return {"assessment_summary": res.assessment_summary or "Assessment complete"}


# ============================================================================
# ROUTING NODE
# ============================================================================

def routing_node(state: FarmState) -> Dict[str, str]:
    """Hybrid routing: fast-path check, keyword matching, then LLM fallback."""

    # FAST PATH: Did assessment_node already determine advisory_type?
    normalized_advisory_type = normalize_advisory_type(state.get("advisory_type"))
    if normalized_advisory_type:
        print(f"[Routing] Using pre-determined type: {normalized_advisory_type} (skipping analysis)")
        return {"advisory_type": normalized_advisory_type}

    crops = state.get("crops", [])
    issues = state.get("current_issues", [])
    assessment = state.get("assessment_summary", "")

    query_text = f"{' '.join(crops)} {' '.join(issues)} {assessment}".lower()

    weather_keywords = [
        "weather", "temperature", "rain", "forecast", "climate", "humidity",
        "wind", "sunny", "cloudy", "precipitation", "storm", "snow", "fog",
        "temp", "how hot", "how cold", "what's the weather"
    ]

    livestock_strong_keywords = [
        "cattle", "cow", "sheep", "goat", "pig", "chicken", "duck", "turkey",
        "horse", "rabbit", "livestock", "breed", "dairy", "beef",
        "poultry", "lamb", "calf", "piglet", "chick"
    ]
    livestock_weak_keywords = ["animal"]
    crop_strong_keywords = [
        "corn", "maize", "wheat", "rice", "barley", "soybean", "cotton",
        "tomato", "potato", "paddy"
    ]
    crop_weak_keywords = ["vegetable", "fruit", "grain", "crop", "plant", "field", "harvest"]

    weather_matches = _count_keyword_matches(query_text, weather_keywords)
    livestock_strong_matches = _count_keyword_matches(query_text, livestock_strong_keywords)
    livestock_weak_matches = _count_keyword_matches(query_text, livestock_weak_keywords)
    crop_strong_matches = _count_keyword_matches(query_text, crop_strong_keywords)
    crop_weak_matches = _count_keyword_matches(query_text, crop_weak_keywords)

    print(
        "[Routing] Keywords - "
        f"Weather: {weather_matches}, "
        f"Livestock(strong/weak): {livestock_strong_matches}/{livestock_weak_matches}, "
        f"Crops(strong/weak): {crop_strong_matches}/{crop_weak_matches}"
    )

    if weather_matches > 0 and livestock_strong_matches == 0 and crop_strong_matches == 0:
        print(f"[Routing] -> weather (pure weather query)")
        return {"advisory_type": "weather"}

    if livestock_strong_matches > 0 and crop_strong_matches == 0:
        print(f"[Routing] -> livestock (strong keyword)")
        return {"advisory_type": "livestock"}
    if crop_strong_matches > 0 and livestock_strong_matches == 0:
        print(f"[Routing] -> crops (strong keyword)")
        return {"advisory_type": "crops"}
    if livestock_strong_matches > 0 and crop_strong_matches > 0:
        print(f"[Routing] -> mixed (strong keywords)")
        return {"advisory_type": "mixed"}

    # Weak-only signals are ambiguous; avoid hard routing unless one side clearly dominates.
    if livestock_weak_matches > 0 and crop_weak_matches == 0:
        print(f"[Routing] -> livestock (weak keyword fallback)")
        return {"advisory_type": "livestock"}
    if crop_weak_matches > 0 and livestock_weak_matches == 0:
        print(f"[Routing] -> crops (weak keyword fallback)")
        return {"advisory_type": "crops"}

    # LLM fallback (only for ambiguous cases)
    print(f"[Routing] Using LLM fallback...")
    classifier = llm.with_structured_output(QueryClassification)
    prompt = f"""Classify as 'livestock', 'crops', 'mixed', or 'weather':
Crops/Animals: {', '.join(crops) if crops else 'Not specified'}
Issues: {', '.join(issues) if issues else 'None'}
Assessment: {assessment}"""

    try:
        result = classifier.invoke(prompt)
        print(f"[Routing] LLM: {result.category}")
        llm_type = normalize_advisory_type(result.category)
        if llm_type:
            return {"advisory_type": llm_type}
    except Exception as e:
        print(f"[Routing] LLM error: {e}")

    return {"advisory_type": "crops"}


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
    if _assessment.startswith("General question:"):
        print(f"[Advisory Agent] General question - answering directly")
        _history = state.get("history") or []
        _msg = ""
        for _h in reversed(_history):
            if _h.startswith("User:"):
                _msg = _h.replace("User:", "", 1).strip()
                break
        _pid = state.get("people_id")
        _ml = _msg.lower()
        if any(k in _ml for k in ["peopleid", "people_id", "people id", "user id", "userid", "my id"]):
            _answer = f"Your PeopleID is {_pid}." if _pid else "Your PeopleID is not available in this context."
        elif any(k in _ml for k in ["businessid", "business_id", "business id", "my business"]):
            _bid = state.get("business_id")
            _answer = f"Your BusinessID is {_bid}." if _bid else "No BusinessID is set in this session. Try opening Saige from your business page."
        else:
            try:
                _resp = llm.invoke(
                    "You are Saige, a farm assistant. The user is mid-conversation. "
                    "Answer the question directly and concisely. "
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

    latest_user_message = ""
    for msg in reversed(history):
        if msg.startswith("User:"):
            latest_user_message = msg.replace("User:", "", 1).strip()
            break
    if not latest_user_message:
        latest_user_message = ", ".join(issues) if issues else "General inquiry"

    recent_turns = "\n".join(history[-8:]) if history else "Not available"

    soil_lines = []
    if isinstance(soil_info, dict) and soil_info:
        for key in ["ph", "electrical_conductivity", "cec", "organic_matter", "nitrogen", "phosphorus", "potassium"]:
            if key in soil_info and soil_info[key] is not None:
                soil_lines.append(f"- {key}: {soil_info[key]}")
        if soil_info.get("raw_text"):
            soil_lines.append(f"- raw_report: {str(soil_info['raw_text'])[:600]}")
    soil_section = "Soil test data:\n" + "\n".join(soil_lines) if soil_lines else "Soil test data: Not provided"

    # 2. RAG Retrieval (Centralized)
    rag_context = ""
    if rag_systems and RAG_AVAILABLE:
        query_text = f"{', '.join(crops)} {', '.join(issues)} {assessment} {latest_user_message}"
        context_parts = []
        for rag_sys in rag_systems:
            try:
                rag_sys.initialize()
                ctx = rag_sys.get_context_for_query(query_text)
                if ctx:
                    context_parts.append(ctx)
                    print(f"[Advisory Agent] RAG context retrieved from {rag_sys._label}")
            except Exception as e:
                print(f"[Advisory Agent] RAG error ({rag_sys._label}): {e}")
        rag_context = "\n\n".join(context_parts)

    # 3. Construct Full Prompt
    rag_section = f"RELEVANT KNOWLEDGE BASE:\n{rag_context}" if rag_context else ""

    _people_id_ctx = state.get("people_id") or ""
    _business_id_ctx = state.get("business_id") or ""
    identity_section = (
        f"AUTHENTICATED IDENTITY (already known — do NOT ask the user for these):\n"
        f"- PeopleID: {_people_id_ctx or 'unknown'}\n"
        f"- BusinessID: {_business_id_ctx or 'unknown'}\n"
        "Every tool that needs people_id or business_id receives them automatically from "
        "this session. Call the tool directly — never ask the user to 'link their account' "
        "or provide these IDs. If a tool returns no data, say so plainly; do not blame "
        "missing authentication."
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
        parts.append(
            "Use these facts naturally — don't re-ask for location/crops you already know. "
            "If the current message references something previously discussed, carry it forward."
        )
        memory_section = "\n".join(parts)

    full_prompt = f"""{role_prompt}

{identity_section}

{memory_section}

Farmer's latest message: {latest_user_message}
Farmer's tracked issues: {', '.join(issues) if issues else 'General inquiry'}
Current Context:
- Crops/Livestock: {', '.join(crops) if crops else 'Not specified'}
- Location: {location}
{soil_section}

Recent conversation turns:
{recent_turns}

{rag_section}

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
PRECISION AG — Field Data (always start with list_my_fields_tool if field_id is unknown):
- list_my_fields_tool(): list satellite-monitored fields (field ID, name, crop, size, planting date). ALWAYS call this first when the user mentions "my fields", "my farm", or any field question without a specific ID.
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
- get_animal_detail_tool(animal_id): FULL animal profile — name, breed/category, sex, DOB, colors, sale/stud price, embryo/semen price, registration numbers, fiber stats (micron, CV, comfort factor), co-owners. Use when the user asks about a SPECIFIC animal by ID: "tell me about animal #42", "what's the stud fee for that alpaca", "show me the fiber data". Access-controlled to the user's business.

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

Prioritize the latest user message and any newly provided measurements over older generic context.
If soil-test values are present, reference them explicitly and avoid repeating unchanged advice.

Provide a concise, friendly response (3-4 sentences) with:
1. Direct answer to their question
2. 2-3 specific, actionable recommendations

Use simple, conversational language. NO markdown formatting, NO asterisks, NO headers.
Write like you're talking to a friend."""

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
    max_iterations = 3
    final_response = ""
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
            response = llm_with_tools.invoke(current_input)

            # Check for tool calls
            if hasattr(response, 'tool_calls') and response.tool_calls and iteration < max_iterations - 1:
                print(f"[Advisory Agent] Tool call detected: {len(response.tool_calls)}")
                for tool_call in response.tool_calls:
                    tc_name = tool_call.get('name')
                    tc_args = tool_call.get('args', {}) or {}
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
        "recommendations": recommendations[:5] if recommendations else ["Consider consulting a local expert"]
    }

    if weather_data:
        result["weather_conditions"] = weather_data

    return result


# ============================================================================
# ADVISORY NODES (Declarative - using unified engine)
# ============================================================================

def livestock_advisory_node(state: FarmState):
    """Livestock advisory with RAG (livestock_knowledge) and weather tool."""
    return run_advisory_agent(
        state,
        role_prompt="You are an expert livestock veterinarian and breed specialist. Provide practical advice on animal health, breed selection, and management.",
        rag_systems=[rag_livestock]
    )


def crop_advisory_node(state: FarmState):
    """Crop advisory with RAG (plant_knowledge) and weather tool."""
    return run_advisory_agent(
        state,
        role_prompt="You are an expert agronomist specializing in crop pathology, soil health, and sustainable farming practices.",
        rag_systems=[rag_plant]
    )


def bakasura_advisory_node(state: FarmState):
    """Bakasura docs advisory with RAG (bakasura-docs) and weather tool."""
    return run_advisory_agent(
        state,
        role_prompt="You are a knowledgeable farm advisor with access to the Bakasura knowledge base. Provide accurate, practical guidance based on available documentation.",
        rag_systems=[rag_bakasura]
    )


def news_advisory_node(state: FarmState):
    """News articles advisory with RAG (news_articles) and weather tool."""
    return run_advisory_agent(
        state,
        role_prompt="You are an agricultural news analyst. Provide insights and advice based on the latest farming news, market trends, and agricultural developments.",
        rag_systems=[rag_news]
    )


def mixed_advisory_node(state: FarmState):
    """Integrated advisory using all three RAG collections and weather tool."""
    return run_advisory_agent(
        state,
        role_prompt="You are an integrated farming systems expert specializing in permaculture, mixed farming, and sustainable agricultural practices.",
        rag_systems=[rag_livestock, rag_plant, rag_bakasura, rag_hitl_charlie, rag_news]
    )


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
# ROUTING FUNCTIONS
# ============================================================================

def route_after_assessment(state: FarmState) -> str:
    """Route from assessment to routing node when complete."""
    summary = state.get("assessment_summary")

    print(f"\n[Route] route_after_assessment called:")
    print(f"  - assessment_summary exists: {bool(summary and summary.strip())}")

    if summary and summary.strip():
        print(f"  -> routing_node (assessment complete)")
        return "routing_node"
    
    print(f"  -> assessment_node (continue assessment)")
    return "assessment_node"


def route_to_advisory(state: FarmState) -> str:
    """Route to appropriate advisory node."""
    advisory_type = normalize_advisory_type(state.get("advisory_type")) or "crops"
    if advisory_type == "weather":
        return "weather_advisory_node"
    elif advisory_type == "livestock":
        return "livestock_advisory_node"
    elif advisory_type == "mixed":
        return "mixed_advisory_node"
    elif advisory_type == "bakasura":
        return "bakasura_advisory_node"
    elif advisory_type == "news":
        return "news_advisory_node"
    return "crop_advisory_node"