"""Build source records from reviewed query rows.

Neo4j element identifiers are used only as transient join keys and are
removed before a record is returned.
"""

from __future__ import annotations

from adapter.common import as_int, as_json, as_text, character_span, token_span

EXPERIMENTAL_SOURCE_KINDS = {
    "inverse_generated",
    "rule_inferred",
    "closure_derived",
    "model_inferred",
    "reasoner_entailed",
}


def _labels(row: dict) -> list[str]:
    labels = row.get("labels") or []
    return sorted(str(label) for label in labels)


def _warning(*notes: str) -> str:
    return "warning" if any(notes) else "none"


def _record(
    kind: str,
    source_id: str,
    document_id: str,
    labels: list[str],
    relationship_type: str | None,
    properties: dict,
    provenance: dict,
    eligibility: str,
    notes: list[str],
    endpoints: dict | None = None,
    textual_form: str | None = None,
    token_start=None,
    token_end=None,
    character_start=None,
    character_end=None,
    span_convention: str | None = None,
    sentence_identifier: str | None = None,
    generic_type: str | None = None,
    lemma: str | None = None,
    source_confidence=None,
    source_annotation_identifier: str | None = None,
    extra: dict | None = None,
) -> dict:
    record = {
        "source_record_id": f"{kind}:{source_id}",
        "record_kind": kind,
        "source_labels": labels,
        "relationship_type": relationship_type,
        "source_identifier": source_id,
        "document_identifier": document_id,
        "source_properties": properties,
        "source_endpoint_identifiers": endpoints,
        "provenance": provenance,
        "extraction_warning_state": _warning(*notes),
        "mapping_eligibility_state": eligibility,
        "textual_form": textual_form,
        "token_start": token_start,
        "token_end": token_end,
        "character_start": character_start,
        "character_end": character_end,
        "span_convention": span_convention,
        "sentence_identifier": sentence_identifier,
        "generic_type": generic_type,
        "lemma": lemma,
        "source_confidence": source_confidence,
        "source_annotation_identifier": source_annotation_identifier,
        "notes": [note for note in notes if note],
    }
    if extra:
        record.update(extra)
    return record


def _node_properties(row: dict) -> dict:
    keys = (
        "app_id", "doc_id", "source", "text", "value", "pred", "class_code", "eid", "tid",
        "start_char", "end_char", "start_tok", "end_tok", "confidence", "lemma", "ent_class",
        "type_prop", "head", "framework", "function_in_document", "pos", "upos",
        "tok_index_doc", "sentence_id", "title", "creationtime", "filename", "public_id",
        "source_url", "dct_synthetic", "dct_missing", "dct_source", "author", "filetype",
        "sent_index", "sentence_index",
    )
    return {key: row.get(key) for key in keys if key in row}


def _surface(row: dict) -> str:
    for key in ("text", "value", "head", "pred"):
        if row.get(key):
            return as_text(row[key])
    return ""


def _spans(row: dict, surface: str) -> tuple:
    token_start, token_end, token_note = token_span(row.get("start_tok"), row.get("end_tok"))
    character_start, character_end, character_note = character_span(
        row.get("start_char"), row.get("end_char"), surface
    )
    notes = []
    if token_note == "invalid":
        notes.append("token span is not ordered")
        token_start, token_end = None, None
    if character_note == "invalid":
        notes.append("character span is not ordered")
        character_start, character_end = None, None
    convention = ",".join(item for item in (token_note, character_note) if item)
    return token_start, token_end, character_start, character_end, convention, notes


def _confidence(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return value
    return as_text(value)


def _sentence_for(token_sentence: dict, start_tok) -> str | None:
    index = as_int(start_tok)
    if index is None:
        return None
    return token_sentence.get(index)


def build_records(results: dict, document_id: str) -> dict:
    """Convert query rows into stable source records for one document."""
    warnings: list[str] = []
    documents = []
    for row in results.get("Q07_selected_document") or []:
        surface = as_text(row.get("title"))
        notes = []
        if not row.get("text"):
            notes.append("document text is empty")
        documents.append(
            _record(
                "document",
                document_id,
                document_id,
                _labels(row),
                None,
                _node_properties(row),
                {"query_id": "Q07_selected_document", "graph_source": row.get("source")},
                "eligible",
                notes,
                textual_form=surface or None,
                source_annotation_identifier=document_id,
            )
        )
    if len(documents) != 1:
        warnings.append(f"selected document row count is {len(documents)}")

    token_sentence = {}
    tokens = []
    for row in results.get("Q12_tokens") or []:
        source_id = as_text(row.get("app_id")) or f"token-{row.get('tok_index_doc')}"
        surface = _surface(row)
        token_start, token_end, character_start, character_end, convention, notes = _spans(row, surface)
        sentence_id = as_text(row.get("sentence_id")) or None
        index = as_int(row.get("tok_index_doc"))
        if index is not None and sentence_id:
            token_sentence[index] = sentence_id
        tokens.append(
            _record(
                "token",
                source_id,
                document_id,
                _labels(row) or ["TagOccurrence"],
                None,
                _node_properties(row),
                {"query_id": "Q12_tokens", "graph_source": row.get("source")},
                "eligible_span_support",
                notes,
                textual_form=surface or None,
                token_start=token_start,
                token_end=token_end,
                character_start=character_start,
                character_end=character_end,
                span_convention=convention,
                sentence_identifier=sentence_id,
                lemma=as_text(row.get("lemma")) or None,
                source_annotation_identifier=source_id,
            )
        )

    sentences = []
    sentence_text = {}
    for row in results.get("Q11_sentences") or []:
        source_id = as_text(row.get("app_id"))
        if not source_id:
            warnings.append("sentence without an application identifier")
            continue
        sentence_text[source_id] = as_text(row.get("text"))
        sentences.append(
            _record(
                "sentence",
                source_id,
                document_id,
                _labels(row) or ["Sentence"],
                None,
                _node_properties(row),
                {"query_id": "Q11_sentences", "graph_source": row.get("source")},
                "eligible",
                [] if row.get("text") else ["sentence text is empty"],
                textual_form=as_text(row.get("text")) or None,
                source_annotation_identifier=source_id,
            )
        )

    mentions = []
    seen_mention_ids = set()
    for query_id, layer in (
        ("Q14_entity_mentions", "entity"),
        ("Q15_named_entities", "entity"),
        ("Q18_event_mentions", "event"),
        ("Q25_time_mentions", "time"),
        ("Q32_value_mentions", "value"),
    ):
        for row in results.get(query_id) or []:
            labels = set(_labels(row))
            if "FrameArgument" in labels:
                warnings.append("frame argument returned by a mention query")
                continue
            source_id = as_text(row.get("app_id"))
            if not source_id:
                warnings.append(f"{query_id} row has no application identifier")
                continue
            if source_id in seen_mention_ids:
                continue
            seen_mention_ids.add(source_id)
            surface = _surface(row)
            token_start, token_end, character_start, character_end, convention, notes = _spans(row, surface)
            annotation = as_text(row.get("eid") or row.get("tid") or source_id)
            mentions.append(
                _record(
                    "mention",
                    source_id,
                    document_id,
                    _labels(row),
                    None,
                    _node_properties(row),
                    {"query_id": query_id, "graph_source": row.get("source")},
                    "eligible",
                    notes,
                    textual_form=surface or None,
                    token_start=token_start,
                    token_end=token_end,
                    character_start=character_start,
                    character_end=character_end,
                    span_convention=convention,
                    sentence_identifier=_sentence_for(token_sentence, row.get("start_tok")),
                    generic_type=as_text(row.get("class_code") or row.get("ent_class") or row.get("type_prop")) or None,
                    lemma=as_text(row.get("lemma") or row.get("pred")) or None,
                    source_confidence=_confidence(row.get("confidence")),
                    source_annotation_identifier=annotation,
                    extra={"mention_layer": layer},
                )
            )

    entity_by_mention = {}
    for row in results.get("Q17_entity_refers_to") or []:
        mention_id = as_text(row.get("start_app_id"))
        entity_id = as_text(row.get("end_app_id"))
        if mention_id and entity_id:
            entity_by_mention.setdefault(mention_id, entity_id)
    frame_argument_entity = {}
    for row in results.get("Q37_frame_argument_refers_to") or []:
        argument_id = as_text(row.get("start_app_id"))
        entity_id = as_text(row.get("end_app_id"))
        if argument_id and entity_id:
            frame_argument_entity.setdefault(argument_id, entity_id)

    canonical_entities = []
    for row in results.get("Q16_canonical_entities") or []:
        source_id = as_text(row.get("app_id"))
        if not source_id:
            warnings.append("canonical entity without an application identifier")
            continue
        surface = _surface(row)
        token_start, token_end, character_start, character_end, convention, notes = _spans(row, surface)
        canonical_entities.append(
            _record(
                "canonical_entity",
                source_id,
                document_id,
                _labels(row) or ["Entity"],
                None,
                _node_properties(row),
                {"query_id": "Q16_canonical_entities", "graph_source": row.get("source")},
                "eligible",
                notes,
                textual_form=surface or None,
                token_start=token_start,
                token_end=token_end,
                character_start=character_start,
                character_end=character_end,
                span_convention=convention,
                sentence_identifier=_sentence_for(token_sentence, row.get("start_tok")),
                generic_type=as_text(row.get("ent_class") or row.get("type_prop") or row.get("class_code")) or None,
                source_confidence=_confidence(row.get("confidence")),
                source_annotation_identifier=source_id,
            )
        )

    event_by_mention = {}
    for row in results.get("Q20_event_refers_to") or []:
        mention_id = as_text(row.get("start_app_id"))
        event_eid = as_text(row.get("end_eid"))
        if mention_id and event_eid:
            event_by_mention.setdefault(mention_id, event_eid)
    frame_event = {}
    for row in results.get("Q21_frame_describes_event") or []:
        frame_id = as_text(row.get("frame_id"))
        event_eid = as_text(row.get("event_eid"))
        if frame_id and event_eid:
            frame_event.setdefault(frame_id, event_eid)

    canonical_events = []
    for row in results.get("Q19_canonical_events") or []:
        source_id = as_text(row.get("eid"))
        if not source_id:
            warnings.append("canonical event without eid")
            continue
        surface = _surface(row)
        token_start, token_end, character_start, character_end, convention, notes = _spans(row, surface)
        notes.append("eid is a source annotation identifier")
        canonical_events.append(
            _record(
                "canonical_event",
                source_id,
                document_id,
                _labels(row) or ["TEvent"],
                None,
                _node_properties(row),
                {"query_id": "Q19_canonical_events", "graph_source": row.get("source")},
                "eligible",
                notes,
                textual_form=surface or None,
                token_start=token_start,
                token_end=token_end,
                character_start=character_start,
                character_end=character_end,
                span_convention=convention,
                sentence_identifier=_sentence_for(token_sentence, row.get("start_tok")),
                generic_type=as_text(row.get("class_code") or row.get("type_prop")) or None,
                lemma=as_text(row.get("pred") or row.get("lemma")) or None,
                source_confidence=_confidence(row.get("confidence")),
                source_annotation_identifier=source_id,
            )
        )

    participants = []
    for query_id, layer, eligibility in (
        ("Q22_event_participant", "EVENT_PARTICIPANT", "eligible_primary"),
        ("Q23_has_frame_argument", "HAS_FRAME_ARGUMENT", "eligible_supporting"),
        ("Q24_participant", "PARTICIPANT", "diagnostic_only"),
    ):
        for index, row in enumerate(results.get(query_id) or []):
            start_labels = _labels({"labels": row.get("start_labels")})
            end_labels = _labels({"labels": row.get("end_labels")})
            start_id = as_text(row.get("start_app_id") or row.get("start_eid"))
            end_id = as_text(row.get("end_app_id") or row.get("end_eid") or row.get("end_tid"))
            source_id = f"{layer}:{start_id}:{end_id}:{index}"
            roles = [as_text(row.get(key)) for key in ("role", "raw_role", "type_prop") if row.get(key)]
            notes = []
            if "FrameArgument" in start_labels or "FrameArgument" in end_labels:
                notes.append("endpoint includes a frame argument")
            participants.append(
                _record(
                    "participant",
                    source_id,
                    document_id,
                    sorted(set(start_labels + end_labels)),
                    layer,
                    {
                        "source": row.get("source"),
                        "role": row.get("role"),
                        "raw_role": row.get("raw_role"),
                        "type_prop": row.get("type_prop"),
                        "confidence": row.get("confidence"),
                        "rule_id": row.get("rule_id"),
                        "source_kind": row.get("source_kind"),
                        "start_labels": start_labels,
                        "end_labels": end_labels,
                        "start_app_id": row.get("start_app_id"),
                        "end_app_id": row.get("end_app_id"),
                        "start_eid": row.get("start_eid"),
                        "end_eid": row.get("end_eid"),
                    },
                    {"query_id": query_id, "graph_source": row.get("source")},
                    eligibility,
                    notes,
                    endpoints={"start": start_id, "end": end_id},
                    source_confidence=_confidence(row.get("confidence")),
                    extra={
                        "participant_layer": layer,
                        "supporting_layers": [],
                        "operational_path_count": 1,
                        "source_roles": roles,
                    },
                )
            )

    time_mention_by_tid = {}
    for row in results.get("Q27_time_refers_to") or []:
        mention_id = as_text(row.get("start_app_id"))
        tid = as_text(row.get("end_tid"))
        if mention_id and tid:
            time_mention_by_tid.setdefault(tid, mention_id)

    times = []
    for row in results.get("Q26_time_entities") or []:
        source_id = as_text(row.get("tid") or row.get("app_id"))
        if not source_id:
            warnings.append("time entity without tid or id")
            continue
        surface = _surface(row)
        token_start, token_end, character_start, character_end, convention, notes = _spans(row, surface)
        function = as_text(row.get("function_in_document"))
        eligibility = "eligible_publication_time" if function == "CREATION_TIME" else "eligible"
        if function == "CREATION_TIME":
            notes.append("creation time is publication time")
        times.append(
            _record(
                "time",
                source_id,
                document_id,
                _labels(row) or ["TIMEX"],
                None,
                _node_properties(row),
                {"query_id": "Q26_time_entities", "graph_source": row.get("source")},
                eligibility,
                notes,
                textual_form=surface or None,
                token_start=token_start,
                token_end=token_end,
                character_start=character_start,
                character_end=character_end,
                span_convention=convention,
                generic_type=as_text(row.get("type_prop")) or None,
                source_annotation_identifier=source_id,
                extra={"mention_identifier": time_mention_by_tid.get(source_id)},
            )
        )

    publication_tid = ""
    for row in results.get("Q28_created_on") or []:
        publication_tid = as_text(row.get("tid"))

    temporal_relations = []
    for row in results.get("Q28_created_on") or []:
        source_id = "CREATED_ON:" + as_text(row.get("tid"))
        temporal_relations.append(
            _record(
                "temporal_relation",
                source_id,
                document_id,
                ["AnnotatedText", "TIMEX"],
                "CREATED_ON",
                {key: row.get(key) for key in ("tid", "value", "text", "function_in_document", "type_prop", "source")},
                {"query_id": "Q28_created_on", "graph_source": row.get("source")},
                "eligible_publication_time",
                ["publication time is not an event time"],
                endpoints={"start": document_id, "end": as_text(row.get("tid"))},
                textual_form=as_text(row.get("text") or row.get("value")) or None,
                source_annotation_identifier=as_text(row.get("tid")) or None,
            )
        )

    def _temporal_rows(query_id: str, relationship_type: str, eligibility: str):
        built = []
        for index, row in enumerate(results.get(query_id) or []):
            start_id = as_text(row.get("start_eid") or row.get("start_app_id") or row.get("start_tid"))
            end_id = as_text(row.get("end_tid") or row.get("end_eid") or row.get("end_app_id"))
            source_id = f"{relationship_type}:{start_id}:{end_id}:{index}"
            suppressed = bool(row.get("suppressed"))
            source_kind = as_text(row.get("source_kind")).lower()
            notes = []
            if suppressed:
                notes.append("suppressed temporal link")
            if source_kind in EXPERIMENTAL_SOURCE_KINDS:
                notes.append("temporal link is not explicit")
            built.append(
                _record(
                    "temporal_relation",
                    source_id,
                    document_id,
                    sorted(set(_labels({"labels": row.get("start_labels")}) + _labels({"labels": row.get("end_labels")}))),
                    relationship_type,
                    {
                        "source": row.get("source"),
                        "source_kind": row.get("source_kind"),
                        "rel_type": row.get("rel_type"),
                        "rel_type_original": row.get("rel_type_original"),
                        "rel_type_canonical": row.get("rel_type_canonical"),
                        "status": row.get("status"),
                        "suppressed": row.get("suppressed"),
                        "suppressed_by": row.get("suppressed_by"),
                        "suppression_reason": row.get("suppression_reason"),
                        "confidence": row.get("confidence"),
                        "rule_id": row.get("rule_id"),
                        "start_eid": row.get("start_eid"),
                        "end_tid": row.get("end_tid"),
                        "end_eid": row.get("end_eid"),
                    },
                    {"query_id": query_id, "graph_source": row.get("source")},
                    eligibility,
                    notes,
                    endpoints={"start": start_id, "end": end_id},
                    source_confidence=_confidence(row.get("confidence")),
                    source_annotation_identifier=start_id or None,
                )
            )
        return built

    temporal_relations.extend(_temporal_rows("Q29_has_time_anchor", "HAS_TIME_ANCHOR", "eligible_explicit_event_time"))
    temporal_relations.extend(_temporal_rows("Q30_tlink", "TLINK", "diagnostic_only_not_core"))

    values = []
    value_mention_by_value = {}
    for row in results.get("Q33_value_refers_to") or []:
        mention_id = as_text(row.get("start_app_id"))
        value_id = as_text(row.get("end_app_id"))
        if mention_id and value_id:
            value_mention_by_value.setdefault(value_id, mention_id)
    for row in results.get("Q31_values") or []:
        source_id = as_text(row.get("app_id"))
        if not source_id:
            warnings.append("value without an application identifier")
            continue
        surface = _surface(row)
        token_start, token_end, character_start, character_end, convention, notes = _spans(row, surface)
        values.append(
            _record(
                "value",
                source_id,
                document_id,
                _labels(row) or ["VALUE"],
                None,
                _node_properties(row),
                {"query_id": "Q31_values", "graph_source": row.get("source")},
                "eligible",
                notes,
                textual_form=surface or None,
                token_start=token_start,
                token_end=token_end,
                character_start=character_start,
                character_end=character_end,
                span_convention=convention,
                sentence_identifier=_sentence_for(token_sentence, row.get("start_tok")),
                generic_type=as_text(row.get("type_prop")) or None,
                source_confidence=_confidence(row.get("confidence")),
                source_annotation_identifier=source_id,
                extra={"mention_identifier": value_mention_by_value.get(source_id)},
            )
        )

    evidence = []
    for sentence in sentences:
        evidence.append(
            _record(
                "evidence",
                sentence["source_identifier"],
                document_id,
                ["Sentence"],
                None,
                {"sentence_identifier": sentence["source_identifier"]},
                {"query_id": "Q11_sentences", "graph_source": sentence["provenance"].get("graph_source")},
                "eligible",
                [],
                textual_form=sentence.get("textual_form"),
                sentence_identifier=sentence["source_identifier"],
                source_annotation_identifier=sentence["source_identifier"],
            )
        )

    def _sort(records: list[dict]) -> list[dict]:
        return sorted(records, key=lambda item: (item["record_kind"], item["source_identifier"]))

    frame_argument_count = int((results.get("Q34_frame_argument_count") or [{}])[0].get("frame_argument_count") or 0)
    spacy_only = int((results.get("Q35_spacy_timex_only_count") or [{}])[0].get("spacy_timex_only_count") or 0)
    quality_count = int((results.get("Q36_quality_finding_count") or [{}])[0].get("quality_finding_count") or 0)
    if frame_argument_count:
        warnings.append("frame arguments are excluded from entity-mention records")
    if spacy_only:
        warnings.append("spaCy time candidates without a time mention were not copied")
    if quality_count:
        warnings.append("quality findings were counted and not converted to ontology instances")

    bundle = {
        "document_id": document_id,
        "documents": _sort(documents),
        "sentences": _sort(sentences),
        "tokens": _sort(tokens),
        "mentions": _sort(mentions),
        "canonical_entities": _sort(canonical_entities),
        "canonical_events": _sort(canonical_events),
        "participants": _sort(participants),
        "times": _sort(times),
        "temporal_relations": _sort(temporal_relations),
        "values": _sort(values),
        "evidence": _sort(evidence),
        "warnings": warnings,
        "indexes": {
            "entity_by_mention": entity_by_mention,
            "frame_argument_entity": frame_argument_entity,
            "event_by_mention": event_by_mention,
            "frame_event": frame_event,
            "sentence_text": sentence_text,
            "publication_tid": publication_tid,
            "token_sentence": {str(key): value for key, value in sorted(token_sentence.items())},
        },
        "observed_counts": {
            "frame_argument_count": frame_argument_count,
            "spacy_timex_only_count": spacy_only,
            "quality_finding_count": quality_count,
            "span_probe_rows": len(results.get("Q13_span_probe") or []),
        },
    }
    return as_json(bundle)
