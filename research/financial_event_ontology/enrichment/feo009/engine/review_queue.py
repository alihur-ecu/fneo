"""Review queue. Requires-review decisions are not treated as accepted."""

from __future__ import annotations

import csv
from pathlib import Path


COLUMNS = [
    "candidate_id",
    "candidate_kind",
    "proposed_target",
    "rule_id",
    "confidence",
    "review_reason",
    "evidence_summary",
    "source_document_id",
    "source_annotation_ids",
    "blocking_issue",
    "recommended_action",
    "status",
]


def queue_rows(fixtures: list[dict]) -> list[dict]:
    rows = []
    for fixture in fixtures:
        for decision in fixture.get("decisions") or []:
            if decision.get("status") != "requires_review":
                continue
            rows.append(
                {
                    "candidate_id": decision.get("candidate_id") or "",
                    "candidate_kind": decision.get("candidate_kind") or "",
                    "proposed_target": decision.get("target_local_name") or "",
                    "rule_id": decision.get("rule_id") or "",
                    "confidence": decision.get("confidence") or "",
                    "review_reason": decision.get("manual_review_reason") or "",
                    "evidence_summary": " ".join(decision.get("evidence_satisfied") or [])[:240],
                    "source_document_id": decision.get("document_id") or "",
                    "source_annotation_ids": "|".join(decision.get("source_annotation_ids") or []),
                    "blocking_issue": "|".join(decision.get("blocking_conditions_fired") or []),
                    "recommended_action": "Manual review before any direct domain triple.",
                    "status": "requires_review",
                }
            )
    rows.sort(key=lambda row: (row["rule_id"], row["candidate_id"], row["source_document_id"]))
    return rows


def write_queue(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
