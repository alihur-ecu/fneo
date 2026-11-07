# Release overview

Release candidate 0.1.0-rc2 packages the financial-news event ontology and the stock-news graphs used to evaluate it.

The ontology checksum is `6e58c94ce6ffcd0f94d7e8257abb5a33f342b567f28438ebca1761fc122b78af` (1,096 triples). OWL/XML and JSON-LD were checked for triple-set isomorphism with the Turtle file. Byte identity applies to the Turtle copy and to the copied OWL/XML and JSON-LD serialisations. They were not re-serialised.

SHACL shapes are copied byte-for-byte under `validation/original/` and republished in portable form under `validation/portable/`. The portable form does not change constraint logic. It moves warning and information SPARQL checks onto shapes that carry `sh:severity` directly.

Graph profiles, evidence layers, and the human-validated projection are described in the neighbouring notes. Claims that may be repeated elsewhere are listed in `claims/claims_ledger.csv`, each with a source file. The manuscript ledger at `research/financial_event_ontology/manuscript/claims_ledger.csv` was not modified and remains the empty header.

This candidate records a conditional readiness status. Validation can pass while author metadata and corpus licensing remain open. Those open items block public release.
