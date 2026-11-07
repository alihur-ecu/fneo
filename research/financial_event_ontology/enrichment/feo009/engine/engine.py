"""Apply reviewable rules to normalised candidates.

Profiles are evaluated separately. A blocking condition prevents acceptance
even when the rule confidence score is high. Only an accepted decision may
request a direct domain triple.
"""

from __future__ import annotations

from decimal import Decimal

from engine.conditions import View, evaluate_condition
from engine.constants import (
    FNEO_NS,
    GROUP_ORDER,
    KIND_ORDER,
    MAPPING_VERSION,
    RDF_TYPE,
    XSD_NS,
)
from engine.explanations import explain_decision
from engine.identifiers import (
    assertion_iri,
    decision_id,
    object_form_iri,
    object_form_literal,
    resource_iri,
    safe_local_key,
)
from engine.lexicon import default_lexicon, normalise
from engine.profiles import bucket_decision, empty_buckets
from engine.rule_loader import load_rules

ENTITY_CLASSES = {
    "Entity",
    "MarketIndex",
    "EquityMarket",
    "CentralBank",
    "CommercialBank",
    "Currency",
    "EquityShare",
    "FinancialSystem",
    "FinancialSector",
    "FinancialOrganisation",
}
EVENT_CLASSES = {"Event", "MarketChangeEvent", "FinancialEvent"}
VALUE_CLASSES = {"NumericalValue", "PercentageValue", "MonetaryAmount", "QuantityValue"}
TIME_CLASSES = {"TimeEntity"}
ORDER_PROPERTIES = {"precedes", "follows", "simultaneousWith", "occursDuring", "includes"}
EVIDENCE_CONDITIONS = {
    "textual_evidence_present",
    "valid_evidence_span",
    "document_present",
    "traceable_temporal_evidence",
    "source_event_mention",
    "structural_mention_present",
    "value_lexical_present",
    "percentage_lexical_preserved",
    "half_open_span",
}


class Context:
    def __init__(self, candidates: list[dict], lexicon):
        self.candidates = list(candidates)
        self.by_id = {item["candidate_id"]: item for item in candidates}
        self.lexicon = lexicon
        self.decisions: list[dict] = []

    def add(self, decision: dict) -> None:
        self.decisions.append(decision)

    def accepted(self, candidate_id: str | None, target_local: str) -> bool:
        if not candidate_id:
            return False
        for decision in self.decisions:
            if (
                decision["candidate_id"] == candidate_id
                and decision["status"] == "accepted"
                and decision.get("target_local_name") == target_local
            ):
                return True
        return False

    def accepted_any(self, candidate_id: str, names: tuple[str, ...]) -> bool:
        return any(self.accepted(candidate_id, name) for name in names)


def _decimal(value) -> Decimal:
    return Decimal(str(value))


def _score(rule: dict, results: dict) -> tuple[str, list[dict]]:
    total = Decimal("0")
    terms: list[dict] = []
    for condition, weight in (rule.get("confidence_contributions") or {}).items():
        if results.get(condition):
            amount = _decimal(weight)
            total += amount
            terms.append({"condition": condition, "weight": f"{amount:.2f}", "sign": "+"})
    for condition, weight in (rule.get("negative_penalties") or {}).items():
        if results.get(condition):
            amount = _decimal(weight)
            total -= amount
            terms.append({"condition": condition, "weight": f"{amount:.2f}", "sign": "-"})
    if total < 0:
        total = Decimal("0")
    if total > 1:
        total = Decimal("1")
    total = total.quantize(Decimal("0.01"))
    return f"{total:.2f}", terms


def _fired(rule: dict, key: str, results: dict) -> list[str]:
    return [item for item in (rule.get(key) or []) if results.get(item)]


def decide_status(rule: dict, results: dict, score: str) -> str:
    """Blocking, review, and missing requirements override a high score."""
    override = None
    for item in rule.get("outcome_overrides") or []:
        if results.get(item["when"]):
            override = item["status"]
            break
    scope = _fired(rule, "scope_conditions", results)
    rejection = _fired(rule, "rejection_conditions", results)
    blocking = _fired(rule, "blocking_conditions", results)
    review = _fired(rule, "review_conditions", results)
    required_failed = [item for item in rule.get("required_conditions") or [] if not results.get(item)]
    score_value = _decimal(score)
    accept_at = _decimal(rule.get("acceptance_threshold") or "1.00")
    review_at = _decimal(rule.get("review_threshold") or "0.40")

    if scope:
        status = "out_of_scope"
    elif rejection:
        status = "rejected"
    elif override:
        status = override
    elif required_failed:
        status = (
            "requires_review"
            if review or blocking or score_value >= review_at
            else "insufficient_evidence"
        )
    elif blocking or review:
        status = "requires_review"
    elif score_value >= accept_at:
        status = "accepted"
    elif score_value >= review_at:
        status = "requires_review"
    else:
        status = "insufficient_evidence"

    if status == "accepted" and (blocking or review or required_failed or scope or rejection):
        if rejection:
            status = "rejected"
        elif scope:
            status = "out_of_scope"
        elif required_failed and not review and not blocking:
            status = "insufficient_evidence"
        else:
            status = "requires_review"
    return status


def _direct_eligible(status: str, policy: str) -> bool:
    return status == "accepted" and policy in {"direct_and_qualified", "structural_direct"}


def _qualified(status: str, policy: str, rule: dict, results: dict) -> bool:
    if policy in {"structural_direct", "none"}:
        return False
    if rule.get("omit_assertion_unless_accepted") and status != "accepted":
        return False
    if results.get("conflicting_direction_same_event") and status != "accepted":
        return False
    return status in {
        "accepted",
        "requires_review",
        "rejected",
        "suppressed",
        "out_of_scope",
        "insufficient_evidence",
    }


def _manual_review(status: str, rule: dict, candidate: dict) -> str:
    features = candidate.get("features") or {}
    reviewer = features.get("reviewer_decision") == "accepted" or features.get("reviewer_accepted") is True
    if status == "requires_review":
        return "review_required"
    if status == "suppressed":
        return "review_required"
    if status in {"rejected", "out_of_scope", "insufficient_evidence"}:
        return "manually_rejected"
    if status == "accepted" and rule.get("population_profile") == "EXTENSION_REVIEWED" and reviewer:
        return "manually_accepted"
    return "not_reviewed"


def _review_reason(status: str, rule: dict, results: dict) -> str:
    if status != "requires_review":
        return ""
    bits = []
    for condition in _fired(rule, "review_conditions", results):
        bits.append(condition.replace("_", " "))
    for condition in _fired(rule, "blocking_conditions", results):
        bits.append("blocking condition " + condition.replace("_", " "))
    if not bits:
        bits.append("the rule routed this candidate to manual review")
    return "; ".join(bits)


def _candidate_set(rule: dict, status: str, results: dict) -> str:
    target = (rule.get("target_class") or "").rsplit("/", 1)[-1]
    if target != "MarketChangeEvent" and not str(rule.get("rule_id", "")).startswith("FE-MCE"):
        return ""
    if results.get("sensitivity_set_marker") or results.get("dated_descriptor_marker"):
        return "sensitivity"
    if status == "accepted" and rule.get("rule_id") in {"FE-MCE-001", "FE-MCE-005"}:
        return "primary_strict"
    return "neither"


def _local_name(iri: str) -> str:
    if not iri:
        return ""
    return iri.rstrip("/").rsplit("/", 1)[-1].rsplit("#", 1)[-1]


def _corpus(candidate: dict) -> str:
    return str(candidate.get("corpus") or (candidate.get("features") or {}).get("corpus") or "synthetic-feo009")


def _document(candidate: dict) -> str:
    return str(candidate.get("document_id") or "document")


def _key(candidate: dict, field: str, fallback: str) -> str:
    features = candidate.get("features") or {}
    raw = features.get(field) or fallback
    return safe_local_key(str(raw), purpose=field or "local")


def _iri(kind: str, candidate: dict, local: str) -> str:
    return resource_iri(kind, _corpus(candidate), _document(candidate), safe_local_key(local, purpose=kind))


def _subject_kind(rule: dict, candidate: dict) -> str:
    explicit = (candidate.get("features") or {}).get("subject_kind")
    if explicit:
        return str(explicit)
    if candidate["candidate_kind"] == "evidence_candidate":
        return "evidence"
    target = _local_name(rule.get("target_class") or "")
    predicate = _local_name(rule.get("target_property") or "")
    if target in ENTITY_CLASSES:
        return "entity"
    if target in EVENT_CLASSES:
        return "event"
    if target in VALUE_CLASSES:
        return "value"
    if target in TIME_CLASSES:
        return "time"
    if predicate in ORDER_PROPERTIES or predicate in {"hasEventTime", "hasMarketDirection", "hasAffectedMarket", "hasParticipant", "hasReportedValue"}:
        if predicate == "includes":
            return "time"
        return "event"
    if candidate["candidate_kind"] == "value_candidate":
        return "value"
    if candidate["candidate_kind"] == "event_candidate":
        return "event"
    if candidate["candidate_kind"] == "temporal_candidate" and (candidate.get("features") or {}).get("time_mention"):
        return "time"
    return "entity"


def _local_for(candidate: dict, context: Context, pointer: str, own_field: str) -> str:
    features = candidate.get("features") or {}
    if features.get(own_field):
        return str(features[own_field])
    other_id = features.get(pointer)
    if other_id and other_id in context.by_id:
        other = context.by_id[other_id]
        return str((other.get("features") or {}).get("local_key") or other_id)
    return str(features.get("local_key") or candidate["candidate_id"])


def _direction_object(results: dict) -> str:
    if results.get("conflicting_direction_same_event"):
        return ""
    if results.get("direction_up"):
        return FNEO_NS + "UpwardDirection"
    if results.get("direction_down"):
        return FNEO_NS + "DownwardDirection"
    return ""


def _percentage_lexical(candidate: dict) -> tuple[str, str]:
    features = candidate.get("features") or {}
    lexical = str(features.get("lexical") or candidate.get("trigger_or_lexical_form") or "")
    from engine.conditions import _percentage_points

    points = _percentage_points(lexical)
    if points is None:
        raw = features.get("numerical_value")
        return lexical, "" if raw is None else str(raw)
    return lexical, format(points, "f")


def bind_decision(rule: dict, candidate: dict, context: Context, results: dict, status: str) -> dict:
    """Resolve subject, predicate, and object without using a source identifier as an IRI."""
    features = candidate.get("features") or {}
    subject_kind = _subject_kind(rule, candidate)
    if features.get("subject_local_key"):
        subject_local = str(features["subject_local_key"])
    elif subject_kind == "event":
        subject_local = _local_for(candidate, context, "event_candidate_id", "event_local_key")
        if features.get("local_key") and candidate["candidate_kind"] == "event_candidate":
            subject_local = str(features.get("local_key"))
    elif subject_kind == "time" and not features.get("time_mention"):
        subject_local = _local_for(candidate, context, "time_candidate_id", "time_local_key")
    else:
        subject_local = str(features.get("local_key") or candidate["candidate_id"])
    subject_iri = _iri(
        {"entity": "entity", "event": "event", "time": "time", "value": "value", "evidence": "evidence"}[subject_kind],
        candidate,
        subject_local,
    )
    predicate = rule.get("target_property") or RDF_TYPE
    if rule.get("predicate_from_candidate"):
        canonical = str((candidate.get("source_temporal_relation") or {}).get("canonical_property") or "")
        if canonical:
            predicate = FNEO_NS + canonical
    object_iri = ""
    object_lexical = ""
    object_datatype = ""
    target_local = _local_name(rule.get("target_class") or "")
    predicate_local = _local_name(predicate)
    if predicate == RDF_TYPE or predicate_local == "type":
        predicate = RDF_TYPE
        object_iri = rule.get("target_class") or ""
    elif predicate_local == "hasAffectedMarket":
        object_local = _local_for(candidate, context, "market_candidate_id", "market_local_key")
        object_iri = _iri("entity", candidate, object_local)
    elif predicate_local == "hasParticipant":
        object_local = _local_for(candidate, context, "object_candidate_id", "object_local_key")
        object_iri = _iri("entity", candidate, object_local)
    elif predicate_local == "hasEventTime":
        object_local = _local_for(candidate, context, "time_candidate_id", "time_local_key")
        object_iri = _iri("time", candidate, object_local)
    elif predicate_local in ORDER_PROPERTIES:
        if predicate_local == "includes":
            subject_local = _local_for(candidate, context, "time_candidate_id", "time_local_key")
            subject_iri = _iri("time", candidate, subject_local)
            object_local = _local_for(candidate, context, "object_candidate_id", "object_local_key")
            object_iri = _iri("event", candidate, object_local)
        elif predicate_local == "occursDuring":
            object_local = _local_for(candidate, context, "time_candidate_id", "time_local_key")
            object_iri = _iri("time", candidate, object_local)
        else:
            object_local = _local_for(candidate, context, "object_candidate_id", "object_local_key")
            object_iri = _iri("event", candidate, object_local)
        subject_kind = "time" if predicate_local == "includes" else "event"
    elif predicate_local == "hasMarketDirection":
        object_iri = _direction_object(results) if status == "accepted" else ""
    elif predicate_local == "hasReportedValue":
        object_local = _local_for(candidate, context, "value_candidate_id", "value_local_key")
        object_iri = _iri("value", candidate, object_local)
    elif predicate_local == "numericalValue":
        _lexical, points = _percentage_lexical(candidate)
        object_lexical = points
        object_datatype = XSD_NS + "decimal"
    if target_local in VALUE_CLASSES and predicate == RDF_TYPE:
        _lexical, points = _percentage_lexical(candidate)
        features = dict(features)
        features["_lexical_form"] = _lexical
        features["_numeric_points"] = points
    return {
        "subject_kind": subject_kind,
        "subject_local_key": subject_local,
        "subject_iri": subject_iri,
        "predicate_iri": predicate,
        "object_iri": object_iri,
        "object_lexical": object_lexical,
        "object_datatype": object_datatype,
        "target_local_name": target_local if predicate == RDF_TYPE else predicate_local,
        "value_lexical": (features or {}).get("lexical") or candidate.get("trigger_or_lexical_form") or "",
        "value_points": _percentage_lexical(candidate)[1] if target_local in VALUE_CLASSES or predicate_local == "numericalValue" else "",
    }


def _evidence_iris(candidate: dict) -> list[str]:
    features = candidate.get("features") or {}
    local = str(features.get("evidence_key") or features.get("local_key") or candidate["candidate_id"])
    iris = [
        resource_iri(
            "evidence",
            _corpus(candidate),
            _document(candidate),
            safe_local_key(local, purpose="evidence"),
        )
    ]
    mention_kind = {
        "entity_candidate": "entity",
        "event_candidate": "event",
        "value_candidate": "value",
        "temporal_candidate": "time",
        "participation_candidate": "event",
        "evidence_candidate": "entity",
    }.get(candidate["candidate_kind"], "entity")
    if candidate["candidate_kind"] == "temporal_candidate" and features.get("time_mention"):
        mention_kind = "time"
    mention_local = str(features.get("mention_key") or local)
    iris.append(
        resource_iri(
            "mention",
            mention_kind,
            _corpus(candidate),
            _document(candidate),
            safe_local_key(mention_local, purpose="mention"),
        )
    )
    return iris


def _warnings(candidate: dict, context: Context, results: dict, rule: dict) -> list[str]:
    warnings = []
    features = candidate.get("features") or {}
    if features.get("factuality") or features.get("operational_factuality"):
        warnings.append(
            "Operational factuality is stored as source metadata and is not a classification requirement."
        )
    surface = normalise(candidate.get("trigger_or_lexical_form") or "")
    if surface and candidate["candidate_kind"] == "entity_candidate":
        for other in context.candidates:
            if other["candidate_id"] == candidate["candidate_id"]:
                continue
            if other.get("document_id") == candidate.get("document_id"):
                continue
            other_surface = normalise(other.get("trigger_or_lexical_form") or "")
            if other_surface and other_surface == surface:
                warnings.append(
                    "Cross-document identity is deferred. The public individual is document-scoped."
                )
                break
    if results.get("conflicting_direction_same_event"):
        warnings.append("Direction is omitted because the same event carries both upward and downward cues.")
    if results.get("negative_held_out_commercial_bank"):
        warnings.append("The held-out commercial-bank name is excluded from accepted classification.")
    if rule.get("known_limitations"):
        pass
    return warnings


def _profile_for(rule: dict, candidate: dict) -> str:
    if rule.get("decision_profile_mode") == "candidate":
        return candidate["requested_population_profile"]
    return rule["population_profile"]


def _consumes(rule: dict, candidate: dict) -> bool:
    requested = candidate["requested_population_profile"]
    allowed = rule.get("consumes_profiles") or [rule["population_profile"]]
    return requested in allowed


class EnrichmentEngine:
    def __init__(self, rules: list[dict] | None = None, lexicon=None):
        self.rules = list(rules) if rules is not None else load_rules()
        self.lexicon = lexicon or default_lexicon()
        self._fallback = next(rule for rule in self.rules if rule["rule_id"] == "FE-UNMATCHED-001")

    def run(self, envelope: dict) -> dict:
        corpus = envelope.get("corpus") or "synthetic-feo009"
        candidates = []
        for raw in envelope.get("candidates") or []:
            candidate = prepare_candidate(raw, corpus)
            candidates.append(candidate)
        context = Context(candidates, self.lexicon)
        for candidate in sorted(candidates, key=_candidate_sort):
            self._apply_candidate(candidate, context)
            if not any(item["candidate_id"] == candidate["candidate_id"] for item in context.decisions):
                context.add(self._apply_rule(self._fallback, candidate, context))
        self._safeguard_market_change(context)
        for decision in context.decisions:
            decision["explanation"] = explain_decision(decision)
        context.decisions.sort(key=lambda item: (item["candidate_id"], item["rule_id"], item["decision_id"]))
        buckets = empty_buckets()
        for decision in context.decisions:
            bucket_decision(buckets, decision)
        return {
            "fixture_id": envelope.get("fixture_id") or "",
            "mapping_version": MAPPING_VERSION,
            "decisions": context.decisions,
            "by_profile": buckets,
            "documents": list(envelope.get("documents") or []),
            "candidates": candidates,
            "corpus": corpus,
        }

    def _apply_candidate(self, candidate: dict, context: Context) -> None:
        for phase in GROUP_ORDER:
            # Applicability is recomputed each phase so later rules can see
            # decisions already recorded for this candidate.
            in_phase = [
                rule
                for rule in self.rules
                if rule["rule_id"] != "FE-UNMATCHED-001"
                and (rule.get("phase") or rule.get("exclusive_group") or "fallback") == phase
                and _consumes(rule, candidate)
                and _applicable(rule, candidate, context)
            ]
            grouped: dict[str, list[dict]] = {}
            for rule in in_phase:
                key = rule.get("exclusive_group") or ("solo:" + rule["rule_id"])
                grouped.setdefault(key, []).append(rule)
            for key in sorted(grouped):
                group = sorted(grouped[key], key=lambda rule: (-int(rule.get("priority") or 0), rule["rule_id"]))
                context.add(self._apply_rule(group[0], candidate, context))

    def _apply_rule(self, rule: dict, candidate: dict, context: Context) -> dict:
        view = View(candidate, context, self.lexicon)
        condition_ids = []
        for key in (
            "required_conditions",
            "optional_conditions",
            "negative_conditions",
            "blocking_conditions",
            "review_conditions",
            "rejection_conditions",
            "scope_conditions",
        ):
            condition_ids.extend(rule.get(key) or [])
        for item in rule.get("outcome_overrides") or []:
            condition_ids.append(item["when"])
        condition_ids.extend((rule.get("confidence_contributions") or {}).keys())
        results = {}
        for condition_id in condition_ids:
            if condition_id not in results:
                results[condition_id] = evaluate_condition(condition_id, view)
        score, terms = _score(rule, results)
        status = decide_status(rule, results, score)
        policy = rule.get("materialisation_policy") or "direct_and_qualified"
        if status == "accepted" and policy == "direct_and_qualified":
            evidence_ok = results.get("textual_evidence_present") or results.get("traceable_temporal_evidence") or results.get(
                "value_lexical_present"
            )
            if not evidence_ok:
                status = "insufficient_evidence"
                results["missing_evidence_after_score"] = True
        profile = _profile_for(rule, candidate)
        binding = bind_decision(rule, candidate, context, results, status)
        direct = _direct_eligible(status, policy)
        if binding["predicate_iri"].endswith("hasMarketDirection") and not binding["object_iri"]:
            direct = False
            status = "requires_review" if status == "accepted" else status
        qualified = _qualified(status, policy, rule, results) and bool(
            binding["object_iri"] or binding["object_lexical"]
        )
        if not direct and status != "accepted":
            direct = False
        assertion_profile = rule.get("assertion_profile") or (
            candidate["requested_population_profile"]
            if rule.get("decision_profile_mode") == "candidate"
            else rule["population_profile"]
        )
        object_form = (
            object_form_iri(binding["object_iri"])
            if binding["object_iri"]
            else object_form_literal(binding["object_lexical"], binding["object_datatype"] or (XSD_NS + "string"))
        )
        assertion = ""
        if qualified:
            assertion = assertion_iri(
                profile=assertion_profile,
                subject=binding["subject_iri"],
                predicate=binding["predicate_iri"],
                object_form=object_form,
                assertion_kind=rule.get("assertion_kind") or "relation",
            )
        negatives = list(rule.get("negative_conditions") or [])
        failed = [item for item in rule.get("required_conditions") or [] if not results.get(item)]
        missing = list(failed)
        roles = list(candidate.get("source_roles") or [])
        decision = {
            "decision_id": decision_id(rule["rule_id"], candidate["candidate_id"], profile),
            "candidate_id": candidate["candidate_id"],
            "candidate_kind": candidate["candidate_kind"],
            "rule_id": rule["rule_id"],
            "rule_version": rule.get("version") or "",
            "target_iri": rule.get("target_class") or rule.get("target_property") or "",
            "target_label": binding["target_local_name"],
            "target_local_name": binding["target_local_name"],
            "status": status,
            "confidence": score,
            "confidence_terms": terms,
            "acceptance_threshold": str(rule.get("acceptance_threshold")),
            "review_threshold": str(rule.get("review_threshold")),
            "evidence_references": _evidence_iris(candidate) if results.get("textual_evidence_present") or results.get("traceable_temporal_evidence") or candidate.get("textual_evidence") or candidate.get("trigger_or_lexical_form") else [],
            "evidence_satisfied": [item for item in results if results[item] and item in EVIDENCE_CONDITIONS],
            "reasons": _reasons(status, rule, results, failed),
            "satisfied_conditions": sorted(item for item, value in results.items() if value),
            "failed_conditions": failed,
            "missing_conditions": missing,
            "negative_conditions_checked": negatives,
            "negative_conditions_fired": [item for item in negatives if results.get(item)],
            "blocking_conditions_fired": _fired(rule, "blocking_conditions", results),
            "profile": profile,
            "assertion_profile": assertion_profile,
            "direct_triple_eligible": bool(direct and status == "accepted"),
            "qualified_assertion_required": bool(qualified),
            "manual_review_status": _manual_review(status, rule, candidate),
            "manual_review_reason": _review_reason(status, rule, results),
            "source_roles_preserved": roles,
            "source_role_preservation": roles,
            "warnings": _warnings(candidate, context, results, rule),
            "materialisation_policy": policy,
            "assertion_kind": rule.get("assertion_kind") or "relation",
            "assertion_iri": assertion,
            "candidate_set": _candidate_set(rule, status, results),
            "document_id": candidate.get("document_id") or "",
            "source_annotation_ids": list(candidate.get("source_annotation_ids") or []),
            "mapping_version": MAPPING_VERSION,
            "population_method": "documented_rule",
            "original_relation_label": str(
                (candidate.get("source_temporal_relation") or {}).get("original_relation")
                or (candidate.get("source_temporal_relation") or {}).get("original_label")
                or ""
            ),
            "temporal_source_kind": str((candidate.get("source_temporal_relation") or {}).get("source_kind") or ""),
            "temporal_inference": str(
                (candidate.get("source_temporal_relation") or {}).get("inference_status")
                or (candidate.get("source_temporal_relation") or {}).get("inference")
                or ""
            ),
            **binding,
        }
        if decision["direct_triple_eligible"] is False:
            decision["direct_triple_eligible"] = False
        return decision

    def _safeguard_market_change(self, context: Context) -> None:
        """A market-change type without an accepted affected market is not emitted."""
        accepted_events = set()
        for decision in context.decisions:
            if (
                decision["status"] == "accepted"
                and decision.get("target_local_name") == "hasAffectedMarket"
                and decision.get("direct_triple_eligible")
            ):
                accepted_events.add(decision.get("subject_iri"))
        for decision in context.decisions:
            if decision.get("target_local_name") != "MarketChangeEvent":
                continue
            if decision["status"] != "accepted":
                continue
            if decision.get("subject_iri") in accepted_events:
                continue
            decision["status"] = "requires_review"
            decision["direct_triple_eligible"] = False
            decision["manual_review_status"] = "review_required"
            decision["manual_review_reason"] = (
                "Market-change type was not accepted because no affected-market attachment was accepted."
            )
            decision["candidate_set"] = decision.get("candidate_set") or "neither"
            decision["warnings"] = list(decision.get("warnings") or []) + [
                "Direct market-change type suppressed pending an accepted affected market."
            ]
        accepted_mce = {
            item.get("subject_iri")
            for item in context.decisions
            if item.get("target_local_name") == "MarketChangeEvent" and item.get("status") == "accepted"
        }
        for decision in context.decisions:
            if decision.get("target_local_name") != "hasMarketDirection":
                continue
            if decision.get("status") != "accepted":
                continue
            if decision.get("subject_iri") in accepted_mce:
                continue
            decision["status"] = "requires_review"
            decision["direct_triple_eligible"] = False
            decision["qualified_assertion_required"] = False
            decision["assertion_iri"] = ""
            decision["object_iri"] = ""
            decision["manual_review_status"] = "review_required"
            decision["manual_review_reason"] = (
                "Direction was not accepted because the market-change event itself was not accepted."
            )
            if not decision.get("qualified_assertion_required"):
                decision["qualified_assertion_required"] = bool(decision.get("object_iri") or decision.get("object_lexical"))
                if decision["qualified_assertion_required"] and not decision.get("assertion_iri"):
                    object_form = object_form_iri(decision["object_iri"]) if decision.get("object_iri") else object_form_literal(
                        decision.get("object_lexical") or "",
                        decision.get("object_datatype") or (XSD_NS + "string"),
                    )
                    decision["assertion_iri"] = assertion_iri(
                        profile=decision["assertion_profile"],
                        subject=decision["subject_iri"],
                        predicate=decision["predicate_iri"],
                        object_form=object_form,
                        assertion_kind=decision.get("assertion_kind") or "relation",
                    )


def _reasons(status: str, rule: dict, results: dict, failed: list[str]) -> list[str]:
    reasons = [f"Rule {rule['rule_id']} returned {status}."]
    if failed:
        reasons.append("Missing required conditions: " + ", ".join(failed) + ".")
    fired = [item for item in rule.get("negative_conditions") or [] if results.get(item)]
    if fired:
        reasons.append("Negative conditions fired: " + ", ".join(fired) + ".")
    return reasons


def _applicable(rule: dict, candidate: dict, context: Context) -> bool:
    if candidate["candidate_kind"] not in (rule.get("candidate_kinds") or []):
        return False
    view = View(candidate, context, context.lexicon)
    checks = rule.get("applicability_conditions") or []
    if not checks:
        return False
    return all(evaluate_condition(condition_id, view) for condition_id in checks)


def _candidate_sort(candidate: dict) -> tuple:
    kind = candidate["candidate_kind"]
    kind_index = KIND_ORDER.index(kind) if kind in KIND_ORDER else len(KIND_ORDER)
    features = candidate.get("features") or {}
    link_rank = 1 if features.get("event_value_link") or features.get("co_presence_only") else 0
    return (kind_index, link_rank, candidate["candidate_id"])


def prepare_candidate(raw: dict, corpus: str) -> dict:
    candidate = dict(raw)
    features = dict(candidate.get("features") or {})
    candidate["features"] = features
    candidate["corpus"] = candidate.get("corpus") or features.get("corpus") or corpus
    for key in (
        "source_mention_ids",
        "source_annotation_ids",
        "source_roles",
        "participants",
        "explicit_times",
        "values",
    ):
        candidate[key] = list(candidate.get(key) or [])
    candidate["source_temporal_relation"] = dict(candidate.get("source_temporal_relation") or {})
    candidate["provenance"] = dict(candidate.get("provenance") or {})
    role = features.get("source_role")
    if role and role not in candidate["source_roles"]:
        candidate["source_roles"].append(role)
    if not candidate.get("requested_population_profile"):
        raise ValueError(f"Candidate {candidate.get('candidate_id')} has no population profile.")
    return candidate
