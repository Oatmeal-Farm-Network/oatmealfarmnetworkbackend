# Deprecated shim — prefer schemas.models (or saige_models compat path).
from schemas.models import (  # noqa: F401
    FarmState,
    SaigeState,
    AssessmentDecision,
    QueryClassification,
    WeatherQueryParsed,
    QueryTypeClassification,
    FollowUpEntityExtraction,
    SupervisorRouteDecision,
    AccountIntent,
)
