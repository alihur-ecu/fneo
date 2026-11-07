"""Public mention and participation identity for the corrected adapter.

Mention keys follow the FEO-010A policy. They do not include a candidate
identifier, financial class, enrichment rule, confidence, review status,
or RDF profile. Participation keys likewise exclude confidence, review
status, raw path count, and rule identifier.
"""

from __future__ import annotations

import hashlib

from adapter.common import public_key

ADAPTER_VERSION = "feo010a-adapter-0.1.0"
MAPPING_VERSION = "feo009-enrichment-0.1.0"

MENTION_TYPES = {
    "entity": "EntityMention",
    "event": "EventMention",
    "time": "TimeMention",
    "value": "TextualMention",
}


def _digest16(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def textual_form_hash(textual_form: str) -> str:
    return _digest16(textual_form or "")


def mention_material(
    corpus: str,
    document_id: str,
    mention_kind: str,
    source_annotation_id: str | None,
    token_start,
    token_end,
    textual_form: str,
) -> str:
    """Identity material. Character offsets are not required."""
    kind = mention_kind or "mention"
    annotation = (source_annotation_id or "").strip()
    if annotation:
        parts = [corpus, document_id, kind, annotation]
    else:
        parts = [
            corpus,
            document_id,
            kind,
            "" if token_start is None else str(token_start),
            "" if token_end is None else str(token_end),
            textual_form_hash(textual_form or ""),
        ]
    return "|".join(parts)


def mention_local_key(
    corpus: str,
    document_id: str,
    mention_kind: str,
    source_annotation_id: str | None,
    token_start,
    token_end,
    textual_form: str,
) -> str:
    material = mention_material(
        corpus, document_id, mention_kind, source_annotation_id, token_start, token_end, textual_form
    )
    return "mention-" + _digest16(material)


def group_textual_mentions(mentions: list[dict]) -> dict[str, dict]:
    """Map each source mention identifier to one textual-mention identity.

    Source records that share mention kind, token span, and textual form are
    one underlying textual mention. The retained annotation identifier is the
    lexicographic minimum, so the public key stays on an annotation identifier
    when one is present. Records with different spans stay distinct even when
    the surface string is the same.
    """
    groups: dict[tuple, list[dict]] = {}
    for mention in mentions:
        key = (
            mention.get("mention_layer") or "",
            mention.get("token_start"),
            mention.get("token_end"),
            mention.get("textual_form") or "",
        )
        groups.setdefault(key, []).append(mention)
    resolved: dict[str, dict] = {}
    for members in groups.values():
        ordered = sorted(members, key=lambda item: (item.get("source_annotation_identifier") or "", item["source_identifier"]))
        canonical = ordered[0]
        local = mention_local_key(
            "meantime-en-stock",
            canonical.get("document_identifier") or "",
            canonical.get("mention_layer") or "",
            canonical.get("source_annotation_identifier"),
            canonical.get("token_start"),
            canonical.get("token_end"),
            canonical.get("textual_form") or "",
        )
        # Corpus is supplied by the caller through rebinding below when needed.
        for member in ordered:
            resolved[member["source_identifier"]] = {
                "local_key": local,
                "mention_kind": member.get("mention_layer") or "",
                "canonical_annotation_id": canonical.get("source_annotation_identifier") or "",
                "group_size": len(ordered),
                "source_ids": [item["source_identifier"] for item in ordered],
                "token_start": member.get("token_start"),
                "token_end": member.get("token_end"),
                "textual_form": member.get("textual_form") or "",
            }
    return resolved


def bind_mention_groups(mentions: list[dict], corpus: str) -> dict[str, dict]:
    """Same grouping as group_textual_mentions, with an explicit corpus."""
    groups: dict[tuple, list[dict]] = {}
    for mention in mentions:
        key = (
            mention.get("mention_layer") or "",
            mention.get("token_start"),
            mention.get("token_end"),
            mention.get("textual_form") or "",
        )
        groups.setdefault(key, []).append(mention)
    resolved: dict[str, dict] = {}
    for members in groups.values():
        ordered = sorted(
            members,
            key=lambda item: ((item.get("source_annotation_identifier") or ""), item["source_identifier"]),
        )
        canonical = ordered[0]
        local = mention_local_key(
            corpus,
            canonical.get("document_identifier") or "",
            canonical.get("mention_layer") or "",
            canonical.get("source_annotation_identifier"),
            canonical.get("token_start"),
            canonical.get("token_end"),
            canonical.get("textual_form") or "",
        )
        for member in ordered:
            resolved[member["source_identifier"]] = {
                "local_key": local,
                "mention_kind": member.get("mention_layer") or "",
                "canonical_annotation_id": canonical.get("source_annotation_identifier") or "",
                "group_size": len(ordered),
                "source_ids": [item["source_identifier"] for item in ordered],
                "token_start": member.get("token_start"),
                "token_end": member.get("token_end"),
                "character_start": member.get("character_start"),
                "character_end": member.get("character_end"),
                "textual_form": member.get("textual_form") or "",
                "document_id": member.get("document_identifier") or "",
            }
    return resolved


def participation_local_key(
    document_id: str,
    event_source_id: str,
    participant_source_id: str,
    participant_kind: str,
    selected_relation: str,
    mapping_version: str = MAPPING_VERSION,
) -> str:
    """Deterministic participation key.

    Inputs are document, canonical event source identity, canonical participant
    source identity, participant candidate kind, selected relation, and mapping
    version. Confidence, review status, raw path count, and rule identifier
    are not inputs.
    """
    material = "|".join(
        [
            document_id,
            event_source_id,
            participant_source_id,
            participant_kind,
            selected_relation,
            mapping_version,
        ]
    )
    return public_key("participation", document_id, material)


def feo010_mention_local_key(document_id: str, source_mention_id: str) -> str:
    """Reproduce the FEO-010 representative mention key. Not used for new IRIs."""
    return public_key("mention", document_id, source_mention_id)
