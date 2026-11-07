"""Recalculate headline fractions from the public label tables in this package.

Reviewer free text and the private second-reader directory are not read.
The second-reader agreement tables already stored under evaluation/public
are the calculation inputs.
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FEO013 = ROOT / "research" / "financial_event_ontology" / "evaluation" / "feo013"

EVENT_TASK = "MarketChangeEvent classification"
REL_TASK = "hasAffectedMarket relation extraction"
EVENT_POS = {"correct_market_change"}
EVENT_NEG = {"not_market_change"}
REL_POS = {"correct"}
REL_NEG = {"incorrect", "wrong_participant_type"}

HEADLINES = (
    ("R-EVT-BASE", "baseline event precision", "31/50", "Results, selective materialisation"),
    ("R-EVT-REF", "refined event precision", "25/26", "Results, selective materialisation"),
    ("R-REL-BASE", "baseline affected-market precision", "29/50", "Results, selective materialisation"),
    ("R-REL-REF", "refined affected-market precision", "23/26", "Results, selective materialisation"),
    ("R-EVT-HOLD", "event acceptance retention", "26/50", "Results, selective materialisation"),
    ("R-REL-HOLD", "affected-market acceptance retention", "26/50", "Results, selective materialisation"),
    ("R-EVT-AVAIL", "event candidate availability", "21/24", "Results, candidate availability"),
    ("R-REL-AVAIL", "affected-market candidate availability", "6/19", "Results, candidate availability"),
    ("R-TRIG-EXACT", "exact trigger coverage", "0/27", "Results, component grounding"),
    ("R-TRIG-PART", "exact-or-partial trigger support", "18/27", "Results, component grounding"),
    ("R-ASSERT-ALIGN", "assertion-path alignment", "22/25", "Results, component grounding"),
    ("R-READ-EVT", "second-reader event agreement", "46/50", "Evaluation design, protocol-guided second reading"),
    ("R-READ-REL", "second-reader affected-market agreement", "45/50", "Evaluation design, protocol-guided second reading"),
    ("R-READ-EVID", "second-reader assertion-evidence agreement", "26/27", "Evaluation design, protocol-guided second reading"),
)


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def decision_index(root: Path) -> dict[tuple, list[str]]:
    found: dict[tuple, list[str]] = {}
    for path in sorted((root / "decisions" / "per_document").glob("*/decisions.json")):
        for row in json.loads(path.read_text(encoding="utf-8")):
            key = (row.get("target_local_name"), row.get("document_id"), row.get("candidate_id"))
            found.setdefault(key, []).append(row.get("status"))
    return found


def viewed_rows(post: list[dict]) -> tuple[list[dict], dict]:
    viewed = []
    by_id = {}
    for row in post:
        if row.get("row_origin") != "feo012b_reference_set":
            continue
        by_id[row["review_id"]] = row
        superseded = row.get("eligibility_scope") == "superseded_by_delta_review"
        viewed.append(
            {
                "review_id": row.get("review_id", ""),
                "document_id": row.get("document_id", ""),
                "evaluation_task": row.get("evaluation_task", ""),
                "adjudicated_label": row.get("prior_adjudicated_label", "") if superseded else row.get("evaluation_label", ""),
                "evaluation_inclusion": "excluded" if superseded or row.get("evaluation_eligible") != "true" else "included",
                "system_decision": row.get("system_decision", ""),
            }
        )
    return viewed, by_id


def accepted_precision(viewed, by_id, task, positive, negative) -> tuple[int, int]:
    true_positive = denominator = 0
    for row in viewed:
        if row["evaluation_task"] != task or row["evaluation_inclusion"] != "included":
            continue
        if by_id[row["review_id"]]["system_decision"] != "accepted":
            continue
        if row["adjudicated_label"] not in positive | negative:
            continue
        denominator += 1
        true_positive += row["adjudicated_label"] in positive
    return true_positive, denominator


def transition(viewed, by_id, decisions, task, positive, negative, target) -> dict:
    base = retained = true_positive = unmatched = 0
    for row in viewed:
        if row["evaluation_task"] != task or row["evaluation_inclusion"] != "included":
            continue
        source = by_id[row["review_id"]]
        if source["system_decision"] != "accepted" or row["adjudicated_label"] not in positive | negative:
            continue
        base += 1
        key = (target, source["document_id"], source["corrected_candidate_id"])
        statuses = decisions.get(key) or []
        if len(statuses) != 1:
            unmatched += 1
            continue
        if statuses[0] == "accepted":
            retained += 1
            true_positive += row["adjudicated_label"] in positive
    return {
        "baseline_denominator": base,
        "retained": retained,
        "refined_true_positive": true_positive,
        "refined_denominator": retained,
        "unmatched": unmatched,
    }


def _agreement(rows: list[dict]) -> tuple[int, int]:
    agree = sum(row["second_reader_answer"] == row["expected_answer"] for row in rows)
    return agree, len(rows)


def boundary_checks(public_dir: Path, viewed) -> dict:
    ambiguous = read_csv(public_dir / "ambiguity_register.csv")
    duplicates = read_csv(public_dir / "duplicate_event_register.csv")
    accepted_duplicates = [
        row for row in duplicates
        if row.get("system_decision") == "accepted" and "duplicate" in (row.get("exclusion_reason") or "")
    ]
    included_ids = {row["review_id"] for row in viewed if row["evaluation_inclusion"] == "included"}
    return {
        "ambiguous_assertion_paths": len(ambiguous),
        "ambiguous_ids": [row["review_id"] for row in ambiguous],
        "accepted_duplicate_ids": [row["review_id"] for row in accepted_duplicates],
        "accepted_duplicates_outside_included_view": all(
            row["review_id"] not in included_ids for row in accepted_duplicates
        ),
    }


def calculate(public_dir: Path, refined_decisions: Path) -> list[dict]:
    post = read_csv(public_dir / "frozen_reference_labels.csv")
    viewed, by_id = viewed_rows(post)
    event_base = accepted_precision(viewed, by_id, EVENT_TASK, EVENT_POS, EVENT_NEG)
    rel_base = accepted_precision(viewed, by_id, REL_TASK, REL_POS, REL_NEG)
    refined = decision_index(refined_decisions)
    event_move = transition(viewed, by_id, refined, EVENT_TASK, EVENT_POS, EVENT_NEG, "MarketChangeEvent")
    rel_move = transition(viewed, by_id, refined, REL_TASK, REL_POS, REL_NEG, "hasAffectedMarket")
    if str(FEO013) not in sys.path:
        sys.path.insert(0, str(FEO013))
    import compute_feo013 as metrics

    elicited = read_csv(public_dir / "candidate_availability_register.csv")
    event_recall = metrics.event_recall(viewed, elicited)
    relation = metrics.relation_recall(viewed, elicited, read_csv(public_dir / "market_review.csv"))
    rel_avail = (len(relation["true_positive"]), len(relation["true_positive"]) + len(relation["false_negative"]))
    trigger = Counter(row["human_label"] for row in read_csv(public_dir / "trigger_evidence_labels.csv"))
    assertion = Counter(row["human_label"] for row in read_csv(public_dir / "assertion_evidence_labels.csv"))
    nonambiguous = assertion["correct_answer"] + assertion["incorrect_answer"] + assertion["partially_correct_answer"]
    events = read_csv(public_dir / "second_reader_event_labels.csv")
    markets = read_csv(public_dir / "second_reader_affected_market_labels.csv")
    evidence = read_csv(public_dir / "second_reader_evidence_labels.csv")
    values = {
        "R-EVT-BASE": event_base,
        "R-EVT-REF": (event_move["refined_true_positive"], event_move["refined_denominator"]),
        "R-REL-BASE": rel_base,
        "R-REL-REF": (rel_move["refined_true_positive"], rel_move["refined_denominator"]),
        "R-EVT-HOLD": (event_move["retained"], event_move["baseline_denominator"]),
        "R-REL-HOLD": (rel_move["retained"], rel_move["baseline_denominator"]),
        "R-EVT-AVAIL": (len(event_recall["hits"]), len(event_recall["hits"]) + len(event_recall["misses"])),
        "R-REL-AVAIL": rel_avail,
        "R-TRIG-EXACT": (trigger["correct_answer"], sum(trigger.values())),
        "R-TRIG-PART": (trigger["correct_answer"] + trigger["partially_correct_answer"], sum(trigger.values())),
        "R-ASSERT-ALIGN": (assertion["correct_answer"], nonambiguous),
        "R-READ-EVT": _agreement(events),
        "R-READ-REL": _agreement(markets),
        "R-READ-EVID": _agreement(evidence),
    }
    meta = {item[0]: item for item in HEADLINES}
    rows = []
    for result_id, (numerator, denominator) in values.items():
        name, _expected, section = meta[result_id][1:]
        rows.append(
            {
                "result_id": result_id,
                "name": name,
                "numerator": numerator,
                "denominator": denominator,
                "fraction": f"{numerator}/{denominator}",
                "universe": name,
                "label_view": "primary frozen labels" if not result_id.startswith("R-READ") else "second reading",
                "source_input_file": public_dir.name,
                "inclusion_rule": "evaluation_inclusion=included and the task's positive or negative labels",
                "exclusion_rule": "requires_review and rejected decisions are outside accepted-set precision; ambiguous assertion paths are outside 22/25; the duplicate event is outside U_A",
                "manuscript_location": section,
                "unmatched_event": event_move["unmatched"],
                "unmatched_relation": rel_move["unmatched"],
            }
        )
    rows.append({"boundary": boundary_checks(public_dir, viewed)})
    return rows
