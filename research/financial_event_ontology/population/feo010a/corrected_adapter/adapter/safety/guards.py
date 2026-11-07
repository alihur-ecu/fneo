"""Read-only guards for the approved research graph endpoint.

The password is loaded from the environment or the gitignored research
environment file. This module never prints the password.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.parse import urlparse

APPROVED_URI = "bolt://127.0.0.1:17688"
REJECTED_URIS = {
    "bolt://localhost:7687",
    "bolt://127.0.0.1:7687",
    "neo4j://localhost:7687",
    "neo4j://127.0.0.1:7687",
}
ALLOWED_CALLS = {"db.labels", "db.relationshiptypes"}
WRITE_PATTERNS = (
    r"\bCREATE\b",
    r"\bMERGE\b",
    r"\bDELETE\b",
    r"\bDETACH\b",
    r"\bSET\b",
    r"\bREMOVE\b",
    r"\bDROP\b",
    r"\bLOAD\s+CSV\b",
    r"\bFOREACH\b",
    r"\bCALL\s+apoc\.periodic\b",
    r"\bCALL\s+dbms\b",
    r"\bCREATE\s+INDEX\b",
    r"\bCREATE\s+CONSTRAINT\b",
    r"\bDROP\s+INDEX\b",
    r"\bDROP\s+CONSTRAINT\b",
)
CALL_RE = re.compile(r"\bCALL\s+([A-Za-z0-9_.]+)", re.IGNORECASE)


class EndpointRejected(RuntimeError):
    """The requested graph endpoint is not the approved research endpoint."""


class QueryRejected(RuntimeError):
    """A query is not a reviewed read operation."""


def repo_root() -> Path:
    """Repository root. The corrected adapter is one directory deeper than FEO-010."""
    return Path(__file__).resolve().parents[7]


def assert_approved_endpoint(uri: str) -> str:
    """Accept only bolt://127.0.0.1:17688. Reject the development endpoint."""
    text = (uri or "").strip()
    if not text:
        raise EndpointRejected("The graph URI is empty.")
    lowered = text.rstrip("/")
    if lowered.lower() in {item.lower() for item in REJECTED_URIS}:
        raise EndpointRejected("The development graph URI is rejected.")
    parsed = urlparse(lowered)
    host = (parsed.hostname or "").lower()
    port = parsed.port
    if port == 7687:
        raise EndpointRejected("Port 7687 is rejected.")
    if lowered != APPROVED_URI or host != "127.0.0.1" or port != 17688:
        raise EndpointRejected("The graph URI is not bolt://127.0.0.1:17688.")
    if parsed.scheme != "bolt":
        raise EndpointRejected("The graph URI scheme is not bolt.")
    return APPROVED_URI


def assert_read_only_query(cypher: str, *, allow_unscoped: bool = False, document_parameter: str = "$doc_id") -> None:
    """Reject write clauses and metadata calls outside the allowlist."""
    if not cypher or not str(cypher).strip():
        raise QueryRejected("The query text is empty.")
    text = str(cypher)
    for pattern in WRITE_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            raise QueryRejected("The query contains a rejected write or admin operation.")
    for match in CALL_RE.finditer(text):
        name = match.group(1).lower()
        if name not in ALLOWED_CALLS:
            raise QueryRejected("A metadata procedure is not on the allowlist.")
    if not allow_unscoped and document_parameter not in text:
        raise QueryRejected("A document-scoped query does not bind the document parameter.")


def load_password(env_var: str = "FEO_NEO4J_PASSWORD") -> str:
    """Return the research database password without logging it."""
    current = os.environ.get(env_var, "")
    if current:
        return current
    env_path = repo_root() / "research" / "financial_event_ontology" / "infrastructure" / ".env"
    if not env_path.is_file():
        raise RuntimeError("FEO_NEO4J_PASSWORD is not set and the local environment file is absent.")
    value = ""
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, raw = stripped.split("=", 1)
        if key.strip() == env_var:
            value = raw.strip().strip('"').strip("'")
            break
    if not value or value.startswith("replace-with"):
        raise RuntimeError("FEO_NEO4J_PASSWORD is not set.")
    os.environ[env_var] = value
    return value
