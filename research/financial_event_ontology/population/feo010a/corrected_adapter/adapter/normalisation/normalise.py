"""Convert source records into FEO-009 normalised candidates.

Financial classes are not assigned here. The enrichment engine classifies
candidates from their source text, spans, and participant layers.
"""

from __future__ import annotations

import sys
from decimal import Decimal, InvalidOperation

from adapter.classification import build_participant_groups, build_time_context, classify_time_anchor
from adapter.common import as_text, public_key
from adapter.extraction.extractor import feo010_root
from adapter.identity import ADAPTER_VERSION, MAPPING_VERSION, bind_mention_groups, participation_local_key
from adapter.safety.guards import repo_root

LAYER_ORDER = ("EVENT_PARTICIPANT", "HAS_FRAME_ARGUMENT", "PARTICIPANT")
EXPLICIT_EXCLUDED = {
    "inverse_generated",
    "rule_inferred",
    "closure_derived",
    "model_inferred",
    "reasoner_entailed",
}


def ensure_engine_path() -> None:
    path = repo_root() / "research" / "financial_event_ontology" / "enrichment" / "feo009"
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)


def _percentage_points(lexical: str):
    ensure_engine_path()
    from engine.conditions import _percentage_points as parse_points

    return parse_points(lexical)


def _blank(kind: str, candidate_id: str, document_id: str, corpus: str) -> dict:
    return {
        "candidate_id": candidate_id,
        "candidate_kind": kind,
        "document_id": document_id,
        "sentence_id": None,
        "passage_id": None,
        "source_mention_ids": [],
        "source_annotation_ids": [],
        "textual_evidence": "",
        "token_start": None,
        "token_end": None,
        "character_start": None,
        "character_end": None,
        "text_boundary_length": None,
        "token_boundary_length": None,
        "generic_type": "",
        "trigger_or_lexical_form": "",
        "lemma": None,
        "participants": [],
        "source_roles": [],
        "participant_generic_types": [],
        "explicit_times": [],
        "values": [],
        "source_temporal_relation": {},
        "document_publication_time": None,
        "source_confidence": None,
        "provenance": {"origin": "feo010a-adapter", "adapter_version": ADAPTER_VERSION},
        "requested_population_profile": "CORE_DETERMINISTIC",
        "corpus": corpus,
        "features": {},
    }


def _publication(bundle: dict) -> dict | None:
    lexical = ""
    normalised = ""
    for record in bundle["temporal_relations"]:
        if record["relationship_type"] != "CREATED_ON":
            continue
        props = record["source_properties"]
        lexical = as_text(props.get("text") or props.get("value"))
        value = as_text(props.get("value"))
        if len(value) >= 10 and value[4:5] == "-" and value[7:8] == "-":
            normalised = value
    if not lexical and bundle["documents"]:
        lexical = as_text(bundle["documents"][0]["source_properties"].get("creationtime"))
        if len(lexical) >= 10 and lexical[4:5] == "-" and lexical[7:8] == "-":
            normalised = lexical if "T" in lexical else lexical[:10] + "T00:00:00"
    if not lexical and not normalised:
        return None
    return {"lexical": lexical, "normalised": normalised}


def _document_bounds(bundle: dict) -> tuple:
    text = ""
    if bundle["documents"]:
        text = as_text(bundle["documents"][0]["source_properties"].get("text"))
    ends = [item["token_end"] for item in bundle["tokens"] if isinstance(item.get("token_end"), int)]
    token_bound = max(ends) if ends else None
    return (len(text) if text else None), token_bound


def _apply_span(candidate: dict, record: dict, text_bound, token_bound) -> list[str]:
    missing = []
    candidate["token_start"] = record.get("token_start")
    candidate["token_end"] = record.get("token_end")
    candidate["character_start"] = record.get("character_start")
    candidate["character_end"] = record.get("character_end")
    if candidate["token_start"] is None or candidate["token_end"] is None:
        missing.append("token_span")
    elif token_bound is not None:
        candidate["token_boundary_length"] = token_bound
    if candidate["character_start"] is None or candidate["character_end"] is None:
        missing.append("character_span")
    elif text_bound is not None:
        candidate["text_boundary_length"] = text_bound
    return missing


def _entity_side(record: dict, indexes: dict):
    properties = record["source_properties"]
    for side in ("start", "end"):
        labels = set(properties.get(f"{side}_labels") or [])
        app_id = as_text(properties.get(f"{side}_app_id"))
        if "FrameArgument" in labels and app_id:
            mapped = indexes["frame_argument_entity"].get(app_id)
            if mapped:
                return ("entity", mapped, "frame_argument_aligned", app_id)
            return ("frame_argument", app_id, "unresolved_frame_argument", app_id)
        if "Entity" in labels and app_id:
            return ("entity", app_id, "entity", app_id)
        if app_id and labels.intersection({"EntityMention", "NominalMention", "NamedEntity"}):
            mapped = indexes["entity_by_mention"].get(app_id)
            if mapped:
                return ("entity", mapped, "mention", app_id)
            return ("mention", app_id, "mention_without_entity", app_id)
    return None


def _event_side(record: dict, indexes: dict):
    properties = record["source_properties"]
    for side in ("end", "start"):
        labels = set(properties.get(f"{side}_labels") or [])
        app_id = as_text(properties.get(f"{side}_app_id"))
        eid = as_text(properties.get(f"{side}_eid"))
        if "TEvent" in labels and eid:
            return ("tevent", eid, eid)
        if "EventMention" in labels and app_id:
            mapped = indexes["event_by_mention"].get(app_id)
            if mapped:
                return ("tevent", mapped, mapped)
            return ("event_mention", app_id, app_id)
        if "Frame" in labels and app_id:
            mapped = indexes["frame_event"].get(app_id)
            if mapped:
                return ("tevent", mapped, mapped)
            return ("frame", app_id, app_id)
    return None


def deduplicate_participants(bundle: dict) -> list[dict]:
    """Collapse operational participant paths that share an event and a participant."""
    grouped: dict[tuple, dict] = {}
    for record in bundle["participants"]:
        event = _event_side(record, bundle["indexes"])
        participant = _entity_side(record, bundle["indexes"])
        if event is None or participant is None:
            event = ("unresolved", record["source_identifier"], "")
            participant = ("unresolved", record["source_identifier"], "unresolved", "")
        key = (event[0], event[1], participant[0], participant[1])
        bucket = grouped.setdefault(
            key,
            {"event": event, "participant": participant, "layers": [], "roles": [], "records": []},
        )
        layer = record["participant_layer"]
        if layer not in bucket["layers"]:
            bucket["layers"].append(layer)
        for role in record.get("source_roles") or []:
            if role not in bucket["roles"]:
                bucket["roles"].append(role)
        bucket["records"].append(record["source_identifier"])
    rows = []
    for key in sorted(grouped):
        bucket = grouped[key]
        present = [layer for layer in LAYER_ORDER if layer in bucket["layers"]]
        primary = present[0] if present else ""
        supporting = present[1:]
        ambiguity = ""
        if bucket["participant"][2] not in {"entity", "mention"}:
            ambiguity = bucket["participant"][2]
        if bucket["event"][0] == "unresolved" or bucket["participant"][0] == "unresolved":
            ambiguity = ambiguity or "unresolved_endpoint"
        decision = "merged_paths" if len(bucket["records"]) > 1 else "single_path"
        if bucket["event"][0] not in {"tevent", "event_mention"} or ambiguity.startswith("unresolved"):
            decision = "unresolved_not_emitted"
        rows.append(
            {
                "event": bucket["event"],
                "participant": bucket["participant"],
                "primary_layer": primary,
                "supporting_layers": supporting,
                "source_roles": bucket["roles"],
                "operational_path_count": len(bucket["records"]),
                "source_records": bucket["records"],
                "deduplication_decision": decision,
                "ambiguity": ambiguity,
                "candidate_id": "",
                "normalised_candidate_count": 0,
                "notes": "",
            }
        )
    return rows


def _mentions_for(bundle: dict, layer: str, index_name: str, target: str) -> list[dict]:
    found = []
    for mention in bundle["mentions"]:
        if mention.get("mention_layer") != layer:
            continue
        if bundle["indexes"][index_name].get(mention["source_identifier"]) == target:
            found.append(mention)
    return sorted(found, key=lambda item: item["source_identifier"])


def _numeric_feature(lexical: str, stored):
    if stored is None or stored == "":
        return None
    try:
        number = Decimal(str(stored))
    except (InvalidOperation, ValueError):
        return None
    points = _percentage_points(lexical) if lexical else None
    if points is not None and number != points:
        return None
    return format(points if points is not None else number, "f")


def normalise(bundle: dict, corpus: str) -> dict:
    """Return candidates, deduplication rows, and normalisation warnings."""
    document_id = bundle["document_id"]
    publication = _publication(bundle)
    text_bound, token_bound = _document_bounds(bundle)
    sentence_text = bundle["indexes"]["sentence_text"]
    mention_identity = bind_mention_groups(bundle["mentions"], corpus)
    time_context = build_time_context(bundle)

    def mention_key_for(mention_id: str | None):
        if not mention_id:
            return None
        info = mention_identity.get(mention_id)
        return info["local_key"] if info else None
    warnings = []
    candidates = []
    entity_candidates = {}
    event_candidates = {}

    def finish(candidate: dict, record: dict | None, missing: list[str]) -> None:
        if publication:
            candidate["document_publication_time"] = dict(publication)
        candidate["features"]["missing_fields"] = missing
        candidate["features"]["label"] = candidate["trigger_or_lexical_form"]
        if record and record.get("source_confidence") is not None:
            candidate["source_confidence"] = record["source_confidence"]
        candidates.append(candidate)

    for entity in bundle["canonical_entities"]:
        entity_id = entity["source_identifier"]
        local_key = public_key("entity", document_id, entity_id)
        candidate = _blank("entity_candidate", "cand-" + local_key, document_id, corpus)
        mentions = _mentions_for(bundle, "entity", "entity_by_mention", entity_id)
        representative = mentions[0] if mentions else entity
        missing = _apply_span(candidate, representative, text_bound, token_bound)
        if not mentions:
            missing.append("entity_mention")
        surface = as_text(representative.get("textual_form") or entity.get("textual_form"))
        sentence_id = representative.get("sentence_identifier")
        candidate["sentence_id"] = sentence_id
        candidate["textual_evidence"] = sentence_text.get(sentence_id or "", surface)
        candidate["trigger_or_lexical_form"] = surface
        candidate["generic_type"] = as_text(entity.get("generic_type"))
        candidate["lemma"] = representative.get("lemma")
        candidate["source_mention_ids"] = [item["source_identifier"] for item in mentions]
        candidate["source_annotation_ids"] = [entity_id]
        candidate["features"].update(
            {
                "local_key": local_key,
                "mention_key": mention_key_for(mentions[0]["source_identifier"]) if mentions else None,
                "other_mention_ids": [item["source_identifier"] for item in mentions[1:]],
                "source_entity_id": entity_id,
            }
        )
        if " and " in surface.lower():
            candidate["features"]["conjunction"] = True
        finish(candidate, representative, missing)
        entity_candidates[entity_id] = candidate

    for mention in bundle["mentions"]:
        if mention.get("mention_layer") != "entity":
            continue
        if mention["source_identifier"] in bundle["indexes"]["entity_by_mention"]:
            continue
        local_key = public_key("entity", document_id, "mention:" + mention["source_identifier"])
        candidate = _blank("entity_candidate", "cand-" + local_key, document_id, corpus)
        missing = _apply_span(candidate, mention, text_bound, token_bound)
        missing.append("canonical_entity")
        surface = as_text(mention.get("textual_form"))
        sentence_id = mention.get("sentence_identifier")
        candidate["sentence_id"] = sentence_id
        candidate["textual_evidence"] = sentence_text.get(sentence_id or "", surface)
        candidate["trigger_or_lexical_form"] = surface
        candidate["generic_type"] = as_text(mention.get("generic_type"))
        candidate["lemma"] = mention.get("lemma")
        candidate["source_mention_ids"] = [mention["source_identifier"]]
        candidate["source_annotation_ids"] = [mention["source_identifier"]]
        candidate["features"].update(
            {
                "local_key": local_key,
                "mention_key": mention_key_for(mention["source_identifier"]),
                "mention_without_canonical_entity": True,
            }
        )
        finish(candidate, mention, missing)
        entity_candidates["mention:" + mention["source_identifier"]] = candidate

    for event in bundle["canonical_events"]:
        eid = event["source_annotation_identifier"]
        local_key = public_key("event", document_id, "eid:" + eid)
        candidate = _blank("event_candidate", "cand-" + local_key, document_id, corpus)
        mentions = _mentions_for(bundle, "event", "event_by_mention", eid)
        representative = mentions[0] if mentions else event
        missing = _apply_span(candidate, representative, text_bound, token_bound)
        if not mentions:
            missing.append("event_mention")
        surface = as_text(representative.get("textual_form") or representative.get("lemma") or event.get("textual_form"))
        sentence_id = representative.get("sentence_identifier")
        candidate["sentence_id"] = sentence_id
        candidate["textual_evidence"] = sentence_text.get(sentence_id or "", surface)
        candidate["trigger_or_lexical_form"] = surface
        candidate["lemma"] = representative.get("lemma") or event.get("lemma")
        candidate["generic_type"] = as_text(event.get("generic_type") or representative.get("generic_type"))
        candidate["source_mention_ids"] = [item["source_identifier"] for item in mentions]
        candidate["source_annotation_ids"] = [eid]
        candidate["features"].update(
            {
                "local_key": local_key,
                "mention_key": mention_key_for(mentions[0]["source_identifier"]) if mentions else None,
                "other_mention_ids": [item["source_identifier"] for item in mentions[1:]],
                "source_event_eid": eid,
                "evidence_key": public_key("evidence", document_id, local_key),
                "primary_participant_local_keys": [],
            }
        )
        finish(candidate, representative, missing)
        event_candidates[eid] = candidate

    for mention in bundle["mentions"]:
        if mention.get("mention_layer") != "event":
            continue
        if mention["source_identifier"] in bundle["indexes"]["event_by_mention"]:
            continue
        local_key = public_key("event", document_id, "mention:" + mention["source_identifier"])
        candidate = _blank("event_candidate", "cand-" + local_key, document_id, corpus)
        missing = _apply_span(candidate, mention, text_bound, token_bound)
        missing.append("canonical_event")
        surface = as_text(mention.get("textual_form") or mention.get("lemma"))
        sentence_id = mention.get("sentence_identifier")
        candidate["sentence_id"] = sentence_id
        candidate["textual_evidence"] = sentence_text.get(sentence_id or "", surface)
        candidate["trigger_or_lexical_form"] = surface
        candidate["lemma"] = mention.get("lemma")
        candidate["generic_type"] = as_text(mention.get("generic_type"))
        candidate["source_mention_ids"] = [mention["source_identifier"]]
        candidate["source_annotation_ids"] = [mention["source_identifier"]]
        candidate["features"].update(
            {
                "local_key": local_key,
                "mention_key": mention_key_for(mention["source_identifier"]),
                "evidence_key": public_key("evidence", document_id, local_key),
                "primary_participant_local_keys": [],
            }
        )
        finish(candidate, mention, missing)
        event_candidates["mention:" + mention["source_identifier"]] = candidate

    participant_groups = build_participant_groups(bundle)
    dedup_rows = []
    for group in participant_groups:
        event_key = group["event_lookup"]
        participant_id = group["participant_lookup"]
        alignment = group["alignment"]
        event_candidate = event_candidates.get(event_key) or event_candidates.get("mention:" + event_key)
        entity_candidate = entity_candidates.get(participant_id)
        if group["participant_kind_token"] == "mention":
            entity_candidate = entity_candidates.get("mention:" + participant_id)
        if not group["emit"] or event_candidate is None or entity_candidate is None:
            group["emit"] = False
            dedup_rows.append(group)
            continue
        local_key = participation_local_key(
            document_id,
            event_key,
            participant_id,
            "entity_participant",
            "hasParticipant",
            MAPPING_VERSION,
        )
        candidate = _blank("participation_candidate", "cand-" + local_key, document_id, corpus)
        candidate["sentence_id"] = event_candidate.get("sentence_id")
        candidate["textual_evidence"] = event_candidate.get("textual_evidence") or ""
        candidate["trigger_or_lexical_form"] = entity_candidate.get("trigger_or_lexical_form") or ""
        for field in ("token_start", "token_end", "character_start", "character_end", "text_boundary_length", "token_boundary_length"):
            candidate[field] = entity_candidate.get(field)
        candidate["source_roles"] = list(group["source_roles"])
        candidate["source_annotation_ids"] = list(group["source_records"])
        candidate["source_mention_ids"] = list(entity_candidate.get("source_mention_ids") or [])
        layers = list(group["layers"])
        candidate["participants"] = [
            {
                "event_source_id": event_key,
                "participant_source_id": participant_id,
                "primary_layer": group["primary_relationship"],
                "supporting_layers": list(group["supporting_layers"]),
                "supporting_path_ids": list(group["source_records"]),
            }
        ]
        candidate["features"].update(
            {
                "local_key": local_key,
                "evidence_layers": layers,
                "event_candidate_id": event_candidate["candidate_id"],
                "event_local_key": event_candidate["features"]["local_key"],
                "object_candidate_id": entity_candidate["candidate_id"],
                "object_local_key": entity_candidate["features"]["local_key"],
                "participant_entity_local_key": entity_candidate["features"]["local_key"],
                "source_role": group["source_roles"][0] if group["source_roles"] else "",
                "endpoint_alignment": alignment,
                "evidence_key": event_candidate["features"].get("evidence_key"),
                "participant_candidate_kind": "entity_participant",
                "selected_relation": "hasParticipant",
                "mapping_version": MAPPING_VERSION,
                "supporting_path_ids": list(group["source_records"]),
            }
        )
        missing = []
        if not candidate["source_roles"]:
            missing.append("source_role")
        finish(candidate, None, missing)
        group["candidate_id"] = candidate["candidate_id"]
        group["participation_key"] = local_key
        dedup_rows.append(group)
        if group["primary_relationship"] == "EVENT_PARTICIPANT":
            keys = event_candidate["features"]["primary_participant_local_keys"]
            local = entity_candidate["features"]["local_key"]
            if local not in keys:
                keys.append(local)

    time_candidates = {}
    publication_tid = bundle["indexes"].get("publication_tid") or ""
    for time_record in bundle["times"]:
        tid = time_record["source_annotation_identifier"]
        local_key = "publication" if tid and tid == publication_tid else public_key("time", document_id, "tid:" + tid)
        candidate = _blank("temporal_candidate", "cand-" + local_key, document_id, corpus)
        mention_id = time_record.get("mention_identifier")
        mention = next((item for item in bundle["mentions"] if item["source_identifier"] == mention_id), None)
        missing = _apply_span(candidate, mention or time_record, text_bound, token_bound)
        surface = as_text((mention or time_record).get("textual_form") or time_record["source_properties"].get("value"))
        candidate["trigger_or_lexical_form"] = surface
        candidate["textual_evidence"] = surface
        candidate["generic_type"] = as_text(time_record.get("generic_type"))
        candidate["source_annotation_ids"] = [tid] if tid else []
        candidate["source_mention_ids"] = [mention_id] if mention_id else []
        normalised = as_text(time_record["source_properties"].get("value"))
        candidate["features"].update(
            {
                "local_key": local_key,
                "time_mention": bool(mention_id),
                "mention_key": mention_key_for(mention_id),
                "normalised": normalised or None,
                "source_tid": tid,
            }
        )
        finish(candidate, time_record, missing)
        time_candidates[tid] = candidate

    for relation in bundle["temporal_relations"]:
        if relation["relationship_type"] != "HAS_TIME_ANCHOR":
            continue
        props = relation["source_properties"]
        eid = as_text(props.get("start_eid"))
        tid = as_text(props.get("end_tid"))
        if tid and tid == publication_tid:
            warnings.append("an explicit anchor targets publication time and was not normalised as event time")
            continue
        event_candidate = event_candidates.get(eid)
        time_candidate = time_candidates.get(tid)
        if event_candidate is None or time_candidate is None:
            warnings.append("an explicit anchor is missing an endpoint candidate")
            continue
        local_key = public_key("event-time", document_id, eid + "|" + tid)
        candidate = _blank("temporal_candidate", "cand-" + local_key, document_id, corpus)
        candidate["textual_evidence"] = event_candidate.get("textual_evidence") or ""
        candidate["trigger_or_lexical_form"] = time_candidate.get("trigger_or_lexical_form") or ""
        for field in ("token_start", "token_end", "character_start", "character_end", "text_boundary_length", "token_boundary_length"):
            candidate[field] = event_candidate.get(field)
        candidate["source_annotation_ids"] = [eid, tid]
        suppressed = bool(props.get("suppressed"))
        classified = classify_time_anchor(relation, time_context)
        if classified["classification"] == "document_time":
            warnings.append("document publication time was not normalised as event time")
            continue
        # Explicit event time requires textual, annotation, and provenance evidence.
        # A rule attachment is not promoted because the source relation is named HAS_TIME_ANCHOR.
        if classified["eligible_explicit"]:
            inference = "explicit"
            source_kind = "explicit"
        elif classified["rule_attachment"] or classified["classification"] in {
            "rule_attached_candidate",
            "inferred_event_time",
        }:
            inference = "rule_inferred"
            source_kind = "rule_inferred"
        else:
            inference = "not_explicit"
            source_kind = "not_explicit"
        candidate["source_temporal_relation"] = {
            "canonical_property": "hasEventTime",
            "original_relation": "HAS_TIME_ANCHOR",
            "original_label": as_text(props.get("rel_type") or "HAS_TIME_ANCHOR"),
            "committed": not suppressed,
            "active": not suppressed,
            "suppressed": suppressed,
            "proposed": False,
            "inference_status": inference if not suppressed else "not_explicit",
            "source_kind": source_kind,
            "subject_endpoint_type": "Event",
            "object_endpoint_type": "TimeEntity",
        }
        candidate["features"].update(
            {
                "local_key": local_key,
                "event_time": True,
                "time_mention": False,
                "event_candidate_id": event_candidate["candidate_id"],
                "event_local_key": event_candidate["features"]["local_key"],
                "time_candidate_id": time_candidate["candidate_id"],
                "time_local_key": time_candidate["features"]["local_key"],
                "time_normalised": time_candidate["features"].get("normalised"),
                "evidence_key": event_candidate["features"].get("evidence_key"),
                "anchor_classification": classified["classification"],
                "anchor_review_reason": classified["review_reason"],
                "explicit_textual_signal": classified["explicit_textual_signal"] == "true",
                "direct_source_annotation": classified["direct_source_annotation"] == "true",
                "operational_rule_id": classified["rule_id"],
                "operational_source": classified["source"],
            }
        )
        finish(candidate, relation, [])

    for value in bundle["values"]:
        value_id = value["source_identifier"]
        local_key = public_key("value", document_id, value_id)
        candidate = _blank("value_candidate", "cand-" + local_key, document_id, corpus)
        mention_id = value.get("mention_identifier")
        mention = next((item for item in bundle["mentions"] if item["source_identifier"] == mention_id), None)
        missing = _apply_span(candidate, mention or value, text_bound, token_bound)
        lexical = as_text((mention or value).get("textual_form") or value["source_properties"].get("value"))
        stored = value["source_properties"].get("value")
        numeric = _numeric_feature(lexical, stored)
        if stored not in (None, "") and numeric is None and lexical and _percentage_points(lexical) is not None:
            missing.append("conflicting_stored_number_not_copied")
        candidate["trigger_or_lexical_form"] = lexical
        candidate["textual_evidence"] = lexical
        candidate["generic_type"] = as_text(value.get("generic_type"))
        candidate["sentence_id"] = (mention or value).get("sentence_identifier")
        candidate["source_annotation_ids"] = [value_id]
        candidate["source_mention_ids"] = [mention_id] if mention_id else []
        candidate["features"].update(
            {
                "local_key": local_key,
                "lexical": lexical,
                "numerical_value": numeric,
                "mention_key": mention_key_for(mention_id),
                "source_value_type": as_text(value.get("generic_type")) or None,
            }
        )
        finish(candidate, value, missing)

    seen_evidence = set()
    for candidate in list(candidates):
        if candidate["candidate_kind"] != "event_candidate":
            continue
        evidence_key = candidate["features"].get("evidence_key")
        if not evidence_key or evidence_key in seen_evidence:
            continue
        seen_evidence.add(evidence_key)
        evidence = _blank("evidence_candidate", "cand-" + evidence_key, document_id, corpus)
        evidence["sentence_id"] = candidate.get("sentence_id")
        evidence["textual_evidence"] = candidate.get("textual_evidence") or ""
        evidence["trigger_or_lexical_form"] = candidate.get("trigger_or_lexical_form") or ""
        for field in ("token_start", "token_end", "character_start", "character_end", "text_boundary_length", "token_boundary_length"):
            evidence[field] = candidate.get(field)
        evidence["source_annotation_ids"] = list(candidate.get("source_annotation_ids") or [])
        evidence["features"] = {"local_key": evidence_key, "label": (evidence["textual_evidence"] or "")[:240], "missing_fields": []}
        if publication:
            evidence["document_publication_time"] = dict(publication)
        candidates.append(evidence)

    for candidate in candidates:
        mapping = {}
        for mention_id in candidate.get("source_mention_ids") or []:
            info = mention_identity.get(mention_id)
            if info:
                mapping[mention_id] = info["local_key"]
        if mapping:
            candidate.setdefault("features", {})["mention_identity_by_source"] = mapping
    candidates.sort(key=lambda item: (item["candidate_kind"], item["candidate_id"]))
    return {
        "candidates": candidates,
        "deduplication": [
            {
                "candidate_id": row.get("candidate_id") or "",
                "event_source_id": row.get("event_source_id") or "",
                "participant_source_id": row.get("participant_source_id") or "",
                "primary_layer": row.get("primary_relationship") or "",
                "supporting_layers": "|".join(row.get("supporting_layers") or []),
                "source_roles": "|".join(row.get("source_roles") or []),
                "operational_path_count": row.get("operational_path_count") or 0,
                "normalised_candidate_count": 1 if row.get("candidate_id") else 0,
                "deduplication_decision": "emitted" if row.get("candidate_id") else row.get("classification") or "",
                "ambiguity": row.get("alignment") or "",
                "notes": row.get("notes") or "",
                "classification": row.get("classification") or "",
                "normalisation_action": row.get("normalisation_action") or "",
                "participation_key": row.get("participation_key") or "",
                "path_id": row.get("path_id") or "",
                "supporting_path_ids": "|".join(row.get("source_records") or []),
            }
            for row in dedup_rows
        ],
        "participant_groups": dedup_rows,
        "mention_identity": mention_identity,
        "warnings": warnings,
        "publication": publication,
    }


def attach_accepted_markets(candidates: list[dict], decisions: list[dict]) -> list[str]:
    """Copy accepted market candidate identifiers onto existing participant paths."""
    accepted = {}
    for decision in decisions:
        if decision.get("profile") != "CORE_DETERMINISTIC" or decision.get("status") != "accepted":
            continue
        if decision.get("target_local_name") in {"MarketIndex", "EquityMarket"}:
            accepted[decision["candidate_id"]] = decision["target_local_name"]
    by_id = {item["candidate_id"]: item for item in candidates}
    local_to_ids: dict[str, list[str]] = {}
    for candidate_id in sorted(accepted):
        candidate = by_id.get(candidate_id)
        if candidate:
            local_to_ids.setdefault(candidate["features"]["local_key"], []).append(candidate_id)
    notes = []
    for candidate in candidates:
        if candidate["candidate_kind"] != "event_candidate":
            continue
        matched = []
        for local_key in candidate["features"].get("primary_participant_local_keys") or []:
            matched.extend(local_to_ids.get(local_key, []))
        matched = sorted(set(matched))
        if len(matched) == 1:
            chosen = by_id[matched[0]]
            candidate["features"]["market_candidate_id"] = matched[0]
            candidate["features"]["market_local_key"] = chosen["features"]["local_key"]
            candidate["features"]["market_surface"] = chosen.get("trigger_or_lexical_form") or ""
            candidate["features"]["evidence_layers"] = ["EVENT_PARTICIPANT"]
        elif len(matched) > 1:
            candidate["features"]["ambiguous_attachment"] = True
            candidate["features"]["candidate_market_ids"] = matched
            notes.append(candidate["candidate_id"] + " has more than one accepted market participant")
    for candidate in candidates:
        if candidate["candidate_kind"] != "participation_candidate":
            continue
        ids = local_to_ids.get(candidate["features"].get("participant_entity_local_key") or "", [])
        layers = candidate["features"].get("evidence_layers") or []
        if len(ids) == 1 and "EVENT_PARTICIPANT" in layers:
            chosen = by_id[ids[0]]
            candidate["features"]["market_candidate_id"] = ids[0]
            candidate["features"]["market_local_key"] = chosen["features"]["local_key"]
    return notes


def feo010_candidates_dir():
    return feo010_root()
