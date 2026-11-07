# Financial News Event Ontology

Assembled artefact package for development candidate 0.1.0-rc2. This is not a
released artefact package. No repository URL and no DOI are assigned. The
intended repository `alihur-ecu/fneo` has not been created. The namespace
`https://w3id.org/fneo/` is not registered.

Creator: Ali HUR, https://orcid.org/0000-0001-9537-2648

Contact: the creator, identified by the ORCID above. A public contact address
is not published in this pre-release package.

## 1. Project overview

FNEO is a corpus-grounded OWL ontology for entities, events, participant
roles, financial objects, values, times, qualified assertions, and textual
evidence in financial news. The accompanying experiment projects a fixed
operational TextGraph, document by document, into status-gated domain graphs.

Provenance of the study input:

```text
raw Wikinews text and source metadata
    -> TextGraphX processing
    -> operational TextGraphs
    -> status-gated semantic projection
    -> FNEO domain graph views
```

## 2. Article contribution

The manuscript's contribution is:

1. a governed semantic-publication lifecycle, as the primary contribution;
2. a financial-news instantiation of that lifecycle;
3. a bounded empirical analysis of two operating points on the same 30 documents.

## 3. Ontology overview

One OWL file, version IRI `https://w3id.org/fneo/ontology/0.1.0-rc2`, prior
version IRI `https://w3id.org/fneo/ontology/0.1.0-rc1`. Release candidate
0.1.0-rc2 follows development candidate 0.1.0-rc1. No stable public release
precedes 0.1.0. Extension temporal relations are experimental. See
`ontology/CHANGELOG.md`, `ontology/DESIGN_DECISIONS.md`, and
`ontology/FUTURE_CHANGES.md`.

## 4. Reproducibility boundary

Computational reproducibility here starts from the frozen operational input.
From that input the package is intended to regenerate semantic projection,
SHACL validation, competency questions, and evaluation summaries.

It does not claim:

- full source-document-to-domain-KG reproduction;
- independent replication;
- public availability;
- unseen-document or cross-domain validation;
- OWL-reasoner reproduction, until HermiT has actually been rerun and the
  report in `validation/owl/` says passed rather than blocked.

## 5. What is included

The ontology, SHACL profiles, baseline and refined configurations, competency
questions FDQ-001 through FDQ-005, the 30 operational TextGraphs, the
store-level supplement, public evaluation registers, and the validation
reports produced for this candidate.

## 6. What is excluded

Private second-reader material, reviewer free text, personal data,
credentials, absolute local paths, frozen private endpoints, scratch Neo4j
stores, `work/`, and files whose licence is unresolved. The annotated MEANTIME
files are not included in the release. The original distribution licence
file is included at `third_party/MEANTIME/LICENSE.txt`. See
`third_party/MEANTIME/SOURCE_RECORD.md`.

## 7. Quick start

From this directory, after the requirements in the next section are installed:

```bash
make verify-inputs PYTHON=python3
make validate-ontology PYTHON=python3
```

`make reproduce` regenerates decisions when the projection engine and a
disposable Neo4j are available. `make reproduce-clean` verifies the frozen
input without reading a personal password file. Full decision regeneration
from `make reproduce-clean` stays blocked until the projection engine is
vendored inside this package. The current engines live outside it.

## 8. Environment requirements

| Component | Pin |
| --- | --- |
| Python | 3.12 |
| RDFLib | 7.6.0 in the pySHACL environment; 7.1.4 parses the ontology in the study interpreter |
| pySHACL | 0.40.2 |
| Neo4j | 5.9.0, disposable, started by `docker-compose.reproduce.yml` |
| ROBOT | 1.9.11, image `docker/ontology-validation` |
| HermiT | the reasoner bundled with ROBOT 1.9.11 |
| Java | 17 in the validation image |

No credential is stored in the package.

## 9. Operational input

`inputs/operational/textgraphs/` has one JSON file for each of the 30 English
stock-market documents and `_store_supplement.json` (4 PhaseRun nodes and 432
cross-document relationships). The recorded store totals are 27,126 nodes and
121,539 relationships. Source text is present. `contains_meantime_annotation`
is `no` for every document. Read `inputs/operational/SOURCE_NOTICE.md`.

## 10. Baseline and refined configurations

`configs/baseline/market_change_rules.json` has no blocking condition.
`configs/refined/market_change_rules.json` adds
`negative_market_not_undergoer_of_trigger` to `FE-MCE-001`. That is the only
scientific difference between the two market-change files.

## 11. Clean reproduction command

```bash
make reproduce-clean PYTHON=python3
```

The command verifies the 30 graphs, the supplement, and the input checksums.
It does not use an institutional Neo4j store. A disposable database is defined
in `docker-compose.reproduce.yml` and requires `FNEO_NEO4J_PASSWORD` to be
generated for the run. Decision regeneration is blocked until the external
projection engine is part of this package. Do not treat a blocked engine step
as a failed scientific result, and do not edit headline numbers to force a pass.

## 12. Expected results

| Result | Fraction |
| --- | --- |
| Baseline event precision | 31/50 |
| Refined event precision | 25/26 |
| Baseline affected-market precision | 29/50 |
| Refined affected-market precision | 23/26 |
| Acceptance retention | 26/50 |
| Event candidate availability | 21/24 |
| Affected-market candidate availability | 6/19 |
| Exact trigger coverage | 0/27 |
| Exact-or-partial trigger support | 18/27 |
| Assertion-path alignment | 22/25 |
| Second-reader events | 46/50 |
| Second-reader affected-market links | 45/50 |
| Second-reader assertion evidence | 26/27 |

Refined census: 4,285; 379; 1,751; 66; 1,481. Total decisions: 7,962.

Two ambiguous assertion paths remain outside 22/25. The accepted duplicate
event remains outside \(U_A\). No calibration-excluded result is a headline
result.

## 13. Validation

`make validate-ontology` parses the Turtle, checks metadata and IRI syntax,
reruns competency questions against the System-Accepted Graph, and runs SHACL
when pySHACL imports. ROBOT profile validation and HermiT consistency run when
the validation image or a local ROBOT jar is available. Reports are under
`validation/`. A blocked reasoner is not a consistency pass.

## 14. Competency questions

FDQ-001 through FDQ-005 are in `competency_questions/queries/feo017/`. They
are executed against the System-Accepted Graph.

## 15. Licensing

See `LICENSING.md`. Code is MIT. The ontology, SHACL profiles, and SPARQL
queries are CC BY 4.0. Mappings and rules are proposed CC BY 4.0, subject to
final approval. Source-bearing TextGraphs are not MIT and not CC0.

## 16. Attribution

The 30 operational TextGraphs were generated by TextGraphX from the raw Wikinews articles and retained source-file metadata. No manual MEANTIME annotations were used to generate the TextGraphs or evaluate semantic projection in this study. The Wikinews article text is redistributed and transformed under CC BY 2.5, with article title, contributor attribution, publication date, source URL, licence, and transformation notice recorded in `document_manifest.tsv`. MEANTIME identifies the complete 30-document English stock-market topic and supplies limited packaging metadata, including publicId and corpus filenames. This metadata is attributed to MEANTIME under CC BY 4.0. The annotated MEANTIME files are not included in the release.

## 17. Citation

See `CITATION.cff`. Prefer: Hur, Ali. Financial News Event Ontology,
development release candidate 0.1.0-rc2. ORCID
https://orcid.org/0000-0001-9537-2648. No DOI and no public release date are
assigned.

## 18. Troubleshooting

- Input verification failure: restore the graph from `inputs/operational/SHA256SUMS`. Do not edit a graph in place.
- A headline mismatch is a scientific discrepancy. Do not replace the fraction.
- Java is required only for HermiT. Decision counts do not depend on Java.
- If `make reproduce-clean` reports the decision engine as blocked, the frozen
  operational checksums can still pass. That block is the missing vendored
  engine, not a changed result.
- Private second-reader notes are not in this package.

## 19. Contact

Ali HUR, https://orcid.org/0000-0001-9537-2648
