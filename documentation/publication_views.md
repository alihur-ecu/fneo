# Publication views

This candidate publishes several graphs. They answer different questions and must not be substituted for one another.

The ontology does not change between views. What changes is which assertions are materialised as positive facts.

## A. System-accepted graph

File: `population/system-accepted/fneo-stock-system-accepted.ttl`

SHA-256: `bec3809d5ac94406109e2825a0822f3d7d9f8a9c9a9b9a3a5343a847772087ac`

Triple count: 51,472.

This file is a byte-identical copy of the frozen assertion-evidence projection. It is the reproducibility graph. It contains:

- frozen system-accepted direct facts;
- frozen qualified assertions;
- frozen assertion-level evidence links;
- human-review metadata already present on those resources.

It does not remove known semantic errors. Incorrect and ambiguous facts identified later remain here so that an evaluation can be repeated against the system output.

The companion file `population/system-accepted/fneo-stock-core-deduplicated.ttl` (SHA-256 `6d11cc255926e6f93242b368f3fddbd941ff88eff1ec38e0d8e3102d08f96343`) is the frozen deduplicated publication graph before assertion-evidence links were added. The system-accepted file is that graph plus the assertion-evidence projection. Neither file was edited.

## B. Human-validated graph

File: `population/human-validated/fneo-stock-human-validated.ttl`

This file is a derived projection, not a byte copy. It keeps accepted facts whose recorded final human label supports publication, together with the structural triples needed to interpret them: mentions, documents, publication time, source identifiers, and provenance that was already on the system output.

It excludes positive direct facts judged incorrect, wrong in participant type, ambiguous as a fact, or dependent on an excluded affected-market link. Excluded records are listed in `population/human-validated/human_validated_exclusions.csv`. They remain in the system-accepted graph.

Duplicate semantic units follow the frozen duplicate-unit crosswalk. The discarded Dow event individual is absent. The retained event and its two correct assertion-evidence paths remain.

Wrong temporal normalisations are not published as accepted temporal facts. This graph contains no accepted `hasEventTime` triple and no direct event-order triple.

## C. Review-required graph

File: `population/review-required/fneo-stock-review-required.ttl`

Derived union of the 30 frozen per-document files in `per-document/`. The per-document files are byte-identical copies. The union is not a byte copy.

The union contains 1,751 resources with validation status RequiresReview and 19,671 triples. It is a candidate overlay. It is not merged into the accepted graph, and it is not evaluated as a standalone accepted domain graph. Some event, entity, and evidence context is described only in the system-accepted graph.

The `candidate-review/` files are frozen comment files. They contain no triples.

## D. Rejected graph

File: `population/rejected/fneo-stock-rejected.ttl`

Derived union of the frozen per-document rejected files (726 triples). Rejected assertions stay out of the accepted and human-validated graphs.

## E. Extension graph

File: `population/extension/fneo-stock-extension.ttl`

Byte-identical consolidated extension graph (808 triples), including market-direction assertions. Direction is optional for the core profile and is not merged into the system-accepted graph. Per-document extension files are also copied.

## F. Experimental temporal graph

File: `population/experimental-temporal/fneo-stock-experimental-temporal.ttl`

The union of the frozen per-document experimental files contains 0 triples. A conformance result on this graph is vacuous. No accepted event-order fact is published here.
