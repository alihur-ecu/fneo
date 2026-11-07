# Human-validated projection policy

The human-validated graph is derived from the system-accepted graph. Labels are taken only from recorded review tables. No label was invented.

## Label sources

- FEO-017 core competency-question review, final `human_label` on each returned answer.
- Assertion-evidence review, final `human_label` on each of the 27 assertion paths.
- FEO-012B reference identifiers and FEO-014 corrected candidate and decision identifiers, joined where a review row cites them.
- The frozen duplicate-unit crosswalk for the Dow plunge and decline unit.
- The FEO-016 sensitivity report, used to confirm that the two post-adjudication disagreements are not in this publication graph. They were already absent from the system-accepted graph.

The frozen reference remains the primary alignment for the competency-question review. This projection uses the final human labels on the answers that the queries actually returned.

## Rules applied

1. An incorrect direct positive semantic triple is removed from the human-validated graph and left in the system-accepted graph.
2. The system decision and the human judgement stay in the review tables and in `human_validated_exclusions.csv`.
3. An ambiguous classification is not published as a validated positive fact. One MarketIndex answer labelled ambiguous loses `rdf:type MarketIndex`. The individual remains an `Entity`, so mentions still denote an entity.
4. Duplicate resources follow the frozen duplicate-unit policy. The discarded event IRI is absent. Both assertion-evidence paths that the review labelled correct on the retained event are kept.
5. No accepted event-time anchor and no direct event-order triple is present in the source graph, so none is published here. Source literals are not rewritten.
6. Trigger-level evidence for an excluded market-change classification is not linked by `supportedBy` from that event. The evidence individual can remain in the graph. It is not presented as validated support for a positive market-change fact.
7. An incorrect or ambiguous assertion-evidence path is not a validated evidence path. The 22 paths labelled correct are kept.
8. Every retained resource is still present in the system-accepted graph. The projection does not create new domain individuals.

## What was removed

| Exclusion | Count | How identified |
| --- | ---: | --- |
| Incorrect MarketIndex or EquityMarket type | 6 | FDQ-001 or FDQ-002 `incorrect_answer` |
| Ambiguous MarketIndex type | 1 | FDQ-001 `ambiguous_answer` |
| Incorrect `hasAffectedMarket` pair | 3 | FDQ-004 `incorrect_answer` |
| Incorrect market-change event classification | 1 | FDQ-003 `incorrect_answer` |
| Dependent market-change classification | 2 | FDQ-003 `correct_answer`, but the only affected-market pair is `incorrect_answer` |
| Assertion-evidence path removed with an incorrect pair | 3 | Assertion-evidence `incorrect_answer` on those pairs |
| Ambiguous assertion-evidence path, pair retained | 2 | Assertion-evidence `ambiguous_answer`; FDQ-003 and FDQ-004 remain `correct_answer` |

The two dependent exclusions are projection consequences. A typed market-change event requires a validated affected market. Those two events keep the human label `correct_answer` in the exclusion table. Their classification is omitted so that an incorrect market link is not replaced by an incomplete validated event. This is not a new judgement that the event text is incorrect.

Qualified assertions that materialised an excluded type or an excluded affected-market link are removed from this graph and retained in the system-accepted graph. They are not rewritten into a different validation status.

## Retained validated facts

- 61 `MarketIndex` individuals, each with FDQ-001 label `correct_answer`.
- 12 `EquityMarket` individuals, each with FDQ-002 label `correct_answer`.
- 23 `MarketChangeEvent` individuals, each with FDQ-003 label `correct_answer` and a retained affected-market pair.
- 23 `hasAffectedMarket` triples, each with FDQ-004 label `correct_answer`.
- 22 assertion-evidence resources, each with assertion-evidence label `correct_answer`.

`Entity` and `Event` types are kept when a narrower type is removed, so mention denotation remains interpretable. Documents, publication times, and source-document identifiers are kept.
