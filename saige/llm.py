# --- llm.py --- (LLM initialization)
import os
from langchain_google_genai import ChatGoogleGenerativeAI


def initialize_llm():
    """Initialize ChatGoogleGenerativeAI with Vertex AI or Developer API."""
    project = os.getenv("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
    use_vertexai = os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").lower() == "true"
    service_account_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

    if use_vertexai or project:
        vertex_model = os.getenv("VERTEX_AI_MODEL", "gemini-2.5-flash-lite")
        llm_kwargs = {"model": vertex_model, "temperature": 0}
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
        print(f"[LLM] Using Vertex AI ({vertex_model})")
        return ChatGoogleGenerativeAI(**llm_kwargs)

    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("No authentication found. Set GOOGLE_API_KEY or GOOGLE_CLOUD_PROJECT")

    dev_model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    print(f"[LLM] Using Developer API ({dev_model})")
    return ChatGoogleGenerativeAI(model=dev_model, temperature=0)


llm = initialize_llm()
