"""Document-scoped candidate and decision identifiers.

Version 2 identifiers are the identifiers written by the FEO-014 population.
The enrichment engine is not modified. It still receives the legacy candidate
identifier, which keeps the engine's within-document processing order stable.
The population driver replaces candidate and decision identifiers with this
policy before materialisation and before any output is written.

Candidate inputs: corpus identifier, document identifier, candidate kind,
stable source identity, and mapping version.

Decision inputs: candidate identifier, rule identifier, target ontology term,
population profile, and decision-schema version.

Confidence, review status, timestamps, and processing order are not inputs.
"""

from __future__ import annotations

import hashlib

POLICY_ID = "feo014-identifier-policy-v2"
DECISION_SCHEMA_VERSION = "feo009-enrichment-decision-0.1.0"
MAPPING_VERSION = "feo009-enrichment-0.1.0"

_FEATURE_ID_FIELDS = (
    "event_candidate_id",
    "object_candidate_id",
    "time_candidate_id",
    "market_candidate_id",
    "value_candidate_id",
    "participant_candidate_id",
)


def _digest16(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def candidate_identifier(
    corpus: str,
    document_id: str,
    candidate_kind: str,
    stable_source_identity: str,
    mapping_version: str = MAPPING_VERSION,
) -> str:
    """Deterministic candidate identifier. The same inputs always yield the same value."""
    if not corpus or not document_id or not candidate_kind or not stable_source_identity or not mapping_version:
        raise ValueError("A candidate identifier is missing a required input.")
    material = "|".join(
        [
            str(corpus),
            str(document_id),
            str(candidate_kind),
            str(stable_source_identity),
            str(mapping_version),
        ]
    )
    return "cand-" + _digest16(material)


def decision_identifier(
    candidate_id: str,
    rule_id: str,
    target_term: str,
    profile: str,
    schema_version: str = DECISION_SCHEMA_VERSION,
) -> str:
    """Deterministic decision identifier. The target term may be empty when a rule has none."""
    if not candidate_id or not rule_id or not profile or not schema_version:
        raise ValueError("A decision identifier is missing a required input.")
    material = "|".join(
        [
            str(candidate_id),
            str(rule_id),
            str(target_term or ""),
            str(profile),
            str(schema_version),
        ]
    )
    return "dec-" + _digest16(material)


def target_term(decision: dict) -> str:
    """Ontology term used by the decision identifier. An IRI is preferred to a local name."""
    iri = str(decision.get("target_iri") or "").strip()
    if iri:
        return iri
    return str(decision.get("target_local_name") or "").strip()


def _rewrite_candidate(candidate: dict, mapping: dict[str, str]) -> dict:
    """Replace candidate identifiers without rewriting textual evidence."""
    updated = dict(candidate)
    updated["candidate_id"] = mapping[candidate["candidate_id"]]
    features = dict(candidate.get("features") or {})
    for field in _FEATURE_ID_FIELDS:
        value = features.get(field)
        if isinstance(value, str) and value in mapping:
            features[field] = mapping[value]
    market_ids = features.get("candidate_market_ids")
    if isinstance(market_ids, list):
        features["candidate_market_ids"] = [mapping.get(item, item) if isinstance(item, str) else item for item in market_ids]
    features["identifier_policy"] = POLICY_ID
    updated["features"] = features
    return updated


def identifier_mapping(candidates: list[dict], corpus: str, mapping_version: str = MAPPING_VERSION) -> dict[str, str]:
    """Map legacy candidate identifiers to version-2 identifiers."""
    mapping = {}
    for candidate in candidates:
        features = candidate.get("features") or {}
        stable = str(features.get("local_key") or "")
        if not stable:
            raise ValueError(
                "Candidate {0} has no stable source identity.".format(candidate.get("candidate_id"))
            )
        new_id = candidate_identifier(
            corpus,
            str(candidate.get("document_id") or ""),
            str(candidate.get("candidate_kind") or ""),
            stable,
            mapping_version,
        )
        old_id = candidate["candidate_id"]
        if old_id in mapping and mapping[old_id] != new_id:
            raise ValueError("Legacy candidate identifier {0} is not unique in this document.".format(old_id))
        mapping[old_id] = new_id
    if len(set(mapping.values())) != len(mapping):
        raise ValueError("Version-2 candidate identifiers collide inside one document.")
    return mapping


def apply_identifier_policy(
    candidate_lists: list[list[dict]],
    decisions: list[dict],
    corpus: str,
    mapping_version: str = MAPPING_VERSION,
) -> dict[str, str]:
    """Replace legacy identifiers on candidate lists and on the decision records.

    Each list is rewritten once. Decision objects that are shared with profile
    buckets are updated in place.
    """
    if not candidate_lists or not candidate_lists[0]:
        return {}
    mapping = identifier_mapping(candidate_lists[0], corpus, mapping_version)
    seen_lists = []
    unique_lists = []
    for candidates in candidate_lists:
        if any(candidates is existing for existing in seen_lists):
            continue
        seen_lists.append(candidates)
        unique_lists.append(candidates)
    for candidates in unique_lists:
        for index, candidate in enumerate(candidates):
            old_id = candidate["candidate_id"]
            if old_id not in mapping:
                raise ValueError("Candidate list is inconsistent with the identifier mapping.")
            candidates[index] = _rewrite_candidate(candidate, mapping)
    for decision in decisions:
        old_id = decision.get("candidate_id") or ""
        if old_id not in mapping:
            raise ValueError("Decision {0} names an unknown candidate.".format(decision.get("decision_id")))
        decision["candidate_id"] = mapping[old_id]
        for field in _FEATURE_ID_FIELDS:
            if field in decision and isinstance(decision[field], str):
                decision[field] = mapping.get(decision[field], decision[field])
        decision["decision_id"] = decision_identifier(
            decision["candidate_id"],
            str(decision.get("rule_id") or ""),
            target_term(decision),
            str(decision.get("profile") or ""),
            DECISION_SCHEMA_VERSION,
        )
        decision["identifier_policy"] = POLICY_ID
        explanation = decision.get("explanation")
        if isinstance(explanation, str) and explanation:
            for old_id in sorted(mapping, key=len, reverse=True):
                if old_id in explanation:
                    explanation = explanation.replace(old_id, mapping[old_id])
            decision["explanation"] = explanation
    decisions.sort(key=lambda item: (item.get("candidate_id") or "", item.get("rule_id") or "", item.get("decision_id") or ""))
    for candidates in candidate_lists:
        candidates.sort(key=lambda item: (item.get("candidate_kind") or "", item.get("candidate_id") or ""))
    return mapping
