# --- nodes.py --- (All node functions, routing, and advisory engine)
import re
from typing import Dict, Any, List, Optional
from langgraph.types import interrupt

from config import RAG_AVAILABLE, WEATHER_AVAILABLE, MAX_QUESTIONS
from models import FarmState, AssessmentDecision, QueryClassification, QueryTypeClassification, WeatherQueryParsed, FollowUpEntityExtraction
from llm import llm
from rag import rag
from weather import weather_service, get_weather_tool, weather_tools

VALID_ADVISORY_TYPES = {"weather", "livestock", "crops", "mixed"}
ADVISORY_TYPE_ALIASES = {
    "crop": "crops",
    "crops": "crops",
    "livestock": "livestock",
    "animal": "livestock",
    "animals": "livestock",
    "weather": "weather",
    "mixed": "mixed",
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
                classification_prompt = f"""Analyze this farmer's query and classify it:

Query: "{first_user_message}"

Classify the query type, whether it's specific, if it needs clarification, and extract any mentioned items.

Examples:
- "weather in California" → query_type: weather, is_specific: false, needs_clarification: false, items: []
- "cattle breeds for my farm" → query_type: livestock, is_specific: true, needs_clarification: true, items: ["cattle"]
- "animal recommendation for maize field" → query_type: mixed, is_specific: false, needs_clarification: true, items: ["maize"]
- "my tomato plants have yellow leaves" → query_type: crops, is_specific: true, needs_clarification: false, items: ["tomato"]"""

                classification_result = classifier.invoke(classification_prompt)
                
                query_type = normalize_advisory_type(classification_result.query_type)
                is_specific = classification_result.is_specific
                needs_clarification = classification_result.needs_clarification
                detected_items = classification_result.items

                print(f"[Assessment] Parsed: type={query_type}, specific={is_specific}, needs_clarification={needs_clarification}, items={detected_items}")

                # Decision logic based on LLM classification
                if query_type == "weather" and not needs_clarification:
                    print(f"[Assessment] Weather query - fast-tracking")
                    return {
                        "assessment_summary": f"Weather query: {first_user_message}",
                        "current_issues": [first_user_message],
                        "advisory_type": "weather"
                    }

                elif query_type and is_specific and not needs_clarification:
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

def run_advisory_agent(state: FarmState, role_prompt: str, use_rag: bool = False) -> Dict[str, Any]:
    """
    Unified engine for all advisory nodes (Crop, Livestock, Mixed).
    Handles context gathering, RAG retrieval, and the Tool-Calling Loop.
    """
    print(f"\n[Advisory Agent] Processing with role: {role_prompt[:50]}...")

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
    if use_rag and RAG_AVAILABLE:
        query_text = f"{', '.join(crops)} {', '.join(issues)} {assessment} {latest_user_message}"
        try:
            rag.initialize()
            rag_context = rag.get_context_for_query(query_text)
            if rag_context:
                print(f"[Advisory Agent] RAG context retrieved")
        except Exception as e:
            print(f"[Advisory Agent] RAG error: {e}")

    # 3. Construct Full Prompt
    rag_section = f"RELEVANT KNOWLEDGE BASE:\n{rag_context}" if rag_context else ""

    full_prompt = f"""{role_prompt}

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

Prioritize the latest user message and any newly provided measurements over older generic context.
If soil-test values are present, reference them explicitly and avoid repeating unchanged advice.

Provide a concise, friendly response (3-4 sentences) with:
1. Direct answer to their question
2. 2-3 specific, actionable recommendations

Use simple, conversational language. NO markdown formatting, NO asterisks, NO headers.
Write like you're talking to a friend."""

    # 4. Bind Tools
    llm_with_tools = llm.bind_tools(weather_tools) if WEATHER_AVAILABLE else llm

    # 5. Tool Execution Loop (ReAct Pattern)
    weather_data = None
    weather_context = ""
    max_iterations = 3
    final_response = ""

    try:
        for iteration in range(max_iterations):
            current_input = full_prompt + (f"\n\n[Weather Update]: {weather_context}" if weather_context else "")
            response = llm_with_tools.invoke(current_input)

            # Check for tool calls
            if hasattr(response, 'tool_calls') and response.tool_calls and iteration < max_iterations - 1:
                print(f"[Advisory Agent] Tool call detected: {len(response.tool_calls)}")
                for tool_call in response.tool_calls:
                    if tool_call.get('name') == 'get_weather_tool':
                        loc = tool_call.get('args', {}).get('location', location)
                        print(f"[Advisory Agent] Executing Weather Tool for: {loc}")

                        tool_result = get_weather_tool.invoke({"location": loc})
                        weather_context = f"Weather Information:\n{tool_result}"

                        try:
                            weather_data = weather_service.get_weather(loc)
                        except:
                            pass
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
    """Livestock advisory with RAG and weather tool integration."""
    return run_advisory_agent(
        state,
        role_prompt="You are an expert livestock veterinarian and breed specialist. Provide practical advice on animal health, breed selection, and management.",
        use_rag=True
    )


def crop_advisory_node(state: FarmState):
    """Crop advisory with weather tool integration."""
    return run_advisory_agent(
        state,
        role_prompt="You are an expert agronomist specializing in crop pathology, soil health, and sustainable farming practices.",
        use_rag=False
    )


def mixed_advisory_node(state: FarmState):
    """Integrated crop+livestock advisory with RAG and weather tool."""
    return run_advisory_agent(
        state,
        role_prompt="You are an integrated farming systems expert specializing in permaculture, mixed farming, and sustainable agricultural practices.",
        use_rag=True
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
    return "crop_advisory_node"
