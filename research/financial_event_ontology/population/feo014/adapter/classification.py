"""Evidence classification for temporal anchors and participant paths.

Class labels are assigned from saved source records. A relation type name
is not treated as sufficient evidence of explicit event time. A frame
argument is not treated as an entity participant unless both canonical
endpoints are present and the participant endpoint is an entity or an
entity mention.
"""

from __future__ import annotations

import re

from adapter.common import as_text

TEMPORAL_PREPOSITIONS = {"on", "in", "at", "during", "around", "by", "following", "since", "after", "before"}
RULE_SOURCE_KINDS = {"rule", "rule_inferred", "inverse_generated", "closure_derived", "model_inferred", "reasoner_entailed"}
STRUCTURAL_ROLES = {
    "ARGM",
    "ARGM-MNR",
    "ARGM-ADV",
    "ARGM-DIR",
    "ARGM-MOD",
    "ARGM-NEG",
    "ARGM-DIS",
    "ARGM-PRD",
    "ARGM-LOC",
    "ARGM-CAU",
    "ARGM-PNC",
    "ARGM-GOL",
    "Support",
    "C-Support",
}
TEMPORAL_ROLES = {"ARGM-TMP", "R-ARGM-TMP", "C-ARGM-TMP"}
LAYER_ORDER = ("EVENT_PARTICIPANT", "HAS_FRAME_ARGUMENT", "PARTICIPANT")
FRAME_ARGUMENT_RE = re.compile(r"^fa_(\d+)_(\d+)_(\d+)_(.+)$")
UNRESOLVED_COLUMNS = [
    "path_id",
    "event_source_id",
    "event_endpoint_type",
    "participant_source_id",
    "participant_endpoint_type",
    "primary_relationship",
    "supporting_relationships",
    "source_roles",
    "frame_id",
    "frame_argument_id",
    "entity_id",
    "mention_id",
    "value_id",
    "time_id",
    "text",
    "document_id",
    "sentence_id",
    "evidence_available",
    "canonical_event_available",
    "canonical_entity_available",
    "duplicate_path",
    "classification",
    "normalisation_action",
    "financial_mapping_eligible",
    "review_required",
    "notes",
]
ANCHOR_COLUMNS = [
    "anchor_id",
    "event_source_id",
    "time_source_id",
    "event_type",
    "time_type",
    "source_relation",
    "source",
    "rule_id",
    "status",
    "commitment",
    "suppression",
    "event_text",
    "time_text",
    "event_span",
    "time_span",
    "same_sentence",
    "explicit_textual_signal",
    "direct_source_annotation",
    "classification",
    "direct_triple_eligible",
    "review_reason",
    "notes",
]


def _bool(value: bool) -> str:
    return "true" if value else "false"


def _span(start, end) -> str:
    if start is None or end is None:
        return ""
    return f"{start}-{end}"


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


def _argument_span(argument_id: str):
    match = FRAME_ARGUMENT_RE.match(argument_id or "")
    if not match:
        return None, None
    start = int(match.group(2))
    end_inclusive = int(match.group(3))
    if end_inclusive < start:
        return None, None
    return start, end_inclusive + 1


def _overlaps(start_a, end_a, start_b, end_b) -> bool:
    if None in (start_a, end_a, start_b, end_b):
        return False
    return start_a < end_b and start_b < end_a


def _token_text(tokens_by_start: dict, start, end) -> str:
    if start is None or end is None:
        return ""
    parts = [tokens_by_start.get(index, "") for index in range(start, end)]
    return " ".join(part for part in parts if part)


def _sentence_for_token(token_sentence: dict, start) -> str:
    if start is None:
        return ""
    return as_text(token_sentence.get(start) or token_sentence.get(str(start)))


def build_time_context(bundle: dict) -> dict:
    mentions = {item["source_identifier"]: item for item in bundle["mentions"]}
    events_by_eid = {}
    for mention_id, eid in bundle["indexes"]["event_by_mention"].items():
        mention = mentions.get(mention_id)
        if mention:
            events_by_eid.setdefault(eid, []).append(mention)
    for event in bundle["canonical_events"]:
        events_by_eid.setdefault(event["source_annotation_identifier"], [])
    times = {item["source_annotation_identifier"]: item for item in bundle["times"]}
    tokens = {}
    for token in bundle["tokens"]:
        if token.get("token_start") is not None:
            tokens[token["token_start"]] = token.get("textual_form") or ""
    return {
        "events_by_eid": events_by_eid,
        "canonical_events": {item["source_annotation_identifier"]: item for item in bundle["canonical_events"]},
        "times": times,
        "tokens": tokens,
        "token_sentence": bundle["indexes"].get("token_sentence") or {},
        "publication_tid": bundle["indexes"].get("publication_tid") or "",
        "publication_value": "",
    }


def _explicit_textual_signal(event_start, event_end, time_start, time_end, tokens: dict, same_sentence: bool) -> bool:
    """Local textual signal. Same-sentence co-presence alone is not a signal."""
    if not same_sentence:
        return False
    if None in (event_start, event_end, time_start, time_end):
        return False
    if time_start == event_end:
        previous = tokens.get(time_start - 1, "").lower()
        return previous in TEMPORAL_PREPOSITIONS and (event_start <= time_start - 1 < event_end or time_start - 1 == event_end - 1)
    if time_end == event_start:
        return True
    return False


def classify_time_anchor(record: dict, context: dict) -> dict:
    properties = record.get("source_properties") or {}
    event_id = as_text((record.get("source_endpoint_identifiers") or {}).get("start") or properties.get("start_eid"))
    time_id = as_text((record.get("source_endpoint_identifiers") or {}).get("end") or properties.get("end_tid"))
    event_mentions = context["events_by_eid"].get(event_id) or []
    event_mention = sorted(event_mentions, key=lambda item: item["source_identifier"])[0] if event_mentions else None
    canonical = context["canonical_events"].get(event_id)
    time_record = context["times"].get(time_id)
    event_text = as_text((event_mention or {}).get("textual_form") or (canonical or {}).get("textual_form") or (canonical or {}).get("lemma"))
    time_text = as_text((time_record or {}).get("textual_form") or (time_record or {}).get("source_properties", {}).get("value") if time_record else "")
    event_start = (event_mention or {}).get("token_start")
    event_end = (event_mention or {}).get("token_end")
    time_start = (time_record or {}).get("token_start") if time_record else None
    time_end = (time_record or {}).get("token_end") if time_record else None
    event_sentence = as_text((event_mention or {}).get("sentence_identifier")) or _sentence_for_token(context["token_sentence"], event_start)
    time_sentence = _sentence_for_token(context["token_sentence"], time_start)
    same_sentence = bool(event_sentence and time_sentence and event_sentence == time_sentence)
    signal = _explicit_textual_signal(event_start, event_end, time_start, time_end, context["tokens"], same_sentence)
    source = as_text(properties.get("source"))
    source_kind = as_text(properties.get("source_kind")).lower()
    rule_id = as_text(properties.get("rule_id"))
    relation_label = as_text(properties.get("rel_type") or properties.get("rel_type_original") or properties.get("rel_type_canonical"))
    rule_attachment = source_kind in RULE_SOURCE_KINDS or "T1_RULE" in source or rule_id.startswith("event_timex_attach")
    direct_annotation = bool(relation_label) and not rule_attachment and source_kind not in RULE_SOURCE_KINDS
    suppressed = bool(properties.get("suppressed"))
    status = as_text(properties.get("status")) or "absent"
    commitment = "committed" if status.lower() in {"asserted", "committed"} and not rule_attachment else "uncommitted"
    publication_tid = context.get("publication_tid") or ""
    function = as_text((time_record or {}).get("source_properties", {}).get("function_in_document") if time_record else "")
    is_document_time = bool(time_id and publication_tid and time_id == publication_tid) or function == "CREATION_TIME"
    endpoints_ok = bool(canonical and time_record)
    notes = []
    if not canonical:
        notes.append("canonical event record is absent")
    if not time_record:
        notes.append("time record is absent")
    if rule_attachment:
        notes.append("provenance is an operational rule attachment")
    if signal:
        notes.append("a local temporal preposition or adjacent modifier is present in the sentence")
    else:
        notes.append("no local explicit textual anchor was observed for this pair")
    if not direct_annotation:
        notes.append("no direct temporal annotation label is stored on the relation")
    normalised = as_text((time_record or {}).get("source_properties", {}).get("value") if time_record else "")
    if normalised.startswith("2007-02-27") and not is_document_time:
        notes.append("normalised value coincides with the document date but the node is not the creation-time anchor")

    if not event_id or not time_id or not endpoints_ok:
        classification = "unresolved"
        review_reason = "An endpoint record is missing, so the anchor is not accepted."
    elif is_document_time:
        classification = "document_time"
        review_reason = "Document publication time is not an event time."
    elif rule_attachment and "prior" in rule_id:
        classification = "inferred_event_time"
        review_reason = "A prior-date rule inferred the attachment. It is not a direct event-time annotation."
    elif rule_attachment:
        classification = "rule_attached_candidate"
        review_reason = "The relation is an operational rule attachment and lacks a direct temporal annotation."
    elif signal and direct_annotation and not suppressed and endpoints_ok:
        classification = "explicit_event_time"
        review_reason = ""
    elif not signal and not direct_annotation:
        classification = "unsupported_attachment"
        review_reason = "Neither a direct annotation nor an explicit local textual signal supports this attachment."
    else:
        classification = "unresolved"
        review_reason = "The stored evidence does not meet the explicit event-time policy."

    eligible = (
        classification == "explicit_event_time"
        and endpoints_ok
        and direct_annotation
        and signal
        and not suppressed
        and not rule_attachment
        and status.lower() not in {"inactive", "deleted"}
    )
    return {
        "anchor_id": record.get("source_identifier") or "",
        "event_source_id": event_id,
        "time_source_id": time_id,
        "event_type": as_text((canonical or {}).get("generic_type") or (event_mention or {}).get("lemma") or (canonical or {}).get("lemma")),
        "time_type": as_text((time_record or {}).get("generic_type") if time_record else ""),
        "source_relation": record.get("relationship_type") or "HAS_TIME_ANCHOR",
        "source": source,
        "rule_id": rule_id,
        "status": status,
        "commitment": commitment,
        "suppression": "suppressed" if suppressed else "not_suppressed",
        "event_text": event_text,
        "time_text": time_text,
        "event_span": _span(event_start, event_end),
        "time_span": _span(time_start, time_end),
        "same_sentence": _bool(same_sentence),
        "explicit_textual_signal": _bool(signal),
        "direct_source_annotation": _bool(direct_annotation),
        "classification": classification,
        "direct_triple_eligible": _bool(eligible),
        "review_reason": review_reason,
        "notes": "; ".join(notes),
        "eligible_explicit": eligible,
        "rule_attachment": rule_attachment,
        "suppressed_bool": suppressed,
    }


def classify_time_anchors(bundle: dict) -> list[dict]:
    context = build_time_context(bundle)
    rows = []
    seen = set()
    for record in bundle["temporal_relations"]:
        if record.get("relationship_type") != "HAS_TIME_ANCHOR":
            continue
        row = classify_time_anchor(record, context)
        pair = (row["event_source_id"], row["time_source_id"])
        if pair in seen and pair != ("", ""):
            row["classification"] = "duplicate"
            row["direct_triple_eligible"] = "false"
            row["eligible_explicit"] = False
            row["review_reason"] = "Duplicate event-time pair consolidated with the retained relation."
        seen.add(pair)
        rows.append(row)
    rows.sort(key=lambda item: item["anchor_id"])
    return rows


def _role_set(roles: list[str]) -> set[str]:
    found = set()
    for role in roles:
        for part in role.split("|"):
            text = part.strip()
            if text:
                found.add(text)
    return found


def _classify_group(group: dict, bundle: dict, mention_index: dict) -> dict:
    roles = _role_set(group["source_roles"])
    argument_id = group["frame_argument_id"]
    span_start, span_end = _argument_span(argument_id)
    tokens = mention_index["tokens"]
    text = _token_text(tokens, span_start, span_end)
    sentence_id = _sentence_for_token(bundle["indexes"].get("token_sentence") or {}, span_start)
    time_hit = ""
    value_hit = ""
    event_hit = ""
    entity_mention_hit = ""
    value_contained = False
    event_contained = False
    time_contained = False

    def _contained(mention) -> bool:
        m_start = mention.get("token_start")
        m_end = mention.get("token_end")
        if None in (span_start, span_end, m_start, m_end):
            return False
        argument_inside = m_start <= span_start and span_end <= m_end
        mention_inside = span_start <= m_start and m_end <= span_end
        if not argument_inside and not mention_inside:
            return False
        shorter = min(span_end - span_start, m_end - m_start)
        longer = max(span_end - span_start, m_end - m_start)
        return longer > 0 and shorter / longer >= 0.8

    for mention in bundle["mentions"]:
        overlaps = _overlaps(span_start, span_end, mention.get("token_start"), mention.get("token_end"))
        contained = _contained(mention)
        if not overlaps and not contained:
            continue
        layer = mention.get("mention_layer")
        if layer == "time" and not time_hit:
            time_hit = mention["source_identifier"]
            time_contained = contained
        elif layer == "value" and not value_hit:
            value_hit = mention["source_identifier"]
            value_contained = contained
        elif layer == "event" and not event_hit:
            event_hit = mention["source_identifier"]
            event_contained = contained
        elif layer == "entity" and not entity_mention_hit:
            entity_mention_hit = mention["source_identifier"]
    entity_known = group["entity_id"] in mention_index["canonical_entity_ids"]
    event_known = group["event_endpoint_type"] == "tevent" and group["event_source_id"] in mention_index["canonical_event_ids"]
    event_mention_known = group["event_endpoint_type"] == "event_mention"
    alignment = group["alignment"]
    temporal_role = bool(roles & TEMPORAL_ROLES) or any(role.endswith("ARGM-TMP") for role in roles)
    structural_only = bool(roles) and roles <= STRUCTURAL_ROLES
    notes = []
    if group["operational_path_count"] > 1:
        notes.append(f"{group['operational_path_count']} operational edges share this endpoint pair")
    if alignment == "frame_argument_aligned" and not entity_known:
        notes.append("REFERS_TO names an entity identifier that has no canonical entity record in the saved extract")
    if alignment == "unresolved_frame_argument":
        notes.append("frame argument has no REFERS_TO entity")
    if temporal_role:
        notes.append("source role is a temporal modifier")
    if time_hit:
        notes.append("argument span overlaps a time mention")
    if value_hit:
        notes.append("argument span overlaps a value mention")
    if event_hit:
        notes.append("argument span overlaps an event mention")

    resolved_entity_participant = entity_known and (event_known or event_mention_known) and (
        alignment in {"entity", "mention"} or alignment == "frame_argument_aligned"
    )
    classification = "unresolved"
    action = "unresolved"
    review = True
    eligible = False
    if not group["event_source_id"] or not group["participant_source_id"]:
        classification = "malformed"
        action = "reject"
        review = True
    elif resolved_entity_participant:
        classification = "valid_entity_participant"
        action = "emit_participation_candidate"
        review = False
        eligible = True
        if alignment == "frame_argument_aligned":
            notes.append("frame argument is aligned to a canonical entity record through REFERS_TO")
    elif alignment == "frame_argument_aligned" and not entity_known:
        classification = "unresolved_reference"
        action = "route_to_review"
    elif group["event_endpoint_type"] == "frame" and not event_known:
        classification = "unresolved_reference"
        action = "route_to_review"
        notes.append("frame is not linked to a canonical event")
    elif temporal_role or time_contained:
        classification = "temporal_argument"
        action = "retain_supporting_evidence"
        review = False
        notes.append("not emitted as an entity participant")
    elif structural_only:
        classification = "structural_only"
        action = "ignore_as_structural"
        review = False
    elif "ARGM-EXT" in roles or value_contained:
        classification = "value_argument"
        action = "retain_supporting_evidence"
        review = False
        notes.append("not emitted as an entity participant")
    elif event_contained:
        classification = "event_argument"
        action = "retain_supporting_evidence"
        review = False
        notes.append("not emitted as an entity participant")
    elif alignment == "mention_without_entity" or group["participant_endpoint_type"] == "mention":
        classification = "mention_without_canonical_entity"
        action = "route_to_review"
    elif alignment == "unresolved_frame_argument" or group["participant_endpoint_type"] == "frame_argument":
        classification = "frame_argument_without_entity"
        action = "retain_supporting_evidence"
        review = True
    else:
        classification = "unresolved"
        action = "route_to_review"

    if group["duplicate_of_emitted"]:
        classification = "duplicate_operational_path"
        action = "deduplicate"
        review = False
        eligible = False
        notes.append("consolidated into the retained participation candidate")

    return {
        "text": text,
        "sentence_id": sentence_id,
        "value_id": value_hit,
        "time_id": time_hit,
        "mention_id": entity_mention_hit or (group["participant_source_id"] if group["participant_endpoint_type"] == "mention" else ""),
        "evidence_available": _bool(bool(text or sentence_id)),
        "canonical_event_available": _bool(event_known or event_mention_known),
        "canonical_entity_available": _bool(entity_known),
        "classification": classification,
        "normalisation_action": action,
        "financial_mapping_eligible": _bool(eligible),
        "review_required": _bool(review),
        "notes": "; ".join(notes),
        "emit": eligible,
    }


def build_participant_groups(bundle: dict) -> list[dict]:
    """Group operational paths, then classify each group from saved evidence."""
    indexes = bundle["indexes"]
    grouped: dict[tuple, dict] = {}
    for record in bundle["participants"]:
        event = _event_side(record, indexes)
        participant = _entity_side(record, indexes)
        if event is None or participant is None:
            event = ("unresolved", record["source_identifier"], "")
            participant = ("unresolved", record["source_identifier"], "unresolved", "")
        key = (event[0], event[1], participant[0], participant[1])
        bucket = grouped.setdefault(
            key,
            {
                "event": event,
                "participant": participant,
                "layers": [],
                "roles": [],
                "records": [],
            },
        )
        layer = record["participant_layer"]
        if layer not in bucket["layers"]:
            bucket["layers"].append(layer)
        for role in record.get("source_roles") or []:
            if role not in bucket["roles"]:
                bucket["roles"].append(role)
        bucket["records"].append(record["source_identifier"])

    mention_index = {
        "tokens": {
            token["token_start"]: token.get("textual_form") or ""
            for token in bundle["tokens"]
            if token.get("token_start") is not None
        },
        "canonical_entity_ids": {item["source_identifier"] for item in bundle["canonical_entities"]},
        "canonical_event_ids": {item["source_annotation_identifier"] for item in bundle["canonical_events"]},
    }
    rows = []
    for key in sorted(grouped):
        bucket = grouped[key]
        present = [layer for layer in LAYER_ORDER if layer in bucket["layers"]]
        primary = present[0] if present else ""
        supporting_layers = present[1:]
        event_type, event_id, _event_raw = bucket["event"]
        part_type, part_id, alignment, raw_argument = bucket["participant"]
        records = sorted(bucket["records"])
        primary_ids = [item for item in records if item.startswith(primary + ":")] if primary else []
        path_id = primary_ids[0] if primary_ids else (records[0] if records else "")
        supporting_ids = [item for item in records if item != path_id]
        frame_id = event_id if event_type == "frame" else ""
        argument_id = raw_argument if alignment in {"frame_argument_aligned", "unresolved_frame_argument"} else ""
        for record_id in records:
            body, _index = record_id.rsplit(":", 1)
            pieces = body.split(":", 2)
            if len(pieces) != 3:
                continue
            _layer, start_id, end_id = pieces
            if not argument_id and start_id.startswith("fa_"):
                argument_id = start_id
            if not frame_id and (start_id.startswith("frame_") or end_id.startswith("frame_")):
                frame_id = start_id if start_id.startswith("frame_") else end_id
        entity_id = part_id if part_type == "entity" else ""
        group = {
            "path_id": path_id,
            "event_source_id": event_id,
            "event_endpoint_type": event_type,
            "participant_source_id": part_id,
            "participant_endpoint_type": part_type,
            "primary_relationship": primary,
            "supporting_relationships": "|".join(supporting_ids),
            "supporting_layers": supporting_layers,
            "source_roles": bucket["roles"],
            "frame_id": frame_id if frame_id.startswith("frame_") else frame_id,
            "frame_argument_id": argument_id if argument_id.startswith("fa_") else "",
            "entity_id": entity_id,
            "mention_id": "",
            "value_id": "",
            "time_id": "",
            "document_id": bundle["document_id"],
            "duplicate_path": _bool(len(records) > 1),
            "operational_path_count": len(records),
            "source_records": records,
            "alignment": alignment,
            "layers": present,
            "duplicate_of_emitted": False,
            "event_lookup": event_id,
            "participant_lookup": part_id,
            "participant_kind_token": part_type,
        }
        classified = _classify_group(group, bundle, mention_index)
        group.update(classified)
        rows.append(group)
    return rows


def unresolved_participant_rows(groups: list[dict]) -> list[dict]:
    """Rows that are not emitted as entity participation candidates."""
    rows = []
    for group in groups:
        if group.get("emit"):
            continue
        rows.append({column: group.get(column, "") for column in UNRESOLVED_COLUMNS})
    return rows
