# Reuse guide

## Ontology only

Load `ontology/fneo.ttl`, `ontology/fneo.owl`, or `ontology/fneo.jsonld`. They are the same triple set in three serialisations. The Turtle file is the byte-identical canonical copy. Use the portable SHACL files in `validation/portable/` if results must distinguish violations, warnings, and informational findings under pySHACL 0.40.2. Keep the files in `validation/original/` when an exact replay of the earlier severity placement is required.

`https://w3id.org/fneo/` does not yet resolve. Treat the IRIs as identifiers until W3ID registration is merged. The files are available from this repository and from GitHub Pages.

## With the stock-news graphs

Choose the profile in `documentation/publication_views.md` before loading a graph.

Use the human-validated graph for a cleaned semantic view of the reviewed facts. Use the system-accepted graph to reproduce the system output, including known errors. Do not load the review-required file as if it were the accepted knowledge graph. Do not merge the extension or rejected files into the accepted file.

Corpus-derived graphs follow `LICENSING.md`. Do not relicense them as MIT or CC0.

## Queries

The executed competency-question queries are `competency_questions/queries/feo017/FDQ-001.rq` through `FDQ-005.rq`.

Run a query against one graph. Do not union the profiles unless the query documentation says to. Do not average the five core questions.

## Validation

Python pins are in the root `README.md` and `requirements-lock.txt`. `make validate-ontology` does not require the source corpus or a database.

## Citation

Use `CITATION.cff`. The artefact DOI is https://doi.org/10.5281/zenodo.24047774. Hur, Janjua, and Ahmed (2024), *Expert Systems with Applications*, 239, is related work. It is not the citation for this ontology.
