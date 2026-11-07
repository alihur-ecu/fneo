"""Coverage tables, review samples, SHACL, and competency-question previews."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from rdflib import Graph

from driver.common import REPO, ensure_adapter_path, excerpt, local_name, sha256_file, write_csv
from driver.tables import SPARQL_DIR, _candidates, _decisions, document_dirs, load_json

ensure_adapter_path()

from adapter.checks import _shacl, validate_accepted  # noqa: E402
from adapter.normalisation.normalise import ensure_engine_path  # noqa: E402

ENTITY_TARGETS = {
    "MarketIndex",
    "EquityMarket",
    "CentralBank",
    "CommercialBank",
    "Currency",
    "EquityShare",
    "FinancialSystem",
    "FinancialSector",
}
VALUE_TARGETS = ("NumericalValue", "PercentageValue", "MonetaryAmount", "QuantityValue")
ORDER_NAMES = {"precedes", "follows", "simultaneousWith", "occursDuring", "includes"}
TRACE_CATEGORIES = (
    "entity_type",
    "event_type",
    "affected_market",
    "event_time",
    "value_type",
    "temporal_order",
)


def _candidate_map(candidates: list[dict]) -> dict:
    return {item["candidate_id"]: item for item in candidates}


def _by_subject(decisions: list[dict]) -> dict:
    grouped = defaultdict(list)
    for decision in decisions:
        if decision.get("subject_iri"):
            grouped[decision["subject_iri"]].append(decision)
    return grouped


def _bucket(decision: dict) -> str:
    target = decision.get("target_local_name") or ""
    predicate = local_name(decision.get("predicate_iri") or "")
    if target in ENTITY_TARGETS and predicate in {"type", ""} or (predicate == "type" and decision.get("subject_kind") == "entity" and target in ENTITY_TARGETS):
        return "entity"
    if target == "MarketChangeEvent":
        return "market"
    return ""


def write_population_tables(root: Path) -> dict:
    decisions = _decisions(root)
    candidates = _candidates(root)
    by_candidate = _candidate_map(candidates)
    by_subject = _by_subject(decisions)
    entity_rows = []
    market_rows = []
    for decision in decisions:
        target = decision.get("target_local_name") or ""
        candidate = by_candidate.get(decision.get("candidate_id"), {})
        features = candidate.get("features") or {}
        if target in ENTITY_TARGETS:
            mention_iri = ""
            mentions = features.get("mention_identity_by_source") or {}
            if mentions:
                mention_iri = sorted(mentions.values())[0]
            entity_rows.append(
                {
                    "document_id": decision.get("document_id"),
                    "candidate_id": decision.get("candidate_id"),
                    "mention_iri": mention_iri,
                    "entity_iri": decision.get("subject_iri") or "",
                    "target_class": target,
                    "rule_id": decision.get("rule_id"),
                    "status": decision.get("status"),
                    "confidence": decision.get("confidence"),
                    "evidence": excerpt(candidate.get("textual_evidence") or "", 180),
                    "manual_review_reason": decision.get("manual_review_reason") or "",
                    "direct_type_triple": decision.get("status") == "accepted" and decision.get("direct_triple_eligible") and decision.get("profile") == "CORE_DETERMINISTIC",
                    "qualified_assertion": bool(decision.get("assertion_iri")),
                    "notes": "Count is a population tally. It is not a correctness judgement.",
                }
            )
        if target == "MarketChangeEvent":
            subject = decision.get("subject_iri") or ""
            related = by_subject.get(subject, [])
            affected = [item for item in related if item.get("target_local_name") == "hasAffectedMarket"]
            directions = [item for item in related if item.get("target_local_name") == "hasMarketDirection"]
            direction = ""
            if directions:
                direction = local_name(directions[0].get("object_iri") or "") or directions[0].get("status")
            if decision.get("candidate_set") == "sensitivity" or "sensitivity_set_marker" in (decision.get("satisfied_conditions") or []):
                kind = "sensitivity"
            elif decision.get("candidate_set") == "primary_strict" or decision.get("rule_id") in {"FE-MCE-001", "FE-MCE-005"}:
                kind = "primary"
            else:
                kind = "other"
            mention = ""
            identity = features.get("mention_identity_by_source") or {}
            if identity:
                mention = sorted(identity.values())[0]
            market_rows.append(
                {
                    "document_id": decision.get("document_id"),
                    "event_candidate_id": decision.get("candidate_id"),
                    "event_iri": subject,
                    "event_mention_iri": mention,
                    "rule_id": decision.get("rule_id"),
                    "primary_or_sensitivity": kind,
                    "status": decision.get("status"),
                    "direction": direction,
                    "affected_market_count": len(affected),
                    "accepted_affected_market_count": sum(1 for item in affected if item.get("status") == "accepted"),
                    "review_affected_market_count": sum(1 for item in affected if item.get("status") == "requires_review"),
                    "evidence": excerpt(candidate.get("textual_evidence") or "", 180),
                    "confidence": decision.get("confidence"),
                    "manual_review_reason": decision.get("manual_review_reason") or "",
                    "notes": "The elicited primary set of 25 events across 18 documents is reference evidence, not a quota.",
                }
            )
    write_csv(
        root / "evaluation/financial_entity_population.csv",
        entity_rows,
        [
            "document_id",
            "candidate_id",
            "mention_iri",
            "entity_iri",
            "target_class",
            "rule_id",
            "status",
            "confidence",
            "evidence",
            "manual_review_reason",
            "direct_type_triple",
            "qualified_assertion",
            "notes",
        ],
    )
    write_csv(
        root / "evaluation/market_change_population.csv",
        market_rows,
        [
            "document_id",
            "event_candidate_id",
            "event_iri",
            "event_mention_iri",
            "rule_id",
            "primary_or_sensitivity",
            "status",
            "direction",
            "affected_market_count",
            "accepted_affected_market_count",
            "review_affected_market_count",
            "evidence",
            "confidence",
            "manual_review_reason",
            "notes",
        ],
    )
    return {"entity_rows": len(entity_rows), "market_rows": len(market_rows), "decisions": decisions, "candidates": candidates}


def _anchor_counts(root: Path, document_id: str) -> Counter:
    path = root / "decisions/per_document" / document_id / "time_anchors.json"
    counts = Counter()
    if not path.is_file():
        return counts
    for row in load_json(path):
        counts[row.get("classification") or "unresolved"] += 1
    return counts


def _relation_counts(root: Path, document_id: str) -> Counter:
    path = root / "extraction/per_document" / document_id / "temporal_relations.json"
    counts = Counter()
    if not path.is_file():
        return counts
    for row in load_json(path):
        counts[row.get("relationship_type") or "unknown"] += 1
        properties = row.get("source_properties") or {}
        if properties.get("suppressed"):
            counts["suppressed"] += 1
        source_kind = str(properties.get("source_kind") or "")
        if source_kind in {"inverse_generated", "closure_derived", "model_inferred", "reasoner_entailed"}:
            counts["experimental_source"] += 1
    return counts


def write_temporal_and_values(root: Path, decisions: list[dict], candidates: list[dict]) -> None:
    by_doc_decisions = defaultdict(list)
    for decision in decisions:
        by_doc_decisions[decision.get("document_id")].append(decision)
    by_doc_candidates = defaultdict(list)
    for candidate in candidates:
        by_doc_candidates[candidate.get("document_id")].append(candidate)
    temporal_rows = []
    value_rows = []
    for document_id in document_dirs(root):
        anchors = _anchor_counts(root, document_id)
        relations = _relation_counts(root, document_id)
        doc_decisions = by_doc_decisions.get(document_id, [])
        doc_candidates = by_doc_candidates.get(document_id, [])
        publication = ""
        for candidate in doc_candidates:
            if candidate.get("candidate_kind") == "temporal_candidate" and (candidate.get("features") or {}).get("local_key") == "publication":
                publication = (candidate.get("features") or {}).get("normalised") or candidate.get("trigger_or_lexical_form") or ""
                break
        event_time = [item for item in doc_decisions if item.get("target_local_name") == "hasEventTime"]
        temporal_rows.append(
            {
                "document_id": document_id,
                "publication_time": publication,
                "time_mention_count": sum(1 for item in doc_candidates if item.get("candidate_kind") == "temporal_candidate" and (item.get("features") or {}).get("time_mention")),
                "time_entity_count": sum(1 for item in doc_candidates if item.get("candidate_kind") == "temporal_candidate" and (item.get("features") or {}).get("local_key")),
                "time_denotation_count": sum(1 for item in doc_candidates if (item.get("features") or {}).get("normalised")),
                "operational_has_time_anchor_count": relations.get("HAS_TIME_ANCHOR", 0),
                "explicit_event_time_candidates": anchors.get("explicit_event_time", 0),
                "rule_attached_anchors": anchors.get("rule_attached_candidate", 0),
                "inferred_anchors": anchors.get("inferred_event_time", 0),
                "accepted_has_event_time": sum(1 for item in event_time if item.get("status") == "accepted"),
                "review_required_has_event_time": sum(1 for item in event_time if item.get("status") == "requires_review"),
                "rejected_anchors": sum(1 for item in event_time if item.get("status") in {"rejected", "insufficient_evidence", "out_of_scope"}),
                "ordering_relation_count": relations.get("TLINK", 0),
                "extension_eligible_committed_relations": sum(
                    1
                    for item in doc_decisions
                    if item.get("profile") == "EXTENSION_REVIEWED" and local_name(item.get("predicate_iri") or "") in ORDER_NAMES and item.get("status") == "accepted"
                ),
                "suppressed_relations": relations.get("suppressed", 0),
                "experimental_relations": sum(1 for item in doc_decisions if item.get("profile") == "EXPERIMENTAL_TEMPORAL") + relations.get("experimental_source", 0),
                "tlink_count": relations.get("TLINK", 0),
                "notes": "TLINK totals are source inventory. They are not accepted temporal facts. Rule-attached anchors are not accepted event time.",
            }
        )
        values = [item for item in doc_candidates if item.get("candidate_kind") == "value_candidate"]
        value_decisions = [item for item in doc_decisions if item.get("target_local_name") in VALUE_TARGETS or item.get("target_local_name") == "hasReportedValue"]
        value_rows.append(
            {
                "document_id": document_id,
                "numerical_value_count": sum(1 for item in value_decisions if item.get("target_local_name") == "NumericalValue"),
                "percentage_value_count": sum(1 for item in value_decisions if item.get("target_local_name") == "PercentageValue"),
                "monetary_amount_count": sum(1 for item in value_decisions if item.get("target_local_name") == "MonetaryAmount"),
                "quantity_value_count": sum(1 for item in value_decisions if item.get("target_local_name") == "QuantityValue"),
                "parse_failures": sum(1 for item in values if "conflicting_stored_number_not_copied" in ((item.get("features") or {}).get("missing_fields") or [])),
                "lexical_form_present": sum(1 for item in values if (item.get("features") or {}).get("lexical")),
                "numeric_form_present": sum(1 for item in values if (item.get("features") or {}).get("numerical_value") not in {None, ""}),
                "currency_code_present": sum(1 for item in values if (item.get("features") or {}).get("currency_code")),
                "document_coverage": 1 if values else 0,
                "sentence_context_present": sum(1 for item in values if item.get("sentence_id")),
                "event_value_candidates": sum(1 for item in value_decisions if item.get("target_local_name") == "hasReportedValue"),
                "accepted_event_value_links": sum(
                    1 for item in value_decisions if item.get("target_local_name") == "hasReportedValue" and item.get("status") == "accepted"
                ),
                "notes": "Values may be materialised independently. Co-presence is not an event-value link.",
            }
        )
    write_csv(
        root / "evaluation/temporal_population.csv",
        temporal_rows,
        list(temporal_rows[0].keys()) if temporal_rows else ["document_id", "notes"],
    )
    write_csv(
        root / "evaluation/value_population.csv",
        value_rows,
        list(value_rows[0].keys()) if value_rows else ["document_id", "notes"],
    )


def _trace_category(decision: dict) -> str:
    target = decision.get("target_local_name") or ""
    predicate = local_name(decision.get("predicate_iri") or "")
    if predicate in ORDER_NAMES:
        return "temporal_order"
    if target == "hasEventTime" or predicate == "hasEventTime":
        return "event_time"
    if target == "hasAffectedMarket" or predicate == "hasAffectedMarket":
        return "affected_market"
    if target in VALUE_TARGETS:
        return "value_type"
    if decision.get("subject_kind") == "event" and predicate == "type":
        return "event_type"
    if decision.get("subject_kind") == "entity" and predicate == "type":
        return "entity_type"
    return ""


def write_traceability(root: Path, decisions: list[dict], candidates: list[dict]) -> dict:
    by_candidate = _candidate_map(candidates)
    grouped = defaultdict(list)
    for decision in decisions:
        if decision.get("status") != "accepted":
            continue
        category = _trace_category(decision)
        if category:
            grouped[(decision.get("document_id"), category)].append(decision)
    rows = []
    missing_financial = 0
    for document_id in document_dirs(root):
        for category in TRACE_CATEGORIES:
            items = grouped.get((document_id, category), [])
            with_evidence = with_token = with_char = with_source = with_rule = with_conf = with_status = with_qualified = 0
            for decision in items:
                candidate = by_candidate.get(decision.get("candidate_id"), {})
                if decision.get("document_id"):
                    pass
                evidence = str(candidate.get("textual_evidence") or "").strip()
                if evidence:
                    with_evidence += 1
                if candidate.get("token_start") is not None and candidate.get("token_end") is not None:
                    with_token += 1
                if candidate.get("character_start") is not None and candidate.get("character_end") is not None:
                    with_char += 1
                if decision.get("source_annotation_ids") or candidate.get("source_annotation_ids"):
                    with_source += 1
                if decision.get("rule_id"):
                    with_rule += 1
                if decision.get("confidence"):
                    with_conf += 1
                if decision.get("status"):
                    with_status += 1
                if decision.get("assertion_iri"):
                    with_qualified += 1
                financial = category in {"entity_type", "event_type", "affected_market", "event_time"}
                if financial and (not evidence or not decision.get("document_id") or not decision.get("rule_id")):
                    missing_financial += 1
            rows.append(
                {
                    "document_id": document_id,
                    "assertion_category": category,
                    "accepted_count": len(items),
                    "with_source_document": len(items),
                    "with_textual_evidence": with_evidence,
                    "with_token_span": with_token,
                    "with_character_span": with_char,
                    "with_source_annotation_id": with_source,
                    "with_rule_id": with_rule,
                    "with_confidence": with_conf,
                    "with_validation_status": with_status,
                    "with_qualified_resource": with_qualified,
                    "missing_trace_count": max(0, len(items) - with_evidence),
                    "notes": "Validation status here is the decision status. Human review has not assigned a label.",
                }
            )
    write_csv(
        root / "evaluation/evidence_traceability.csv",
        rows,
        [
            "document_id",
            "assertion_category",
            "accepted_count",
            "with_source_document",
            "with_textual_evidence",
            "with_token_span",
            "with_character_span",
            "with_source_annotation_id",
            "with_rule_id",
            "with_confidence",
            "with_validation_status",
            "with_qualified_resource",
            "missing_trace_count",
            "notes",
        ],
    )
    return {"missing_financial_evidence": missing_financial}


def write_schema_rules_and_gaps(root: Path, summaries: list[dict], decisions: list[dict]) -> dict:
    schema_rows = []
    invalid = 0
    for document_id in document_dirs(root):
        path = root / "candidates/per_document" / document_id / "schema_errors.json"
        errors = load_json(path) if path.is_file() else []
        invalid += len(errors)
        if errors:
            schema_rows.extend(errors)
        else:
            count = 0
            candidate_path = root / "candidates/per_document" / document_id / "candidates.json"
            if candidate_path.is_file():
                count = len(load_json(candidate_path))
            schema_rows.append(
                {
                    "document_id": document_id,
                    "candidate_id": "ALL",
                    "candidate_kind": "",
                    "schema_valid": "true",
                    "error_message": "",
                    "notes": f"{count} candidates validated",
                }
            )
    write_csv(
        root / "evaluation/candidate_schema_report.csv",
        schema_rows,
        ["document_id", "candidate_id", "candidate_kind", "schema_valid", "error_message", "notes"],
    )
    ensure_engine_path()
    from engine.constants import RULE_VERSION
    from engine.rule_loader import iter_rule_files, load_rules

    rules = load_rules()
    checksums = {path.name: sha256_file(path) for path in iter_rule_files()}
    firing = Counter()
    by_rule_status = defaultdict(Counter)
    rule_profile = {rule["rule_id"]: rule.get("population_profile") or "" for rule in rules}
    for decision in decisions:
        firing[decision.get("rule_id") or ""] += 1
        by_rule_status[decision.get("rule_id") or ""][decision.get("status") or ""] += 1
    firing_rows = []
    for rule in sorted(rules, key=lambda item: item["rule_id"]):
        rule_id = rule["rule_id"]
        counts = by_rule_status.get(rule_id, Counter())
        firing_rows.append(
            {
                "rule_id": rule_id,
                "population_profile": rule_profile.get(rule_id, ""),
                "decisions": firing.get(rule_id, 0),
                "accepted": counts.get("accepted", 0),
                "requires_review": counts.get("requires_review", 0),
                "rejected": counts.get("rejected", 0),
                "insufficient_evidence": counts.get("insufficient_evidence", 0),
                "out_of_scope": counts.get("out_of_scope", 0),
                "suppressed": counts.get("suppressed", 0),
            }
        )
    write_csv(
        root / "evaluation/rule_firing_counts.csv",
        firing_rows,
        ["rule_id", "population_profile", "decisions", "accepted", "requires_review", "rejected", "insufficient_evidence", "out_of_scope", "suppressed"],
    )
    execution_rows = []
    for summary in summaries:
        execution_rows.append(
            {
                "document_id": summary["document_id"],
                "feo009_version": RULE_VERSION,
                "candidate_count": summary.get("candidates", 0),
                "decision_count": summary.get("decisions", 0),
                "accepted": summary.get("accepted", 0),
                "requires_review": summary.get("review_required", 0),
                "rejected": summary.get("rejected", 0),
                "insufficient_evidence": summary.get("insufficient_evidence", 0),
                "out_of_scope": summary.get("out_of_scope", 0),
                "suppressed": summary.get("suppressed", 0),
                "warning_count": summary.get("warnings", 0),
                "rule_error_count": summary.get("errors", 0),
                "notes": summary.get("notes") or "",
            }
        )
    write_csv(
        root / "evaluation/rule_execution_summary.csv",
        execution_rows,
        [
            "document_id",
            "feo009_version",
            "candidate_count",
            "decision_count",
            "accepted",
            "requires_review",
            "rejected",
            "insufficient_evidence",
            "out_of_scope",
            "suppressed",
            "warning_count",
            "rule_error_count",
            "notes",
        ],
    )
    accepted_mce_without_market = 0
    for decision in decisions:
        if decision.get("target_local_name") == "MarketChangeEvent" and decision.get("status") == "accepted":
            subject = decision.get("subject_iri")
            linked = [
                item
                for item in decisions
                if item.get("subject_iri") == subject and item.get("target_local_name") == "hasAffectedMarket" and item.get("status") == "accepted"
            ]
            if not linked and "accepted_market_referent" in (decision.get("satisfied_conditions") or []):
                accepted_mce_without_market += 1
    proposals = [
        {
            "proposal_id": "FEO011-PROP-000",
            "severity": "informational",
            "rule_id": "",
            "documents_affected": len(document_dirs(root)),
            "observation": "No FEO-009 rule text was changed during this dry population.",
            "proposed_change": "None.",
            "applied": "no",
            "notes": "A proposal is not applied in this task.",
        }
    ]
    comma_documents = sorted({
        decision.get("document_id")
        for decision in decisions
        if decision.get("target_local_name") == "PercentageValue"
        and decision.get("status") == "accepted"
        and "," in str(decision.get("value_lexical") or "")
        and "." not in str(decision.get("value_lexical") or "")
    })
    if comma_documents:
        proposals.append(
            {
                "proposal_id": "FEO011-PROP-001",
                "severity": "moderate",
                "rule_id": "VAL-PERCENT-001",
                "documents_affected": len(comma_documents),
                "observation": "An accepted percentage whose lexical form uses a decimal comma, such as 14,66%, is stored as 1466 rather than 14.66 percentage points. The value was not divided by 100.",
                "proposed_change": "Interpret a decimal comma as a decimal mark before applying the percentage-point convention. Do not apply the change in this task.",
                "applied": "no",
                "notes": "Documents: " + ", ".join(comma_documents) + ".",
            }
        )
    if accepted_mce_without_market:
        proposals.append(
            {
                "proposal_id": "FEO011-PROP-002",
                "severity": "important",
                "rule_id": "FE-MCE-001",
                "documents_affected": "",
                "observation": f"{accepted_mce_without_market} accepted market-change decisions record accepted_market_referent but have no accepted hasAffectedMarket decision on the same subject.",
                "proposed_change": "Review whether the affected-market rule should be required before acceptance. Do not apply the change in this task.",
                "applied": "no",
                "notes": "Recorded for later approval.",
            }
        )
    write_csv(
        root / "evaluation/rule_change_proposals.csv",
        proposals,
        ["proposal_id", "severity", "rule_id", "documents_affected", "observation", "proposed_change", "applied", "notes"],
    )
    gaps = [
        {
            "gap_id": "GAP-ADAPT-001",
            "severity": "important",
            "documents_affected": len(document_dirs(root)),
            "observation": "Extension entity rules consume EXTENSION_REVIEWED only. The corrected adapter requests CORE_DETERMINISTIC, so central-bank, commercial-bank, currency, equity-share, financial-system, and financial-sector rules do not fire.",
            "disposition": "Recorded. The adapter was not changed.",
            "applied": "no",
            "notes": "Profile separation follows the corrected adapter.",
        },
        {
            "gap_id": "GAP-ADAPT-002",
            "severity": "important",
            "documents_affected": len(document_dirs(root)),
            "observation": "Ordering relations such as TLINK are extracted and classified as source records. The corrected adapter does not normalise them into temporal candidates, so experimental ordering rules have no candidate to consume.",
            "disposition": "Inventoried in the temporal sample. Not materialised as accepted facts.",
            "applied": "no",
            "notes": "Raw TLINK totals are not accepted temporal facts.",
        },
        {
            "gap_id": "GAP-ADAPT-004",
            "severity": "minor",
            "documents_affected": 1,
            "observation": "The corrected adapter's deterministic Turtle writer emits a raw newline inside a quoted literal when evidence text contains a line break. Document 113330 could not be parsed until the driver escaped those control characters after materialisation.",
            "disposition": "Serialisation repair in the FEO-011 driver. The adapter file was not edited. The literal value is unchanged.",
            "applied": "no",
            "notes": "Not a rule change.",
        },
        {
            "gap_id": "GAP-ADAPT-005",
            "severity": "important",
            "documents_affected": 6,
            "observation": "Six documents produce a core SHACL violation: an entity mention denotes more than one entity, or a time mention is not distinct from its time entity. The documents are 62405, 112579, 115587, 116834, 122475, and 124259.",
            "disposition": "Excluded from the release-eligible consolidated graph and recorded in the exception register. Rules and shapes were not changed.",
            "applied": "no",
            "notes": "Violations were not converted into warnings.",
        },
        {
            "gap_id": "GAP-ADAPT-003",
            "severity": "informational",
            "documents_affected": len(document_dirs(root)),
            "observation": "The FEO-010A explicit event-time policy remains in force. Rule-attached and inferred anchors are not accepted as hasEventTime.",
            "disposition": "Policy retained.",
            "applied": "no",
            "notes": "Zero accepted event-time anchors, if observed, are reported rather than repaired.",
        },
    ]
    write_csv(
        root / "evaluation/multidocument_adapter_gaps.csv",
        gaps,
        ["gap_id", "severity", "documents_affected", "observation", "disposition", "applied", "notes"],
    )
    unmapped = []
    for document_id in document_dirs(root):
        relations = load_json(root / "extraction/per_document" / document_id / "temporal_relations.json")
        observed_path = root / "extraction/per_document" / document_id / "observed_counts.json"
        observed = load_json(observed_path) if observed_path.is_file() else {}
        counts = Counter(row.get("relationship_type") for row in relations)
        for name, count in sorted(counts.items()):
            if name in {"HAS_TIME_ANCHOR", "CREATED_ON"}:
                continue
            unmapped.append(
                {
                    "document_id": document_id,
                    "structure": name or "unnamed_temporal_relation",
                    "count": count,
                    "disposition": "not_normalised_by_corrected_adapter",
                    "notes": "Source inventory only.",
                }
            )
        for key, label in (
            ("frame_argument_count", "FrameArgument"),
            ("spacy_timex_only_count", "SpacyTimexCandidate_without_time_mention"),
            ("quality_finding_count", "QualityFinding"),
        ):
            count = int(observed.get(key) or 0)
            if count:
                unmapped.append(
                    {
                        "document_id": document_id,
                        "structure": label,
                        "count": count,
                        "disposition": "counted_not_copied_as_ontology_instance",
                        "notes": "Preserved as an extraction warning, not as an ontology individual.",
                    }
                )
    write_csv(
        root / "evaluation/unmapped_source_structures.csv",
        unmapped,
        ["document_id", "structure", "count", "disposition", "notes"],
    )
    return {"rule_version": RULE_VERSION, "rule_checksums": checksums, "invalid_candidates": invalid, "proposals": len(proposals), "gaps": gaps}
