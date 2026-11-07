# Semantic projection architecture

Population proceeds in layers. Each layer can be queried without treating the others as the same claim.

1. A document and its publication time.
2. Textual mentions, with token spans and, where stored, character spans.
3. Entity and event individuals denoted by those mentions.
4. Qualified relation assertions, which name a subject, a predicate IRI, and an object, together with rule provenance and a validation status.
5. Direct triples, materialised only when the assertion status is Accepted.
6. Evidence resources linked by `supportedBy` at trigger level or assertion level.

The deduplicated publication graph collapsed one duplicate market-change unit before step 6. The assertion-evidence projection then added assertion-level evidence without deleting the trigger evidence. The system-accepted file is that result. The human-validated file is a further projection that removes positive facts the recorded review does not support.

Operational labelled-property-graph identifiers are not the public IRIs. Public IRIs use `https://w3id.org/fneo/resource/...`. Mapping tables in `mappings/` record the correspondence. They are not copied into the ontology as implementation classes.
