# Temporal profiles

Temporal questions are separated by the kind of time they use.

## Explicit time

The system-accepted graph contains time entities and time mentions, including publication times on documents. It contains no accepted `hasEventTime` triple. The post-correction evaluation reports zero accepted explicit event-time anchors in the scored sample. Absence of event time on a market-change event is a SHACL warning, not a violation.

## Normalised time

Normalised time values, where present on time entities, are strings. A wrong normalisation identified in the adapter review is not republished here as an accepted event time. Source literals in the system-accepted graph are unchanged.

## Event-time anchoring

No accepted event-time anchor is materialised as a direct `hasEventTime` fact. Review-required files may contain candidate assertions whose predicate IRI is `hasEventTime`. Those candidates are not accepted facts.

## Inferred event order

The system-accepted graph contains no direct `precedes`, `follows`, `simultaneousWith`, `occursDuring`, or `includes` triple. The experimental temporal profile has 0 triples. The event-order review sample was not scored as precision or recall: the review form did not show ordering text, and 73 of 73 rows were held out for that reason. Inferred order is not presented as equal in reliability to an explicit time anchor.

Inverse properties such as `follows` given `precedes` are reasoner entailments on fixtures. They are not extracted facts in the population graphs. `simultaneousWith` is not symmetric in this ontology version.
