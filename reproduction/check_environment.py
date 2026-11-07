"""Fail if the reproduction interpreter is missing a required module."""

from __future__ import annotations

import sys


def main() -> int:
    missing = []
    for name in ("neo4j", "rdflib", "jsonschema", "yaml"):
        try:
            __import__(name)
        except ImportError:
            missing.append(name)
    if missing:
        print("missing modules:", ", ".join(missing))
        print("Use an interpreter that can import neo4j, rdflib, jsonschema, and PyYAML.")
        return 1
    print(f"environment ok: python {sys.version.split()[0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
