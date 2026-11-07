"""FEO-013 limited baseline evaluation.

Reads the FEO-012B reference set and the preserved FEO-011 reports.
Does not contact a database, run a language model, rerun shapes, or
report F1, corpus recall, or competency-question answer correctness.
"""

from __future__ import annotations

import csv
import json
import re
import subprocess
from collections import Counter
from pathlib import Path

FEO = Path(__file__).resolve().parents[2]
REPO = FEO.parents[1]
OUT = Path(__file__).resolve().parent
REF = FEO / "review/feo012b/reference_set/feo012b_reference_set.csv"
ELICITED = FEO / "review/feo012b/evaluation_scope/elicited_primary_outcomes.csv"
MARKET_REVIEW = FEO / "review/feo012/review_forms/completed/affected_market_review.csv"
VALUE_REVIEW = FEO / "review/feo012/review_forms/completed/value_review.csv"
EVENT_REVIEW = FEO / "review/feo012/review_forms/completed/market_change_event_review.csv"
TEMPORAL_REVIEW = FEO / "review/feo012/review_forms/completed/temporal_review_sample.csv"
SHACL_OUTCOMES = FEO / "review/feo012b/adjudication/shacl_exception_outcomes.csv"
SHACL_REPORT = FEO / "population/feo011/validation/consolidated_shacl_report.md"
COVERAGE = FEO / "population/feo011/evaluation/population_coverage.csv"
CQ_CATALOGUE = FEO / "competency_questions/accepted_competency_questions.csv"
CQ_PREVIEW = FEO / "population/feo011/competency_questions/results/cq_preview_results.csv"

ADDENDUM_ROWS = ("FEO012-MKT-0008", "FEO012-MKT-0110", "FEO012-MKT-0113")
COLLISION_REASON = "identifier_collision_review_package_defect"
EVENT_POSITIVE = {"correct_market_change"}
EVENT_NEGATIVE = {"not_market_change"}
RELATION_POSITIVE = {"correct", "missing_relation"}
RELATION_NEGATIVE = {"incorrect", "wrong_participant_type"}
VALID_ELICITED = {
    "valid_reference_event_via_matched_row",
    "valid_reference_event_confirmed_by_researcher",
    "valid_reference_event_alignment_rejected",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict]) -> None:
    header = list(rows[0])
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def rate(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return ""
    return f"{numerator / denominator:.4f}"


def metric(
    metric_id: str,
    name: str,
    numerator,
    denominator,
    inclusion_rule: str,
    exclusions: str,
    limitation: str,
    universe: str,
    refused: str = "",
) -> dict:
    numeric_num = numerator if isinstance(numerator, int) else ""
    numeric_den = denominator if isinstance(denominator, int) else ""
    return {
        "metric_id": metric_id,
        "metric_name": name,
        "numerator": "" if numerator is None else numerator,
        "denominator": "" if denominator is None else denominator,
        "rate": rate(numeric_num, numeric_den) if isinstance(numeric_num, int) and isinstance(numeric_den, int) else "",
        "universe": universe,
        "inclusion_rule": inclusion_rule,
        "exclusions": exclusions,
        "limitation": limitation,
        "refused": refused,
    }


def precision_block(rows: list[dict], positive: set[str], negative: set[str]) -> dict:
    included = [row for row in rows if row["evaluation_inclusion"] == "included"]
    accepted = [row for row in included if row["system_decision"] == "accepted"]
    scored = [row for row in accepted if row["adjudicated_label"] in positive | negative]
    true_positive = [row for row in scored if row["adjudicated_label"] in positive]
    false_positive = [row for row in scored if row["adjudicated_label"] in negative]
    excluded = [row for row in rows if row["evaluation_inclusion"] == "excluded"]
    not_accepted = [row for row in included if row["system_decision"] != "accepted"]
    return {
        "true_positive": true_positive,
        "false_positive": false_positive,
        "excluded": excluded,
        "not_accepted_included": not_accepted,
        "exclusion_counts": Counter(row["exclusion_reason"].split(":")[0] for row in excluded),
        "not_accepted_counts": Counter(row["system_decision"] for row in not_accepted),
    }


def exclusion_text(counts: Counter) -> str:
    if not counts:
        return "none"
    return "; ".join(f"{count} {name}" for name, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def event_recall(reference: list[dict], elicited: list[dict]) -> dict:
    by_id = {row["review_id"]: row for row in reference}
    hits, misses, excluded = [], [], []
    for event in elicited:
        status = event["reference_status"]
        if status not in VALID_ELICITED:
            excluded.append(event)
            continue
        record = {"elicited_id": event["elicited_id"], "system_outcome": event["system_outcome"], "reference_status": status}
        if event["system_outcome"] == "system_candidate_exists":
            hits.append(record)
        elif event["system_outcome"] == "false_negative":
            misses.append(record)
        else:
            excluded.append(event)
    derived = [row["review_id"] for row in reference if row["system_decision"] == "no_marketchangeevent_decision"]
    return {"hits": hits, "misses": misses, "excluded": excluded, "derived_review_ids": derived, "by_id": by_id}


def relation_recall(reference: list[dict], elicited: list[dict], market_review: list[dict]) -> dict:
    review = {row["review_id"]: row for row in market_review}
    matched: dict[str, str] = {}
    for event in elicited:
        if event["reference_status"] not in VALID_ELICITED:
            continue
        for review_id in event["matched_event_review_ids"].split("|"):
            if review_id:
                matched[review_id] = event["elicited_id"]
    true_positive, false_negative, left_out = [], [], []
    for row in reference:
        if row["evaluation_task"] != "hasAffectedMarket relation extraction":
            continue
        source = review[row["review_id"]]
        if row["evaluation_inclusion"] != "included":
            if source["population_key"].startswith("gap|") or row["review_id"] in ADDENDUM_ROWS:
                left_out.append(row)
            continue
        if row["adjudicated_label"] == "missing_relation" and source["population_key"].startswith("gap|"):
            false_negative.append(row)
        elif row["adjudicated_label"] == "correct" and source["event_review_id"] in matched:
            true_positive.append(row)
    return {
        "true_positive": true_positive,
        "false_negative": false_negative,
        "left_out": left_out,
        "matched_events": matched,
    }


def event_time_on_market_change(reference: list[dict], event_review: list[dict], temporal_review: list[dict]) -> int:
    labels = {row["review_id"]: row["adjudicated_label"] for row in reference}
    by_source = {(row["document_id"], row["source_event_id"]): row["review_id"] for row in event_review}
    temporal = {row["review_id"]: row for row in temporal_review}
    count = 0
    for row in reference:
        if row["evaluation_task"] != "explicit event-time anchoring":
            continue
        source = temporal[row["review_id"]]
        match = re.match(r"HAS_TIME_ANCHOR:([^:]+):", source.get("population_identifier", ""))
        event_id = by_source.get((row["document_id"], match.group(1))) if match else None
        if event_id and labels.get(event_id) == "correct_market_change":
            count += 1
    return count


def parse_shacl(text: str) -> dict:
    def grab(label: str) -> str:
        match = re.search(rf"^{re.escape(label)}: (.+)$", text, flags=re.M)
        if not match:
            raise SystemExit(f"missing SHACL field {label}")
        return match.group(1).strip()

    return {
        "engine": grab("Engine"),
        "core_conforms": grab("Core conforms"),
        "core_violations": int(grab("Core violations")),
        "core_warnings": int(grab("Core warnings")),
        "core_information": int(grab("Core information results")),
        "extension_conforms": grab("Extension conforms"),
        "extension_violations": int(grab("Extension violations")),
    }


def git_facts() -> dict:
    def run(*args: str) -> str:
        return subprocess.check_output(["git", *args], cwd=REPO, text=True).strip()

    return {"branch": run("rev-parse", "--abbrev-ref", "HEAD"), "commit": run("rev-parse", "HEAD")}


def assemble() -> dict:
    reference = read_csv(REF)
    elicited = read_csv(ELICITED)
    market_review = read_csv(MARKET_REVIEW)
    value_review = {row["review_id"]: row for row in read_csv(VALUE_REVIEW)}
    event_review = read_csv(EVENT_REVIEW)
    temporal_review = read_csv(TEMPORAL_REVIEW)
    shacl_rows = read_csv(SHACL_OUTCOMES)
    shacl = parse_shacl(SHACL_REPORT.read_text(encoding="utf-8"))
    coverage = read_csv(COVERAGE)
    catalogue = read_csv(CQ_CATALOGUE)
    preview = read_csv(CQ_PREVIEW)

    by_task: dict[str, list[dict]] = {}
    for row in reference:
        by_task.setdefault(row["evaluation_task"], []).append(row)

    index_p = precision_block(by_task["MarketIndex typing"], {"correct"}, {"incorrect"})
    equity_p = precision_block(by_task["EquityMarket typing"], {"correct"}, {"incorrect"})
    event_p = precision_block(by_task["MarketChangeEvent classification"], EVENT_POSITIVE, EVENT_NEGATIVE)
    relation_p = precision_block(by_task["hasAffectedMarket relation extraction"], {"correct"}, RELATION_NEGATIVE)
    events = event_recall(reference, elicited)
    relations = relation_recall(reference, elicited, market_review)

    collision = [row for row in reference if row["exclusion_reason"].split(":")[0] == COLLISION_REASON]
    evidence = by_task["evidence correctness"]
    evidence_in = [row for row in evidence if row["evaluation_inclusion"] == "included"]
    evidence_counts = Counter(row["adjudicated_label"] for row in evidence_in)
    values = by_task["value typing"]
    strata = Counter()
    stratum_correct = Counter()
    for row in values:
        stratum = value_review[row["review_id"]]["stratum"]
        strata[stratum] += 1
        if row["adjudicated_label"] == "correct_type_and_value":
            stratum_correct[stratum] += 1
    value_labels = Counter(row["adjudicated_label"] for row in values)
    anchors = by_task["explicit event-time anchoring"]
    orders = by_task["event-order temporal relations"]
    anchor_on_change = event_time_on_market_change(reference, event_review, temporal_review)

    proposed_core = [row for row in catalogue if row["status"] == "proposed_core"]
    preview_supported = [row for row in preview if row["population_supported"] == "true"]
    preview_unsupported = [row for row in preview if row["population_supported"] != "true"]
    coverage_by_name = {row["target_class_or_property"]: row for row in coverage}

    return {
        "reference_rows": len(reference),
        "eligible": sum(1 for row in reference if row["evaluation_inclusion"] == "included"),
        "excluded": sum(1 for row in reference if row["evaluation_inclusion"] == "excluded"),
        "index_p": index_p,
        "equity_p": equity_p,
        "event_p": event_p,
        "relation_p": relation_p,
        "events": events,
        "relations": relations,
        "collision": collision,
        "evidence_in": evidence_in,
        "evidence_counts": evidence_counts,
        "evidence_excluded": exclusion_text(Counter(row["exclusion_reason"].split(":")[0] for row in evidence if row["evaluation_inclusion"] == "excluded")),
        "values": values,
        "strata": strata,
        "stratum_correct": stratum_correct,
        "value_labels": value_labels,
        "anchors": anchors,
        "anchor_labels": Counter(row["adjudicated_label"] for row in anchors),
        "anchor_on_change": anchor_on_change,
        "orders": orders,
        "order_system": Counter(row["system_decision"] for row in orders),
        "shacl": shacl,
        "shacl_rows": shacl_rows,
        "coverage_by_name": coverage_by_name,
        "by_task": by_task,
        "proposed_core": proposed_core,
        "preview": preview,
        "preview_supported": preview_supported,
        "preview_unsupported": preview_unsupported,
        "addendum": [row for row in reference if row["review_id"] in ADDENDUM_ROWS],
        "value_queue": [row for row in reference if row["review_id"] in {"FEO012-VAL-0119", "FEO012-VAL-0121"}],
    }


def metric_rows(data: dict) -> list[dict]:
    rows = []
    precision_universe = "accepted system decisions in the included reference rows; not the elicited-event universe"
    recall_note = "Different universe from precision. Not corpus recall. No F1 is calculated."

    def add_precision(metric_id, name, block, task_rows):
        numerator = len(block["true_positive"])
        denominator = numerator + len(block["false_positive"])
        withheld = exclusion_text(block["not_accepted_counts"])
        rows.append(metric(
            metric_id, name, numerator, denominator,
            "Included rows with system_decision accepted and an adjudicated label in the positive or negative set. "
            "Numerator: adjudicated positive. Denominator: adjudicated positive or negative.",
            f"Task exclusions: {exclusion_text(block['exclusion_counts'])}. "
            f"Included rows that are not accepted decisions, kept out of this denominator: {withheld}.",
            "Precision is over accepted decisions only. Requires-review and rejected decisions are not positive predictions. "
            f"{len(task_rows)} review units in the task.",
            precision_universe,
        ))

    add_precision("market_index_precision", "MarketIndex precision", data["index_p"], data["by_task"]["MarketIndex typing"])
    add_precision("equity_market_precision", "EquityMarket precision", data["equity_p"], data["by_task"]["EquityMarket typing"])
    add_precision("market_change_event_precision", "MarketChangeEvent precision", data["event_p"], data["by_task"]["MarketChangeEvent classification"])
    hits, misses = data["events"]["hits"], data["events"]["misses"]
    rows.append(metric(
        "market_change_event_scoped_recall",
        "MarketChangeEvent scoped recall",
        len(hits), len(hits) + len(misses),
        "Denominator: elicited primary events whose reference status is valid. "
        "Numerator: those events whose system outcome is system_candidate_exists. "
        "A requires-review candidate that the reference confirms counts as found here.",
        f"{len(data['events']['excluded'])} elicited event excluded (ambiguous, not scored). "
        "Identifier-collision rows are not in this denominator.",
        recall_note + " The precision denominator is the accepted MarketChangeEvent decisions, not these 25 events.",
        "25 elicited primary events, after the ambiguous exclusion",
    ))
    add_precision(
        "has_affected_market_precision",
        "hasAffectedMarket precision",
        data["relation_p"],
        data["by_task"]["hasAffectedMarket relation extraction"],
    )
    found, missed = data["relations"]["true_positive"], data["relations"]["false_negative"]
    rows.append(metric(
        "has_affected_market_scoped_recall",
        "hasAffectedMarket scoped recall",
        len(found), len(found) + len(missed),
        "Denominator: included positive relation references tied to the elicited primary events. "
        "A positive reference is either an included gap row labelled missing_relation, or an included correct "
        "system relation whose event row is a matched elicited event. Numerator: the correct system relations in that set.",
        exclusion_text(Counter(row["exclusion_reason"].split(":")[0] for row in data["relations"]["left_out"]))
        + ". The three unnamed-index gap rows are in this exclusion and are not false negatives. "
        "Correct relations on events outside the elicited set are not in this denominator.",
        recall_note + " The precision denominator is every accepted hasAffectedMarket decision, not this elicited relation reference.",
        "elicited-event relation reference",
    ))

    evidence_n = len(data["evidence_in"])
    for metric_id, name, label in (
        ("evidence_exact_rate", "evidence exact-support rate", "exact_support"),
        ("evidence_partial_rate", "evidence partial-support rate", "partial_support"),
        ("evidence_incorrect_or_insufficient_rate", "evidence incorrect or insufficient rate", "invalid_span"),
    ):
        rows.append(metric(
            metric_id, name, data["evidence_counts"][label], evidence_n,
            "Included evidence rows, which are the rows whose assertion was judged correct. "
            "This is a share of support labels, not precision.",
            data["evidence_excluded"] + ". insufficient_support and wrong_evidence fall in that exclusion because the assertion was not judged correct.",
            "Not precision and not F1. The rate is not projected beyond the assessed assertions.",
            "included evidence rows",
        ))

    for stratum in sorted(data["strata"]):
        rows.append(metric(
            "value_" + re.sub(r"[^a-z0-9]+", "_", stratum.lower()).strip("_"),
            f"value-typing correctness ({stratum})",
            data["stratum_correct"][stratum], data["strata"][stratum],
            "Included value rows in this stratum. Numerator: adjudicated correct_type_and_value.",
            "No value row is excluded from the sample.",
            "Sample or stratum correctness only. Not corpus recall and not F1. "
            "The two percentage parse-failure rows stay correct_type_wrong_value.",
            f"value sample stratum {stratum}",
        ))
    rows.append(metric(
        "value_sample_correct_type_and_value",
        "value-typing correctness (whole sample)",
        data["value_labels"]["correct_type_and_value"], len(data["values"]),
        "All included value rows. Numerator: correct_type_and_value.",
        "none",
        "The value table is a stratified selection. This rate is not corpus recall.",
        "value sample",
    ))

    for task, task_rows in data["by_task"].items():
        if task in {"CQ answer correctness"}:
            continue
        included = sum(1 for row in task_rows if row["evaluation_inclusion"] == "included")
        rows.append(metric(
            "reference_coverage_" + re.sub(r"[^a-z0-9]+", "_", task.lower()).strip("_"),
            f"reference coverage ({task})",
            included, len(task_rows),
            "Numerator: rows included in the task denominator. Denominator: review units of the task, including derived units when the task has them.",
            exclusion_text(Counter(row["exclusion_reason"].split(":")[0] for row in task_rows if row["evaluation_inclusion"] == "excluded")),
            "Coverage of the reference set, not correctness and not corpus coverage.",
            "FEO-012B reference units",
        ))
    for name in ("MarketIndex", "EquityMarket", "MarketChangeEvent", "hasAffectedMarket", "hasEventTime", "NumericalValue", "PercentageValue"):
        source = data["coverage_by_name"][name]
        rows.append(metric(
            "population_coverage_" + name,
            f"population coverage ({name})",
            int(source["document_coverage"]), 30,
            "Copied from the preserved FEO-011 population-coverage table. Numerator: documents in which the class or property was populated. Denominator: 30 corpus documents.",
            f"accepted={source['accepted_count']}; review={source['review_count']}; rejected={source['rejected_count']}; rdf_materialised={source['rdf_materialised']}.",
            "Coverage is not correctness. The population table was written before these reference labels and is not recomputed here.",
            "FEO-011 population inventory",
        ))

    rows.append(metric(
        "shacl_core_violations_release_eligible",
        "SHACL core violations on the release-eligible graph",
        data["shacl"]["core_violations"], None,
        "Read from the preserved consolidated SHACL report. The release-eligible graph is the graph after the six violating documents were left out.",
        "Six documents with a core violation are outside this graph. Shapes were not rerun.",
        f"Engine: {data['shacl']['engine']}. Core conforms: {data['shacl']['core_conforms']}. "
        f"Warnings: {data['shacl']['core_warnings']}. Information results: {data['shacl']['core_information']}. "
        "Warnings are not violations. pySHACL was not available to the original report.",
        "release-eligible consolidated graph",
    ))
    cause_counts = Counter(row["researcher_root_cause"] for row in data["shacl_rows"])
    rows.append(metric(
        "shacl_exception_documents",
        "SHACL exception documents",
        len(data["shacl_rows"]), 30,
        "One preserved exception outcome per document that the FEO-011 register excluded from the release-eligible graph.",
        exclusion_text(cause_counts) + ". affects_system_metric is false on every exception, so these rows do not enter the decision metrics.",
        "Case-level outcomes from the resolution queue. Shapes, rules, the population adapter, and RDF were not changed and shapes were not rerun.",
        "six exception outcomes plus the exception register",
    ))

    rows.append(metric(
        "event_time_explicit_and_correct",
        "explicit event-time anchors described as explicit and correct",
        data["anchor_labels"]["explicit_and_correct"], len(data["anchors"]),
        "All 24 sampled explicit-anchor rows. The system decision on every row is absent: no accepted hasEventTime decision is in the sample.",
        "none in this sample",
        f"Descriptive sample only. {data['anchor_on_change']} of the 24 anchors sit on an event the reference labels correct_market_change. "
        "No precision, recall, or F1. Not corpus recall.",
        "event-time sample",
    ))
    rows.append(metric(
        "event_order_rows_without_ordering_text",
        "event-order rows held out of scoring",
        len(data["orders"]), len(data["orders"]),
        "Every event-order row. Each adjudicated label is no_relation_supported because the review form showed identifiers rather than ordering text.",
        exclusion_text(Counter(row["exclusion_reason"].split(":")[0] for row in data["orders"])),
        f"Descriptive only. System inventory: {exclusion_text(data['order_system'])}. "
        "Relations are predicted, not gold. No optional temporal model was scored. No precision, recall, or F1.",
        "event-order sample",
    ))
    rows.append(metric(
        "cq_proposed_core_questions",
        "proposed core competency questions",
        len(data["proposed_core"]), len(data["proposed_core"]),
        "Questions with status proposed_core in the competency-question catalogue. This count is the size of that set, not a correctness score.",
        "Questions with another status are not in the numerator.",
        "Population support is reported separately. Answer correctness is not evaluated.",
        "competency-question catalogue",
    ))
    rows.append(metric(
        "cq_preview_population_supported",
        "competency-question previews with population support",
        len(data["preview_supported"]), len(data["preview"]),
        "Preserved FEO-011 preview rows whose population_supported flag is true. The flag means the queried classes or properties returned rows, not that the answers are correct.",
        "Previews with population_supported false: " + ", ".join(row["cq_id"] for row in data["preview_unsupported"]) + ".",
        "Every preview row records that manual correctness was not evaluated. This evaluation does not score answers.",
        "FEO-011 competency-question preview",
    ))
    rows.append(metric(
        "identifier_collision_rows_excluded",
        "identifier-collision rows excluded from scoring",
        len(data["collision"]), len(data["collision"]),
        "Rejected-sample rows whose exclusion reason is the identifier-collision defect. They are counted here so they are not left unmarked.",
        "These rows are not true negatives and not false negatives.",
        "One candidate identifier and one decision identifier were reused across documents. The rows are an adapter defect, not reference misses.",
        "rejected-sample collision group",
    ))
    for metric_id, name, limitation in (
        ("f1_refused", "F1", "Precision and scoped recall use different universes, so F1 is not calculated."),
        ("corpus_recall_refused", "corpus recall", "Untyped mentions and unreviewed market-change events are not enumerated. Recall is scoped to the elicited reference."),
        ("cq_answer_correctness_refused", "competency-question answer correctness", "No answer was judged correct or incorrect in this evaluation."),
    ):
        rows.append(metric(metric_id, name, None, None, "not scored", "the whole corpus or answer set", limitation, "not a scored universe", refused="yes"))
    return rows


def render_markdown(data: dict, metrics: list[dict], git: dict) -> str:
    by_id = {row["metric_id"]: row for row in metrics}

    def line(metric_id: str) -> str:
        row = by_id[metric_id]
        return f"{row['numerator']}/{row['denominator']} ({row['rate']})"

    causes = Counter(row["researcher_root_cause"] for row in data["shacl_rows"])
    anchor_labels = ", ".join(f"{count} {label}" for label, count in sorted(data["anchor_labels"].items()))
    core_lines = []
    for question in data["proposed_core"]:
        core_lines.append(
            f"| {question['cq_id']} | {question['required_concepts_placeholder']} | {question['required_relations_placeholder']} |"
        )
    population_lines = []
    for name in ("FinancialNewsDocument", "TextualEvidence", "TimeEntity", "MarketIndex", "EquityMarket", "MarketChangeEvent", "NumericalValue", "PercentageValue", "hasAffectedMarket", "hasEventTime", "hasPublicationTime"):
        source = data["coverage_by_name"].get(name)
        if source is None:
            continue
        population_lines.append(
            f"| {name} | {source['rdf_materialised']} | {source['accepted_count']} | {source['document_coverage']} |"
        )
    addendum = ", ".join(
        f"{row['review_id']} ({row['adjudicated_label']}, {row['evaluation_inclusion']})" for row in data["addendum"]
    )
    return "\n".join([
        "# FEO-013 limited evaluation",
        "",
        "Date: 2026-10-31. Experiment: FEO-013. Branch: " + git["branch"] + ". Commit: `" + git["commit"] + "`.",
        "",
        "This is a limited baseline over the single-researcher reference set and the preserved decisions of the ontology population pipeline. "
        "The gate of that reference set remains READY_FOR_LIMITED_EVALUATION. No figure here upgrades it.",
        "",
        "Precision and scoped recall use different universes. Beside every recall figure, the precision universe is the set of accepted system decisions, and the recall universe is the elicited reference named in that figure. F1 is not calculated. Corpus recall is not calculated. Competency-question answers are not judged.",
        "",
        "## MarketIndex precision",
        "",
        f"Result: {line('market_index_precision')}.",
        "",
        f"Inclusion: {by_id['market_index_precision']['inclusion_rule']}",
        "",
        f"Exclusions: {by_id['market_index_precision']['exclusions']}",
        "",
        f"Limitation: {by_id['market_index_precision']['limitation']}",
        "",
        "## EquityMarket precision",
        "",
        f"Result: {line('equity_market_precision')}.",
        "",
        f"Inclusion: {by_id['equity_market_precision']['inclusion_rule']}",
        "",
        f"Exclusions: {by_id['equity_market_precision']['exclusions']}",
        "",
        f"Limitation: {by_id['equity_market_precision']['limitation']}",
        "",
        "## MarketChangeEvent precision",
        "",
        f"Result: {line('market_change_event_precision')}.",
        "",
        f"Inclusion: {by_id['market_change_event_precision']['inclusion_rule']}",
        "",
        f"Exclusions: {by_id['market_change_event_precision']['exclusions']}",
        "",
        f"Limitation: {by_id['market_change_event_precision']['limitation']}",
        "",
        "## MarketChangeEvent scoped recall",
        "",
        f"Result: {line('market_change_event_scoped_recall')}. This is not corpus recall. The precision figure above uses accepted MarketChangeEvent decisions; this recall uses the 25 elicited primary events. The two denominators are not combined.",
        "",
        f"Inclusion: {by_id['market_change_event_scoped_recall']['inclusion_rule']}",
        "",
        f"Exclusions: {by_id['market_change_event_scoped_recall']['exclusions']}",
        "",
        f"Limitation: {by_id['market_change_event_scoped_recall']['limitation']}",
        "",
        "## hasAffectedMarket precision",
        "",
        f"Result: {line('has_affected_market_precision')}. Wrong participant type is a negative in this denominator.",
        "",
        f"Inclusion: {by_id['has_affected_market_precision']['inclusion_rule']}",
        "",
        f"Exclusions: {by_id['has_affected_market_precision']['exclusions']}",
        "",
        f"Limitation: {by_id['has_affected_market_precision']['limitation']}",
        "",
        "## hasAffectedMarket scoped recall",
        "",
        f"Result: {line('has_affected_market_scoped_recall')}. This is not corpus recall. Precision above is over accepted relation decisions. This recall is over the elicited-event relation reference only. The two denominators are not combined.",
        "",
        f"Inclusion: {by_id['has_affected_market_scoped_recall']['inclusion_rule']}",
        "",
        f"Exclusions: {by_id['has_affected_market_scoped_recall']['exclusions']}",
        "",
        f"Limitation: {by_id['has_affected_market_scoped_recall']['limitation']}",
        "",
        "The three addendum rows are " + addendum + ". Each passage names an unnamed plural index descriptor, which is outside the range of hasAffectedMarket, so missing_relation was not preserved. They are excluded from this recall and are not false negatives.",
        "",
        "## Evidence correctness",
        "",
        f"Exact: {line('evidence_exact_rate')}. Partial: {line('evidence_partial_rate')}. Incorrect or insufficient: {line('evidence_incorrect_or_insufficient_rate')}.",
        "",
        "These are shares of the included evidence rows. They are not precision and not F1. "
        f"Exclusions: {by_id['evidence_exact_rate']['exclusions']}",
        "",
        "## Value-typing correctness",
        "",
        f"Whole sample: {line('value_sample_correct_type_and_value')}. This is stratum and sample correctness, not corpus recall.",
        "",
        "By stratum, numerator correct_type_and_value over the stratum size:",
        "",
        "| stratum | correct_type_and_value | stratum size |",
        "| --- | --- | --- |",
        *[
            f"| {stratum} | {data['stratum_correct'][stratum]} | {data['strata'][stratum]} |"
            for stratum in sorted(data["strata"])
        ],
        "",
        "FEO012-VAL-0119 and FEO012-VAL-0121 remain correct_type_wrong_value. The stored magnitudes 826 and 1466 do not match the decimal-comma surfaces 8,26% and 14,66%. Those two queue decisions were not reopened.",
        "",
        "## Coverage",
        "",
        "Reference coverage is the share of each task's review units that remain in the scoring denominator. It is not a correctness rate.",
        "",
        "Population coverage below is copied from the preserved population-coverage table of the ontology population pipeline. It counts documents and materialised records. It is not correctness, and it was not recomputed from the reference labels.",
        "",
        "| class or property | materialised | accepted records | documents |",
        "| --- | --- | --- | --- |",
        *population_lines,
        "",
        "## SHACL conformance",
        "",
        f"Scope: the release-eligible consolidated graph in the preserved FEO-011 report. Engine: {data['shacl']['engine']}. "
        f"Core conforms: {data['shacl']['core_conforms']}. Core violations: {data['shacl']['core_violations']}. "
        f"Core warnings: {data['shacl']['core_warnings']}. Core information results: {data['shacl']['core_information']}. "
        f"Extension conforms: {data['shacl']['extension_conforms']}. Extension violations: {data['shacl']['extension_violations']}.",
        "",
        "Shapes were not rerun. Warnings are not counted as violations. The report states that an independent SHACL engine was not available.",
        "",
        f"Six documents are outside that graph: {', '.join(row['document_id'] for row in data['shacl_rows'])}. "
        f"Causes: {exclusion_text(causes)}. Each exception has affects_system_metric false, so the decision metrics above do not drop those documents' reviewed rows for this reason. "
        "Three exceptions are one textual mention denoting two resources. Three are two time records receiving one covering mention.",
        "",
        "## Temporal findings",
        "",
        f"Explicit event-time sample: {len(data['anchors'])} rows. Label counts: {anchor_labels}. "
        f"Every system decision in the sample is absent, so there is no accepted hasEventTime anchor to score. "
        f"{data['anchor_on_change']} of the 24 anchors are on an event labelled correct_market_change. "
        "These counts describe the sample. They are not precision, recall, or F1, and they are not corpus recall.",
        "",
        f"Event order: {len(data['orders'])} rows, all excluded because the review form did not show ordering text. "
        f"Every adjudicated label is no_relation_supported. System inventory: {exclusion_text(data['order_system'])}. "
        "The relations are predicted, not gold. No optional temporal model was scored, and no relation vocabulary was normalised for a metric.",
        "",
        "## Competency-question population support",
        "",
        "This section records whether the classes and properties named by the competency questions are present in the population. It does not record whether an answer is correct.",
        "",
        f"The catalogue holds {len(data['proposed_core'])} questions with status proposed_core. Their placeholders for required concepts and relations are:",
        "",
        "| question | concepts | relations |",
        "| --- | --- | --- |",
        *core_lines,
        "",
        f"The preserved preview marks population support on {len(data['preview_supported'])} of {len(data['preview'])} queries. "
        f"Queries without population support: {', '.join(row['cq_id'] for row in data['preview_unsupported'])}. "
        "FCQ-009 asks for a direct hasEventTime link; the population table shows that property with no accepted record. "
        "Every preview row states that manual correctness was not evaluated. Answer correctness is refused in this experiment.",
        "",
        "## Identifier collision",
        "",
        f"{len(data['collision'])} rejected-sample rows share one candidate identifier. They are excluded. They are not true negatives and not false negatives.",
        "",
        "## What was not calculated",
        "",
        "F1 was not calculated. Corpus recall was not calculated. Competency-question answer correctness was not calculated. No language model was used. No database was queried. Shapes were not rerun.",
        "",
    ]) + "\n"


def manifest(data: dict, metrics: list[dict], git: dict) -> dict:
    return {
        "experiment_id": "FEO-013",
        "date": "2026-10-31",
        "branch": git["branch"],
        "commit": git["commit"],
        "corpus": "English stock-market subset used by the preserved population run",
        "reference_set": "research/financial_event_ontology/review/feo012b/reference_set/feo012b_reference_set.csv",
        "reference_rows": data["reference_rows"],
        "evaluation_eligible_rows": data["eligible"],
        "excluded_rows": data["excluded"],
        "gate": "READY_FOR_LIMITED_EVALUATION",
        "optional_modules_enabled": [],
        "model_version": "no language model",
        "random_seed": "not applicable",
        "commands": [
            "PYTHONDONTWRITEBYTECODE=1 python research/financial_event_ontology/evaluation/feo013/compute_feo013.py",
            "PYTHONDONTWRITEBYTECODE=1 python -m pytest research/financial_event_ontology/evaluation/feo013/tests -q -p no:cacheprovider",
        ],
        "output_paths": [
            "research/financial_event_ontology/evaluation/feo013/metrics.csv",
            "research/financial_event_ontology/evaluation/feo013/FEO013_LIMITED_EVALUATION.md",
            "research/financial_event_ontology/evaluation/feo013/FEO013_TASK_MANIFEST.json",
            "research/financial_event_ontology/evaluation/feo013/adapter_correction_proposal.md",
        ],
        "metrics": "precision and scoped recall only; F1, corpus recall, and competency-question answer correctness refused",
        "warnings": [
            "Precision and scoped recall do not share a denominator.",
            "The reference set is a single-researcher adjudication.",
            "The value and temporal figures are sample descriptions.",
            "SHACL figures are copied from the preserved report; shapes were not rerun, and the original engine was a local subset.",
            "Twelve identifier-collision rows are excluded and are not true negatives or false negatives.",
            "The repository commit recorded here is HEAD; these evaluation files are not part of that commit.",
        ],
        "failures": [],
        "scoring": {
            "market_change_event_hits": [row["elicited_id"] for row in data["events"]["hits"]],
            "market_change_event_misses": [row["elicited_id"] for row in data["events"]["misses"]],
            "relation_recall_true_positive": [row["review_id"] for row in data["relations"]["true_positive"]],
            "relation_recall_false_negative": [row["review_id"] for row in data["relations"]["false_negative"]],
            "identifier_collision_review_ids": [row["review_id"] for row in data["collision"]],
            "addendum_review_ids": [row["review_id"] for row in data["addendum"]],
        },
        "metric_count": len(metrics),
    }


def main() -> None:
    data = assemble()
    metrics = metric_rows(data)
    git = git_facts()
    write_csv(OUT / "metrics.csv", metrics)
    (OUT / "FEO013_LIMITED_EVALUATION.md").write_text(render_markdown(data, metrics, git), encoding="utf-8")
    (OUT / "FEO013_TASK_MANIFEST.json").write_text(
        json.dumps(manifest(data, metrics, git), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
