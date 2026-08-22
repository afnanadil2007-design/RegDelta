"""Groundedness verification.

Layer 1 (programmatic span resolution) lives in ``grounding.py`` and runs
inside the assessment graph. Layer 2 (an LLM judge over rationales) is a
separate evaluation suite.
"""

from app.ai.verification.grounding import GroundingResult, verify_judgement

__all__ = ["GroundingResult", "verify_judgement"]
