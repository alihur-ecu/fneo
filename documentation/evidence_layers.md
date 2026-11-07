# Evidence layers

Counts below are from the system-accepted graph unless a sentence names the human-validated graph. They describe that graph. They are not corpus recall.

## Trigger-level evidence

A trigger-level `TextualEvidence` resource grounds an event expression. In the system-accepted graph, 27 such resources are the non-projection `supportedBy` objects of the 26 `MarketChangeEvent` individuals. One retained event has two trigger resources, corresponding to two event mentions of one semantic unit.

The original competency-question review of trigger spans (FDQ-005 on the deduplicated graph) judged those spans as trigger evidence. That review reported 0 correct, 9 incorrect, and 18 partially correct answers out of 27. A partial label there means the span is the change trigger and does not itself enclose the affected market. That result is not assertion-evidence correctness, and it is not corpus recall.

## Entity-mention evidence

An `EntityMention` grounds a financial entity through `denotes`. The system-accepted graph contains 1,392 entity mentions. Twenty-six of those mentions denote an entity that is the object of `hasAffectedMarket` on a market-change event. Entity-mention grounding identifies the market expression. It does not by itself ground the event–market assertion.

## Assertion-level evidence

Assertion evidence grounds the complete event–market assertion. The projection created 27 `TextualEvidence` resources with `populationMethod` `assertion_evidence_projection`, each linked by `supportedBy` from the qualified participation. The human review of those 27 paths is the corrected FDQ-005 result.

Among the 27 paths, the recorded labels are 22 correct, 3 incorrect, and 2 ambiguous. The answer-correctness denominator excludes the two ambiguous paths, so the verified figure is 22/25. The same 22/25 is the exact evidence correctness and the exact-or-partial evidence correctness, because no path was labelled partial. These figures are copied from `evaluation/assertion_evidence_projection/evaluation/fdq005_assertion_correctness.csv`. They are not a corpus-wide evidence rate.

The human-validated graph keeps the 22 paths labelled correct. It omits the 3 incorrect paths and the 2 ambiguous paths. Component grounding does not automatically imply assertion grounding: a trigger span and a market mention can both be present while the assertion span is a separate answer unit.

## Source sentence or passage evidence

Where an assertion-evidence review row records a source sentence, that sentence is the passage from which the assertion span was taken. The release keeps those short excerpts inside the internal review tables. It does not copy full source articles. Excerpt redistribution follows the corpus terms, not the ontology licence.

## Review evidence

Human labels are review evidence. They are stored in the competency-question worksheet and the assertion-evidence worksheet. A label judges a specified answer unit. It is not a second annotation of the whole corpus, and this package does not report inter-annotator agreement.

## Operational provenance

Qualified assertions carry rule identifiers, population method, confidence, and the population activity. Those properties record how the implemented pipeline and the later rule population produced the assertion. They are not domain facts about the market. The human-validated graph keeps that provenance on retained assertions and points excluded assertions back to the system-accepted graph.

## What the layers do not imply

Trigger evidence grounds an event expression. Entity-mention evidence grounds a financial entity. Assertion evidence grounds the complete event–market assertion. A correct component does not make the assertion correct, and a correct assertion does not make an ambiguous assertion-evidence path into validated support. The 22/25 figure is the reviewed assertion-evidence rate for 27 paths. It is not recall over the corpus.
