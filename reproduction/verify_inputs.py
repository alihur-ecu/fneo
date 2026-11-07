"""Verify operational-graph checksums and the 30-document manifest."""

from __future__ import annotations

import csv
import sys

from graphio import EXPECTED_DOCUMENTS, GRAPH_DIR, RC2, sha256_file


def main() -> int:
    bad = []
    lines = (RC2 / "inputs/operational/SHA256SUMS").read_text(encoding="utf-8").splitlines()
    for line in lines:
        if not line.strip():
            continue
        digest, relative = line.split(None, 1)
        path = RC2 / relative
        if not path.is_file() or sha256_file(path) != digest:
            bad.append(relative)
    rows = list(csv.DictReader((RC2 / "document_manifest.tsv").open(encoding="utf-8"), delimiter="\t"))
    blank = [row["document_id"] for row in rows if any(not str(value).strip() for value in row.values())]
    documents = [path for path in GRAPH_DIR.glob("*.json") if path.name != "_store_supplement.json"]
    if bad or blank or len(rows) != EXPECTED_DOCUMENTS or len(documents) != EXPECTED_DOCUMENTS:
        print("input verification failed")
        print("checksum mismatches", bad[:8])
        print("blank manifest rows", blank)
        print("document files", len(documents), "manifest rows", len(rows))
        return 1
    print(f"inputs ok: {len(documents)} operational TextGraphs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
