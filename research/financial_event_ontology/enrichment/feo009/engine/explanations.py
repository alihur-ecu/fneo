"""Readable decision explanations. Numeric scores are never the only record."""

from __future__ import annotations


def _join(items: list[str]) -> str:
    if not items:
        return "none"
    return ", ".join(items)


def explain_decision(decision: dict) -> str:
    """Build one paragraph covering rule, evidence, negatives, score, and status."""
    score_terms = decision.get("confidence_terms") or []
    arithmetic = "0.00"
    if score_terms:
        rendered = []
        for term in score_terms:
            sign = term.get("sign") or "+"
            rendered.append(f"{sign}{term.get('weight')} ({term.get('condition')})")
        arithmetic = " ".join(rendered)
    blocking = decision.get("blocking_conditions_fired") or []
    failed = decision.get("failed_conditions") or []
    missing = decision.get("missing_conditions") or []
    satisfied = decision.get("satisfied_conditions") or []
    negatives = decision.get("negative_conditions_checked") or []
    negatives_fired = decision.get("negative_conditions_fired") or []
    review_reason = decision.get("manual_review_reason") or "none"
    policy = decision.get("materialisation_policy") or ""
    direct = "eligible" if decision.get("direct_triple_eligible") else "not eligible"
    lines = [
        f"Rule {decision.get('rule_id')} version {decision.get('rule_version')} was applied",
        f"to candidate {decision.get('candidate_id')}",
        f"for target {decision.get('target_label') or decision.get('target_iri') or 'unspecified'}.",
        f"Population profile: {decision.get('profile')}.",
        f"Evidence satisfied: {_join(decision.get('evidence_satisfied') or [])}.",
        f"Satisfied conditions: {_join(satisfied)}.",
        f"Negative conditions checked: {_join(negatives)}.",
        f"Negative conditions that fired: {_join(negatives_fired)}.",
        f"Failed conditions: {_join(failed)}.",
        f"Missing conditions: {_join(missing)}.",
        f"Blocking conditions that fired: {_join(blocking)}.",
        (
            "Rule confidence score "
            f"{decision.get('confidence')} is the deterministic sum {arithmetic}, "
            f"bounded to the unit interval. It is not a calibrated probability. "
            f"Acceptance threshold {decision.get('acceptance_threshold')}; "
            f"review threshold {decision.get('review_threshold')}."
        ),
        (
            "Blocking conditions override the score: a fired blocking condition "
            "prevents status accepted."
            if blocking
            else "No blocking condition fired, so the score was allowed to contribute to the status."
        ),
        f"Final status: {decision.get('status')}.",
        f"Materialisation policy {policy}; direct-triple eligibility is {direct}.",
        f"Qualified assertion required: {bool(decision.get('qualified_assertion_required'))}.",
        f"Manual-review reason: {review_reason}.",
        f"Source roles preserved: {_join(decision.get('source_roles_preserved') or [])}.",
    ]
    if decision.get("candidate_set"):
        lines.append(f"Market-change candidate set: {decision.get('candidate_set')}.")
    if decision.get("warnings"):
        lines.append("Warnings: " + _join(list(decision.get("warnings") or [])))
    return " ".join(lines)
