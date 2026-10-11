"""Small builders for fake model verdicts."""

from __future__ import annotations

from foundit_ai.schemas import LLMEvidence, LLMVerdict


def ev(attribute, result, this_quote, candidate_quote, note="n") -> LLMEvidence:
    return LLMEvidence(attribute=attribute, result=result, this_quote=this_quote,
                       candidate_quote=candidate_quote, note=note)


def verdict(candidate_id, evidence, suggestion="likely_match",
            next_step="Describe your keychain to the finder.", missing=()) -> LLMVerdict:
    return LLMVerdict(candidate_id=candidate_id, evidence=evidence,
                      suggested_assessment=suggestion,
                      missing_information=list(missing), next_step=next_step)
