"""Check the reproduction report and the regenerated headline fractions."""

from __future__ import annotations

import csv
import json
import sys

from graphio import RC2

EXPECTED = {
    "R-EVT-BASE": "31/50",
    "R-EVT-REF": "25/26",
    "R-REL-BASE": "29/50",
    "R-REL-REF": "23/26",
    "R-EVT-HOLD": "26/50",
    "R-REL-HOLD": "26/50",
    "R-EVT-AVAIL": "21/24",
    "R-REL-AVAIL": "6/19",
    "R-TRIG-EXACT": "0/27",
    "R-TRIG-PART": "18/27",
    "R-ASSERT-ALIGN": "22/25",
    "R-READ-EVT": "46/50",
    "R-READ-REL": "45/50",
    "R-READ-EVID": "26/27",
}


def main() -> int:
    report_path = RC2 / "evaluation" / "reproduction_report.json"
    if not report_path.is_file():
        print("reproduction report is absent; run make reproduce")
        return 1
    report = json.loads(report_path.read_text(encoding="utf-8"))
    rows = list(csv.DictReader((RC2 / "evaluation/headline_results.csv").open(encoding="utf-8")))
    found = {row["result_id"]: row["fraction"] for row in rows}
    bad = [key for key, value in EXPECTED.items() if found.get(key) != value]
    if not report.get("ok") or bad:
        print("output verification failed")
        print(json.dumps(report.get("steps", {}), indent=2))
        print("fraction mismatches", bad)
        return 1
    print("outputs ok")
    for key in EXPECTED:
        print(f"{key} {found[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
