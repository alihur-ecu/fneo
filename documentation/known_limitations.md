# Known limitations

- One researcher produced the reference labels and the later competency-question labels. There is no second annotator and no inter-annotator agreement.
- Precision uses accepted system decisions. Scoped recall uses an elicited subset. Those denominators are not combined, and no global F1 is defined.
- Corpus-wide recall is not supported. Untyped mentions and unreviewed candidates are not a census of the corpus.
- The system-accepted graph contains facts the review labelled incorrect or ambiguous. It is the reproducibility graph, not a cleaned knowledge base.
- The human-validated graph omits those facts. It does not add a new precision score, and it does not show that every retained triple would survive a second review.
- Two market-change events labelled correct as events are omitted because their only affected-market link was labelled incorrect. The omission is recorded as a dependent exclusion.
- Trigger-level FDQ-005 and assertion-level FDQ-005 measure different spans. The trigger result must not be quoted as the assertion-evidence result.
- No accepted event-time anchor and no accepted event-order fact is in the publication graphs. Temporal reasoning on fixtures is not population evidence.
- The namespace `https://w3id.org/fneo/` is the identifier used in the files. W3ID registration is pending, and a request returned HTTP 404 on 2026-10-31.
- Corpus-derived RDF follows the attribution terms in `LICENSING.md`. It is not MIT and not CC0. The ontology licence does not extend to it.
- pySHACL 0.40.2 does not apply `sh:severity` placed only on a nested SPARQL constraint. Use the portable shapes for a severity-accurate pySHACL result.
- Conformance of the empty experimental graph is vacuous.
