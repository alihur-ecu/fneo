# System-accepted graph

| Item | Value |
| --- | --- |
| Release path | `population/system-accepted/fneo-stock-system-accepted.ttl` |
| SHA-256 | `bec3809d5ac94406109e2825a0822f3d7d9f8a9c9a9b9a3a5343a847772087ac` |
| Triple count | 51,472 |
| Accepted status count | 596 resources with `hasValidationStatus` Accepted |

## Intended use

This graph reflects system output. It is required for reproducibility. It contains known errors identified by human evaluation. It must not be described as a fully human-validated knowledge graph.

Known incorrect and ambiguous positive facts remain in this file. The human-validated projection lists them in `population/human-validated/human_validated_exclusions.csv` and omits the corresponding positive triples from that derived graph only.

## Relation to the deduplicated graph

`fneo-stock-core-deduplicated.ttl` (SHA-256 `6d11cc255926e6f93242b368f3fddbd941ff88eff1ec38e0d8e3102d08f96343`) is the frozen deduplicated publication graph. The assertion-evidence projection copied that graph and added assertion-level evidence resources and `supportedBy` links. The system-accepted file is the projection, not a second deduplication.

## Known errors that remain here

The core competency-question review and the assertion-evidence review, both completed on 2026-10-31, identify incorrect and ambiguous answers among the resources in this graph. Those labels are evaluation metadata. They were not used to delete triples from this file.

Illustrative counts, copied from the review tables rather than recomputed as a new precision metric:

- MarketIndex answers: 61 correct, 3 incorrect, 1 ambiguous, out of 65.
- EquityMarket answers: 12 correct, 3 incorrect, out of 15.
- MarketChangeEvent answers: 25 correct, 1 incorrect, out of 26.
- Affected-market pairs: 23 correct, 3 incorrect, out of 26.
- Assertion-evidence paths: 22 correct, 3 incorrect, 2 ambiguous, out of 27.

The cleaned publication graph is `population/human-validated/fneo-stock-human-validated.ttl`.
