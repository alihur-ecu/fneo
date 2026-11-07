"""Shared constants for the FEO-009 enrichment engine.

Public IRIs follow the identifier policy in the FEO-008 mapping package.
The mapping version here is the enrichment engine's own version, so
assertion digests are not reused from an earlier mapping run.
"""

from __future__ import annotations

FNEO_NS = "https://w3id.org/fneo/"
RESOURCE_BASE = "https://w3id.org/fneo/resource/"
RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
RDFS_LABEL = "http://www.w3.org/2000/01/rdf-schema#label"
XSD_NS = "http://www.w3.org/2001/XMLSchema#"

MAPPING_VERSION = "feo009-enrichment-0.1.0"
RULE_VERSION = "feo009-0.1.0"
ONTOLOGY_FILENAME = "fneo-0.1.0-rc2.ttl"
ONTOLOGY_SHA256 = "6e58c94ce6ffcd0f94d7e8257abb5a33f342b567f28438ebca1761fc122b78af"
DIGEST_LENGTH = 20

PROFILES = (
    "CORE_DETERMINISTIC",
    "EXTENSION_REVIEWED",
    "CANDIDATE_REVIEW",
    "EXPERIMENTAL_TEMPORAL",
)

STATUSES = (
    "accepted",
    "requires_review",
    "rejected",
    "out_of_scope",
    "insufficient_evidence",
    "suppressed",
)

CANDIDATE_KINDS = (
    "entity_candidate",
    "event_candidate",
    "participation_candidate",
    "temporal_candidate",
    "value_candidate",
    "evidence_candidate",
)

# RDF validation-status individuals. RC2 has no out-of-scope individual.
# out_of_scope and insufficient_evidence decisions are recorded in JSON
# and, when an assertion is emitted, use Rejected rather than a new term.
VALIDATION_INDIVIDUAL = {
    "accepted": "Accepted",
    "requires_review": "RequiresReview",
    "rejected": "Rejected",
    "suppressed": "Suppressed",
    "out_of_scope": "Rejected",
    "insufficient_evidence": "Rejected",
}

MANUAL_REVIEW_INDIVIDUAL = {
    "not_reviewed": "NotReviewed",
    "review_required": "ReviewRequired",
    "manually_accepted": "ManuallyAccepted",
    "manually_rejected": "ManuallyRejected",
}

TEMPORAL_TYPE_INDIVIDUAL = {
    "precedes": "Before",
    "follows": "After",
    "simultaneousWith": "Simultaneous",
    "occursDuring": "During",
    "includes": "IncludesRelation",
}

INFERENCE_INDIVIDUAL = {
    "explicit": "Explicit",
    "rule_inferred": "RuleInferred",
    "inverse_generated": "InverseGenerated",
    "closure_derived": "ClosureDerived",
    "model_inferred": "ModelInferred",
}

COMMITMENT_INDIVIDUAL = {
    "committed": "Committed",
    "proposed": "Proposed",
    "suppressed": "SuppressedCommitment",
    "not_accepted": "Proposed",
}

KIND_ORDER = (
    "evidence_candidate",
    "entity_candidate",
    "value_candidate",
    "event_candidate",
    "participation_candidate",
    "temporal_candidate",
)

GROUP_ORDER = (
    "unmapped",
    "evidence",
    "entity_type",
    "structural_entity",
    "value_type",
    "literal_value",
    "structural_time",
    "structural_event",
    "market_change",
    "market_direction",
    "structural_participation",
    "affected_market",
    "event_time",
    "temporal",
    "event_value",
    "fallback",
)
