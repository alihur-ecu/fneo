# Reuse guide

## Ontology only

Load `ontology/fneo.ttl`, `ontology/fneo.owl`, or `ontology/fneo.jsonld`. They are the same triple set in three serialisations. The Turtle file is the byte-identical canonical copy. Use the portable SHACL files in `validation/portable/` if results must distinguish violations, warnings, and informational findings under pySHACL 0.40.2. Keep the files in `validation/original/` when an exact replay of the earlier severity placement is required.

The namespace does not yet resolve. Treat the IRIs as identifiers, not as fetchable documents, until registration is completed.

## With the stock-news graphs

Choose the profile in `documentation/publication_views.md` before loading a graph.

Use the human-validated graph for a cleaned semantic view of the reviewed facts. Use the system-accepted graph to reproduce the system output, including known errors. Do not load the review-required file as if it were the accepted knowledge graph. Do not merge the extension or rejected files into the accepted file.

Corpus-derived graphs are internal until the corpus licence is confirmed.

## Queries

Competency-question queries are in `competency_questions/queries/`. The FEO-017 files are the executed population queries. The foundational directory holds the earlier ontology-development queries, including extension queries. The assertion-evidence directory holds the corrected FDQ-005 query.

Run a query against one graph. Do not union the profiles unless the query documentation says to. Do not average the five core questions.

## Validation

See `reproducibility/PYTHON_ENVIRONMENT.md`. The validation command does not require the source corpus or a database.

## Citation

Use `release/CITATION.cff` after the placeholders are replaced. Until then, do not present the file as a finished citation. The 2024 pipeline article is related work.
