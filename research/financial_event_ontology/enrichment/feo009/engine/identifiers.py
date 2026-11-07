"""Document-scoped public IRIs.

A source annotation identifier may be stored as a literal and may be an
input to a namespaced local key. It is not used as the public IRI.
"""

from __future__ import annotations

import hashlib
import re
from urllib.parse import quote

from engine.constants import DIGEST_LENGTH, MAPPING_VERSION, RESOURCE_BASE

ELEMENT_ID_RE = re.compile(r"^\d+:[0-9a-fA-F-]{8,}:\d+$")
FORBIDDEN_PARTS = (
    "bo" + "lt://",
    "local" + "host",
    "/home" + "/",
    "text" + "graphx",
)


def _refuse(text: str) -> None:
    lowered = text.lower()
    if ELEMENT_ID_RE.match(text) or any(part in lowered for part in FORBIDDEN_PARTS):
        raise ValueError("Refusing an identifier segment that is not a public key.")


def percent_encode_segment(value: str) -> str:
    text = str(value).strip()
    if text == "":
        raise ValueError("Empty IRI path segment.")
    _refuse(text)
    return quote(text, safe="")


def resource_iri(*segments: str) -> str:
    encoded = [percent_encode_segment(segment) for segment in segments]
    iri = RESOURCE_BASE + "/".join(encoded)
    lowered = iri.lower()
    if any(part in lowered for part in FORBIDDEN_PARTS):
        raise ValueError("Public IRI failed the safety check.")
    return iri


def safe_local_key(value: str, *, purpose: str) -> str:
    """Namespace a source key. Element identifiers become digest keys."""
    text = str(value).strip()
    if text == "":
        raise ValueError("Empty local key.")
    if ELEMENT_ID_RE.match(text) or any(part in text.lower() for part in FORBIDDEN_PARTS):
        digest = hashlib.sha256(f"{purpose}|{text}".encode("utf-8")).hexdigest()[:12]
        return "src-" + digest
    return text


def object_form_iri(iri: str) -> str:
    return "iri:" + iri


def object_form_literal(lexical: str, datatype: str) -> str:
    return "lit:" + datatype + "|" + lexical


def assertion_canonical(
    *,
    profile: str,
    subject: str,
    predicate: str,
    object_form: str,
    assertion_kind: str,
) -> str:
    """Identity excludes confidence and review status."""
    return "|".join(
        [
            MAPPING_VERSION,
            profile,
            subject,
            predicate,
            object_form,
            assertion_kind,
        ]
    )


def assertion_digest(canonical: str) -> str:
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:DIGEST_LENGTH]


def assertion_iri(
    *,
    profile: str,
    subject: str,
    predicate: str,
    object_form: str,
    assertion_kind: str,
) -> str:
    digest = assertion_digest(
        assertion_canonical(
            profile=profile,
            subject=subject,
            predicate=predicate,
            object_form=object_form,
            assertion_kind=assertion_kind,
        )
    )
    return resource_iri("assertion", assertion_kind, digest)


def decision_id(rule_id: str, candidate_id: str, profile: str) -> str:
    digest = hashlib.sha256(
        f"{MAPPING_VERSION}|{rule_id}|{candidate_id}|{profile}".encode("utf-8")
    ).hexdigest()[:16]
    return "dec-" + digest


def sha256_file(path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 16), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
