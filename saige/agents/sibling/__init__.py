# Sibling HTTP agents (Cassia, Pairsley, Rosemarie, Chef tools).
"""Independent HTTP-facing sibling agents.

These are NOT LangGraph nodes. Routes are registered on the main Saige API
(``api.app``) and import these modules via root shims.
"""
