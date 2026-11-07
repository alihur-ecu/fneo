"""Read FEO-008 source fixtures without modifying them.

Observations become normalised candidate records. Source identifiers stay
in annotation fields and are not used as public IRIs.
"""

from __future__ import annotations

import json
from pathlib import Path

from engine.paths import feo008_examples

STATUS_MAP = {
    "accepted": "accepted",
    "requires_review": "requires_review",
    "rejected": "rejected",
    "suppressed": "suppressed",
    "unmapped": "out_of_scope",
    "invalid_shape": "rejected",
}


def load_feo008_fixtures(directory: Path | None = None) -> list[dict]:
    folder = directory or feo008_examples()
    envelopes = []
    for path in sorted(folder.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        envelopes.append(adapt_fixture(payload))
    return envelopes


def adapt_fixture(payload: dict) -> dict:
    corpus = payload.get("corpus") or "synthetic-feo008"
    profile = payload.get("profile") or "CORE_DETERMINISTIC"
    documents = []
    candidates = []
    primary_id = ""
    for observation in payload.get("observations") or []:
        if observation.get("kind") == "document":
            documents.append(
                {
                    "document_id": observation.get("source_document_id") or "DOC",
                    "label": observation.get("label") or "Document",
                    "publication_lexical": observation.get("publication_lexical") or "",
                    "publication_normalised": observation.get("publication_normalised") or "",
                    "time_key": observation.get("publication_time_key") or "publication",
                }
            )
            continue
        adapted = _adapt_observation(observation, corpus, profile, payload["fixture_id"])
        candidates.extend(adapted)
        if observation.get("primary") and adapted:
            rule_id = str(observation.get("rule_id") or "")
            if observation.get("kind") == "market_change" and rule_id.startswith("FE-AFF"):
                primary_id = adapted[-1]["candidate_id"]
            else:
                primary_id = adapted[0]["candidate_id"]
    if not documents:
        document_ids = sorted({item.get("document_id") for item in candidates if item.get("document_id")})
        for document_id in document_ids:
            documents.append(
                {
                    "document_id": document_id,
                    "label": "Document",
                    "publication_lexical": "",
                    "publication_normalised": "",
                    "time_key": "publication",
                }
            )
    expected_status = STATUS_MAP.get(payload.get("expected_status") or "", "insufficient_evidence")
    if not candidates:
        expected_status = "structural_only"
    source_rules = list(payload.get("rule_ids") or [])
    return {
        "fixture_id": "feo008-" + payload["fixture_id"],
        "source_fixture_id": payload["fixture_id"],
        "origin": "feo008-source",
        "corpus": corpus,
        "documents": documents,
        "candidates": candidates,
        "expected": {
            "primary_candidate_id": primary_id,
            "status": expected_status,
            "rule_id": _expected_rule(payload),
            "source_rule_ids": source_rules,
            "shacl": "pass",
            "forbid_literals": ["0.0525"] if payload.get("fixture_id") == "fx-21-invalid-percentage" else [],
            "forbid_predicates": _forbid_predicates(payload),
            "forbid_types": (
                ["MarketChangeEvent"]
                if payload.get("fixture_id") in {
                    "fx-11-sensitivity-review",
                    "fx-13-affected-market-review",
                    "fx-19-rejected-candidate",
                }
                else []
            ),
        },
    }


def _expected_rule(payload: dict) -> str:
    mapping = {
        "fx-02-entity-mention": "STR-ENT-001",
        "fx-03-event-mention": "STR-EVT-001",
        "fx-04-time-mention": "STR-TIME-001",
        "fx-05-percentage": "VAL-PERCENT-001",
        "fx-06-market-index": "FE-MKTIDX-001",
        "fx-07-equity-market": "FE-EQMKT-001",
        "fx-08-central-bank": "FE-CB-001",
        "fx-09-system-sector-review": "FE-SYSSEC-001",
        "fx-10-market-change-accepted": "FE-MCE-001",
        "fx-11-sensitivity-review": "FE-MCE-002",
        "fx-12-affected-market-accepted": "FE-AFF-001",
        "fx-13-affected-market-review": "FE-AFF-002",
        "fx-14-event-time": "TMP-ANCHOR-001",
        "fx-15-temporal-accepted": "TMP-BEFORE-001",
        "fx-16-temporal-suppressed": "TMP-INV-001",
        "fx-17-qualified-accepted": "QA-PART-001",
        "fx-18-literal-assertion": "VAL-PERCENT-001",
        "fx-19-rejected-candidate": "FE-MCE-003",
        "fx-20-unmapped-metadata": "NM-SCOPE-001",
        "fx-21-invalid-percentage": "VAL-PERCENT-001",
        "fx-22-temporal-proposed": "TMP-PRO-001",
        "fx-23-value-copresence": "VAL-CAND-001",
        "fx-24-arg-label-only": "FE-AFF-003",
        "fx-25-currency-amount": "FE-CCY-001",
    }
    return mapping.get(payload.get("fixture_id") or "", "")


def _forbid_predicates(payload: dict) -> list[str]:
    fixture_id = payload.get("fixture_id") or ""
    if fixture_id in {"fx-16-temporal-suppressed", "fx-22-temporal-proposed"}:
        return ["precedes", "follows", "simultaneousWith", "occursDuring", "includes"]
    if fixture_id == "fx-23-value-copresence":
        return ["hasReportedValue", "hasPercentageChange", "hasMonetaryAmount"]
    if fixture_id in {"fx-24-arg-label-only", "fx-19-rejected-candidate", "fx-13-affected-market-review", "fx-11-sensitivity-review"}:
        return ["hasAffectedMarket"]
    return []


def _base(observation: dict, corpus: str, profile: str, candidate_id: str, kind: str) -> dict:
    features = {
        "local_key": observation.get("key") or observation.get("entity_key") or observation.get("event_key") or candidate_id,
        "label": observation.get("label") or observation.get("textual_form") or observation.get("lexical") or "",
    }
    return {
        "candidate_id": candidate_id,
        "candidate_kind": kind,
        "document_id": observation.get("source_document_id") or "SYN-DOC-001",
        "sentence_id": observation.get("sentence_id"),
        "passage_id": None,
        "source_mention_ids": [observation.get("key")] if observation.get("key") else [],
        "source_annotation_ids": [observation["source_annotation_id"]] if observation.get("source_annotation_id") else [],
        "textual_evidence": observation.get("evidence_text") or observation.get("textual_form") or observation.get("lexical") or "",
        "token_start": observation.get("token_start"),
        "token_end": observation.get("token_end"),
        "character_start": observation.get("character_start"),
        "character_end": observation.get("character_end"),
        "generic_type": observation.get("source_class_code") or "",
        "trigger_or_lexical_form": observation.get("textual_form") or observation.get("lexical") or observation.get("label") or "",
        "lemma": observation.get("lemma"),
        "participants": [],
        "source_roles": [observation["source_role"]] if observation.get("source_role") else [],
        "participant_generic_types": [],
        "explicit_times": [],
        "values": [],
        "source_temporal_relation": {},
        "document_publication_time": None,
        "source_confidence": observation.get("confidence"),
        "provenance": {"origin": "feo008-source", "source_rule_id": observation.get("rule_id") or ""},
        "requested_population_profile": profile,
        "corpus": corpus,
        "features": features,
    }


def _flags_from_entity(features: dict, observation: dict) -> None:
    if observation.get("requested_type"):
        features["requested_target"] = observation["requested_type"]
    if observation.get("reviewer_accepted"):
        features["reviewer_decision"] = "accepted"
        features["reviewer_accepted"] = True
    if observation.get("contextual_evidence") is not None:
        features["contextual_evidence"] = observation["contextual_evidence"]
    if observation.get("controlled_name"):
        features["controlled_name_attested"] = True
    if observation.get("market_aggregate_reading"):
        features["market_aggregate_reading"] = True
    features["local_key"] = observation.get("entity_key") or observation.get("key") or features["local_key"]
    features["mention_key"] = observation.get("key")


def _adapt_observation(observation: dict, corpus: str, profile: str, fixture_id: str) -> list[dict]:
    kind = observation.get("kind")
    if kind == "entity_mention":
        candidate = _base(
            observation,
            corpus,
            profile,
            "ent-" + str(observation.get("entity_key") or observation.get("key")),
            "entity_candidate",
        )
        _flags_from_entity(candidate["features"], observation)
        return [candidate]
    if kind == "ambiguous_institution":
        candidate = _base(
            observation,
            corpus,
            profile,
            "ent-" + str(observation.get("entity_key") or observation.get("key")),
            "entity_candidate",
        )
        candidate["features"]["competing_targets"] = list(observation.get("competing_types") or [])
        candidate["features"]["requested_target"] = (observation.get("competing_types") or ["FinancialSystem"])[0]
        candidate["features"]["local_key"] = observation.get("entity_key") or observation.get("key")
        candidate["features"]["mention_key"] = observation.get("key")
        return [candidate]
    if kind == "event_mention":
        candidate = _base(observation, corpus, profile, "evt-" + str(observation.get("key")), "event_candidate")
        candidate["features"]["local_key"] = observation.get("event_key") or observation.get("key")
        candidate["features"]["mention_key"] = observation.get("key")
        if observation.get("source_class_code"):
            candidate["generic_type"] = observation["source_class_code"]
        return [candidate]
    if kind == "market_change":
        return _market_change(observation, corpus, profile)
    if kind == "time_mention":
        candidate = _base(observation, corpus, profile, "time-" + str(observation.get("key")), "temporal_candidate")
        candidate["features"]["time_mention"] = True
        candidate["features"]["local_key"] = observation.get("time_key") or observation.get("key")
        candidate["features"]["mention_key"] = observation.get("key")
        candidate["features"]["normalised"] = observation.get("normalised") or ""
        return [candidate]
    if kind == "event_time":
        return [_event_time(observation, corpus, profile)]
    if kind == "temporal_relation":
        return [_temporal(observation, corpus, profile, fixture_id)]
    if kind == "percentage_value":
        return [_percentage(observation, corpus, profile)]
    if kind == "monetary_amount":
        return [_money(observation, corpus, profile)]
    if kind == "value_copresence":
        return [_copresence(observation, corpus, profile)]
    if kind == "affected_market":
        return [_affected(observation, corpus, profile)]
    if kind == "qualified_relation":
        return [_qualified(observation, corpus, profile)]
    if kind == "literal_assertion":
        return [_literal(observation, corpus, profile)]
    if kind == "unmapped_record":
        candidate = _base(observation, corpus, profile, "unmapped-" + fixture_id, "evidence_candidate")
        candidate["document_id"] = observation.get("source_document_id") or "SYN-DOC-001"
        candidate["textual_evidence"] = observation.get("reason") or "unmapped"
        candidate["trigger_or_lexical_form"] = observation.get("structure") or "unmapped"
        candidate["features"]["unmapped"] = True
        candidate["features"]["local_key"] = "unmapped"
        return [candidate]
    return []


def _market_change(observation: dict, corpus: str, profile: str) -> list[dict]:
    event = _base(observation, corpus, profile, "evt-" + str(observation.get("event_key")), "event_candidate")
    event["features"].update(
        {
            "local_key": observation.get("event_key"),
            "mention_key": observation.get("mention_key"),
            "evidence_key": observation.get("evidence_key") or observation.get("event_key"),
            "market_change_candidate": True,
            "market_candidate_id": "ent-" + str(observation.get("market_key")) if observation.get("market_key") else "",
            "market_local_key": observation.get("market_key") or "",
            "market_surface": observation.get("label") or "",
            "change_expression": observation.get("change_expression"),
            "contextual_attachment": observation.get("contextual_attachment"),
            "trigger_only": observation.get("trigger_only"),
            "other_code_only": observation.get("other_code_only"),
            "sensitivity_set": observation.get("sensitivity_set"),
            "dated_descriptor": observation.get("dated_descriptor_outside_primary"),
            "dated_descriptor_outside_primary": observation.get("dated_descriptor_outside_primary"),
            "ambiguous_attachment": observation.get("ambiguous_attachment"),
            "frame_disagreement": observation.get("frame_disagreement"),
            "direction": observation.get("direction") or "",
        }
    )
    if observation.get("source_role"):
        event["features"]["source_role"] = observation["source_role"]
    part = _base(observation, corpus, profile, "part-" + str(observation.get("event_key")), "participation_candidate")
    part["features"].update(
        {
            "local_key": "part-" + str(observation.get("event_key")),
            "affected_market": True,
            "predicate": "hasAffectedMarket",
            "event_candidate_id": event["candidate_id"],
            "market_candidate_id": event["features"]["market_candidate_id"],
            "event_local_key": observation.get("event_key"),
            "market_local_key": observation.get("market_key"),
            "contextual_attachment": observation.get("contextual_attachment"),
            "ambiguous_attachment": observation.get("ambiguous_attachment"),
            "frame_disagreement": observation.get("frame_disagreement"),
            "evidence_key": observation.get("evidence_key") or observation.get("event_key"),
            "evidence_layers": ["EVENT_PARTICIPANT"] if observation.get("contextual_attachment") else [],
            "source_role": observation.get("source_role") or "",
        }
    )
    if observation.get("source_role"):
        part["source_roles"] = [observation["source_role"]]
    return [event, part]


def _event_time(observation: dict, corpus: str, profile: str) -> dict:
    candidate = _base(observation, corpus, profile, "rel-event-time", "temporal_candidate")
    candidate["textual_evidence"] = "explicit event time"
    candidate["trigger_or_lexical_form"] = "event time"
    candidate["source_temporal_relation"] = {
        "canonical_property": "hasEventTime",
        "original_relation": observation.get("original_label") or "HAS_TIME_ANCHOR",
        "subject_endpoint_type": "Event",
        "object_endpoint_type": "TimeEntity",
        "commitment_status": "committed" if observation.get("committed") else "proposed",
        "suppression_status": "suppressed" if observation.get("suppressed") else "not_suppressed",
        "inference_status": observation.get("inference") or "explicit",
        "active": observation.get("active", True),
        "committed": observation.get("committed", True),
        "suppressed": observation.get("suppressed", False),
        "proposed": observation.get("proposed", False),
        "source_kind": "explicit",
        "traceable": observation.get("traceable", True),
    }
    candidate["features"].update(
        {
            "event_time": True,
            "traceable": observation.get("traceable", True),
            "endpoint_types_valid": observation.get("endpoint_types_valid", True),
            "subject_local_key": observation.get("event_key"),
            "event_local_key": observation.get("event_key"),
            "time_local_key": observation.get("time_key"),
            "time_candidate_id": "time-" + str(observation.get("time_key")),
            "local_key": "rel-event-time",
            "time_normalised": "2026-03-03",
        }
    )
    return candidate


def _temporal(observation: dict, corpus: str, profile: str, fixture_id: str) -> dict:
    candidate = _base(observation, corpus, profile, "rel-" + fixture_id, "temporal_candidate")
    candidate["textual_evidence"] = observation.get("suppression_reason") or "temporal relation"
    candidate["trigger_or_lexical_form"] = observation.get("canonical_property") or "temporal"
    inference = observation.get("inference") or "explicit"
    candidate["source_temporal_relation"] = {
        "canonical_property": observation.get("canonical_property") or "",
        "original_relation": observation.get("original_label") or "",
        "subject_endpoint_type": "Event",
        "object_endpoint_type": "Event",
        "commitment_status": "committed" if observation.get("committed") else ("proposed" if observation.get("proposed") else "not_accepted"),
        "suppression_status": "suppressed" if observation.get("suppressed") else "not_suppressed",
        "inference_status": inference,
        "active": observation.get("active", False),
        "committed": observation.get("committed", False),
        "suppressed": observation.get("suppressed", False),
        "proposed": observation.get("proposed", False),
        "source_kind": observation.get("source_kind") or inference,
        "traceable": observation.get("traceable", True),
    }
    candidate["features"].update(
        {
            "traceable": observation.get("traceable", True),
            "endpoint_types_valid": observation.get("endpoint_types_valid", True),
            "subject_local_key": observation.get("subject_key"),
            "event_local_key": observation.get("subject_key"),
            "object_local_key": observation.get("object_key"),
            "object_candidate_id": "evt-" + str(observation.get("object_key")),
            "local_key": "rel-" + fixture_id,
        }
    )
    candidate["requested_population_profile"] = profile
    return candidate


def _percentage(observation: dict, corpus: str, profile: str) -> dict:
    candidate = _base(observation, corpus, profile, "val-" + str(observation.get("key")), "value_candidate")
    candidate["trigger_or_lexical_form"] = observation.get("lexical") or ""
    candidate["textual_evidence"] = observation.get("lexical") or ""
    candidate["features"].update(
        {
            "local_key": observation.get("key"),
            "mention_key": observation.get("mention_key") or observation.get("key"),
            "value_kind": "percentage",
            "lexical": observation.get("lexical") or "",
            "numerical_value": observation.get("fraction_value") if observation.get("force_fraction") else observation.get("points"),
            "force_fraction": bool(observation.get("force_fraction")),
            "label": observation.get("lexical") or "",
        }
    )
    return candidate


def _money(observation: dict, corpus: str, profile: str) -> dict:
    candidate = _base(observation, corpus, profile, "val-" + str(observation.get("key")), "value_candidate")
    candidate["requested_population_profile"] = "EXTENSION_REVIEWED"
    candidate["trigger_or_lexical_form"] = observation.get("lexical") or ""
    candidate["textual_evidence"] = observation.get("lexical") or ""
    candidate["token_start"] = candidate["token_start"] if candidate["token_start"] is not None else 0
    candidate["token_end"] = candidate["token_end"] if candidate["token_end"] is not None else 3
    candidate["features"].update(
        {
            "local_key": observation.get("key"),
            "value_kind": "money",
            "lexical": observation.get("lexical") or "",
            "numerical_value": observation.get("numerical_value") or "",
            "currency_code": observation.get("currency_code") or "",
            "label": observation.get("lexical") or "",
        }
    )
    return candidate


def _copresence(observation: dict, corpus: str, profile: str) -> dict:
    candidate = _base(observation, corpus, profile, "link-copresence", "value_candidate")
    candidate["textual_evidence"] = "same sentence"
    candidate["trigger_or_lexical_form"] = "co-presence"
    candidate["features"].update(
        {
            "event_value_link": True,
            "co_presence_only": True,
            "attachment_basis": "sentence_copresence",
            "event_candidate_id": "evt-" + str(observation.get("event_key")),
            "value_candidate_id": "val-" + str(observation.get("value_key")),
            "event_local_key": observation.get("event_key"),
            "value_local_key": observation.get("value_key"),
            "local_key": "link-copresence",
        }
    )
    return candidate


def _affected(observation: dict, corpus: str, profile: str) -> dict:
    candidate = _base(observation, corpus, profile, "part-" + str(observation.get("event_key")), "participation_candidate")
    candidate["textual_evidence"] = "argument label" if observation.get("arg_label_only") else "affected market"
    candidate["trigger_or_lexical_form"] = observation.get("source_role") or "participant"
    candidate["features"].update(
        {
            "affected_market": True,
            "predicate": "hasAffectedMarket",
            "arg_label_only": observation.get("arg_label_only"),
            "contextual_attachment": observation.get("contextual_attachment"),
            "event_candidate_id": "evt-" + str(observation.get("event_key")),
            "market_candidate_id": "ent-" + str(observation.get("market_key")),
            "event_local_key": observation.get("event_key"),
            "market_local_key": observation.get("market_key"),
            "source_role": observation.get("source_role") or "",
            "evidence_layers": ["EVENT_PARTICIPANT"] if observation.get("participant_evidence") else [],
            "local_key": "part-" + str(observation.get("event_key")),
        }
    )
    if observation.get("source_role"):
        candidate["source_roles"] = [observation["source_role"]]
    return candidate


def _qualified(observation: dict, corpus: str, profile: str) -> dict:
    candidate = _base(observation, corpus, profile, "part-qualified", "participation_candidate")
    candidate["textual_evidence"] = "qualified participation"
    candidate["trigger_or_lexical_form"] = "met"
    candidate["token_start"] = 2
    candidate["token_end"] = 3
    candidate["features"].update(
        {
            "predicate": observation.get("predicate") or "hasParticipant",
            "relation_status": observation.get("status") or "",
            "event_candidate_id": "evt-" + str(observation.get("subject_key")),
            "object_candidate_id": "ent-" + str(observation.get("object_key")),
            "event_local_key": observation.get("subject_key"),
            "object_local_key": observation.get("object_key"),
            "source_role": observation.get("source_role") or "",
            "local_key": "part-qualified",
        }
    )
    if observation.get("source_role"):
        candidate["source_roles"] = [observation["source_role"]]
    return candidate


def _literal(observation: dict, corpus: str, profile: str) -> dict:
    candidate = _base(observation, corpus, profile, "val-" + str(observation.get("value_key") or "literal"), "value_candidate")
    candidate["document_id"] = observation.get("source_document_id") or "SYN-DOC-001"
    candidate["trigger_or_lexical_form"] = observation.get("lexical") or ""
    candidate["textual_evidence"] = observation.get("lexical") or ""
    candidate["token_start"] = 0
    candidate["token_end"] = 1
    candidate["features"].update(
        {
            "value_kind": "percentage",
            "lexical": observation.get("lexical") or "",
            "numerical_value": observation.get("points") or "",
            "literal_assertion": True,
            "local_key": observation.get("value_key") or "literal",
            "label": observation.get("lexical") or "",
        }
    )
    return candidate
