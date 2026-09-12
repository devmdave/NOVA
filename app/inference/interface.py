"""
Legacy shim — kept for backwards compatibility with any code that imported
from app.inference.interface directly.

Prefer importing from app.inference (the package root) in new code.
"""
# Re-export from canonical locations
from app.inference.engine import InferenceEngine  # noqa: F401
from app.inference.models import GenerationResult, GenerationRequest  # noqa: F401
