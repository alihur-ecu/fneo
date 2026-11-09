# Release overview

Artefact release v0.1.1 packages ontology version 0.1.0-rc2 and the stock-news graphs used to evaluate it.

The ontology checksum is `6e58c94ce6ffcd0f94d7e8257abb5a33f342b567f28438ebca1761fc122b78af` (1,096 triples). OWL/XML and JSON-LD were checked for triple-set isomorphism with the Turtle file. Byte identity applies to the Turtle copy and to the copied OWL/XML and JSON-LD serialisations.

SHACL shapes are copied byte-for-byte under `validation/original/` and republished in portable form under `validation/portable/`. The portable form does not change constraint logic. It moves warning and information SPARQL checks onto shapes that carry `sh:severity` directly.

Graph profiles, evidence layers, and the human-validated projection are described in the neighbouring notes. Recorded fractions are listed with their sources in `documentation/evaluation_methodology.md`.

DOI: https://doi.org/10.5281/zenodo.24047774
