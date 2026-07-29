# --- integrations/gemini.py --- (LLM provider abstraction - Gemini primary; Grok deferred)
"""
Saige LLM access.

Production + local default: Gemini 2.5 Flash Lite (via config.GEMINI_MODEL_NAME).
Provider selection: SAIGE_LLM_PROVIDER=gemini|grok (grok not enabled yet).

Public surface:
  - llm              shared Gemini client (siblings / tools / ReAct)
  - get_llm_farm()   farm-graph client (same Gemini today)
  - get_farm_llm_backend()
"""
from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv

load_dotenv()

# Load centralized model / provider config before initializing clients
import config as _saige_config  # noqa: F401
from config import GEMINI_MODEL_NAME, SAIGE_LLM_PROVIDER

from langchain_google_genai import ChatGoogleGenerativeAI


def _gemini_model_name() -> str:
    """Single source of truth: config.GEMINI_MODEL_NAME (env-overridable)."""
    return (GEMINI_MODEL_NAME or "gemini-2.5-flash-lite").strip()


def initialize_llm():
    """Initialize ChatGoogleGenerativeAI with Vertex AI or Developer API."""
    project = os.getenv("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
    use_vertexai = os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").lower() == "true"
    service_account_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    model = _gemini_model_name()

    if use_vertexai or project:
        llm_kwargs: dict = {"model": model, "temperature": 0}
        if project:
            llm_kwargs["project"] = project
        if location:
            llm_kwargs["location"] = location
        if service_account_path:
            try:
                from google.oauth2 import service_account

                credentials = service_account.Credentials.from_service_account_file(
                    service_account_path,
                    scopes=["https://www.googleapis.com/auth/cloud-platform"],
                )
                llm_kwargs["credentials"] = credentials
            except Exception as e:
                print(f"[LLM] Credentials error: {e}")
        if project:
            llm_kwargs["vertexai"] = True
        print(f"[LLM] Using Vertex AI ({model})")
        return ChatGoogleGenerativeAI(**llm_kwargs)

    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("No authentication found. Set GOOGLE_API_KEY or GOOGLE_CLOUD_PROJECT")

    print(f"[LLM] Using Developer API ({model})")
    return ChatGoogleGenerativeAI(model=model, temperature=0)


llm = initialize_llm()


# ============================================================================
# FARM GRAPH LLM (provider-selectable)
# ============================================================================

_farm_llm: Any = None
_farm_llm_backend: str = "uninitialized"


def get_farm_llm_backend() -> str:
    return _farm_llm_backend


def _provider_name() -> str:
    return (SAIGE_LLM_PROVIDER or os.getenv("SAIGE_LLM_PROVIDER", "gemini") or "gemini").strip().lower()


def _init_grok_deferred() -> Any:
    """Reserved for future xAI Grok. Raises until explicitly implemented."""
    raise RuntimeError(
        "SAIGE_LLM_PROVIDER=grok is not enabled yet. "
        "Keep SAIGE_LLM_PROVIDER=gemini (default). "
        "Set XAI_API_KEY later when Grok integration is turned on."
    )


def initialize_llm_farm():
    """Farm-graph LLM. Gemini is production primary; Grok is a future provider slot."""
    global _farm_llm, _farm_llm_backend

    if _farm_llm is not None:
        return _farm_llm

    provider = _provider_name()
    if provider == "grok":
        _farm_llm_backend = "grok:disabled"
        _init_grok_deferred()

    # gemini (default) and any unknown provider → configured Gemini model
    _farm_llm = llm
    model = _gemini_model_name()
    _farm_llm_backend = f"gemini:{model}"
    print(f"[LLM-farm] Using Gemini for farm graph ({model})")
    return _farm_llm


def get_llm_farm():
    return initialize_llm_farm()


try:
    llm_farm = initialize_llm_farm()
except Exception as _init_err:
    llm_farm = None
    _farm_llm_backend = f"error:{_init_err}"
    print(f"[LLM-farm] Deferred init - will retry on first use: {_init_err}")
