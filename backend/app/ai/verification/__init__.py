"""Groundedness verification.

Layer 1 (programmatic span resolution) lives in ``grounding.py`` and runs
inside the assessment graph. Whether a rationale is supported by its evidence
is a separate question, answered by human review (evaluation/support_review.py);
no model judge of rationales is implemented.
"""

from app.ai.verification.grounding import GroundingResult, verify_judgement

__all__ = ["GroundingResult", "verify_judgement"]
