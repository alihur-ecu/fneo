# Financial News Event Ontology

Development candidate 0.1.0-rc2. This is not a public release.

| Item | Value |
| --- | --- |
| Creator | Ali HUR |
| ORCID | https://orcid.org/0000-0001-9537-2648 |
| Repository URL | TO BE ADDED AT PUBLIC RELEASE |
| DOI | TO BE ADDED AT PUBLIC RELEASE |
| Release date | TO BE ADDED AT PUBLIC RELEASE |
| W3ID namespace | TO BE ADDED AT PUBLIC RELEASE (`https://w3id.org/fneo/` is not registered) |

## 1. Project overview

FNEO is a corpus-grounded OWL ontology for entities, events, participant
roles, financial objects, values, times, qualified assertions, and textual
evidence in financial news. The accompanying experiment projects a fixed
operational TextGraph, document by document, into status-gated domain graphs.

```text
raw Wikinews text and source metadata
    -> TextGraphX processing
    -> operational TextGraphs
    -> status-gated semantic projection
    -> FNEO domain graph views
```

## 2. Article contribution

1. a governed semantic-publication lifecycle, as the primary contribution;
2. a financial-news instantiation of that lifecycle;
3. a bounded empirical analysis of two operating points on the same 30 documents.

## 3. Ontology overview

One OWL file, version IRI `https://w3id.org/fneo/ontology/0.1.0-rc2`, prior
version IRI `https://w3id.org/fneo/ontology/0.1.0-rc1`. No stable public
release precedes 0.1.0. Extension temporal relations are experimental. See
`ontology/CHANGELOG.md`.

## 4. Reproducibility boundary

Computational reproduction starts from the frozen operational input. From
that input this package regenerates semantic projection, SHACL validation,
competency questions, and evaluation summaries.

This is not full source-document-to-TextGraph reproduction. This is not
independent replication. This package is not public yet.

## 5. What is included

The ontology, SHACL profiles, baseline and refined configurations, competency
questions FDQ-001 through FDQ-005, the 30 operational TextGraphs, the
store-level supplement, public evaluation registers, and the validation
reports produced for this candidate.

## 6. What is excluded

Private second-reader material, reviewer free text, personal data,
credentials, absolute local paths, scratch Neo4j stores, and the annotated
MEANTIME files. The original MEANTIME distribution licence is at
`third_party/MEANTIME/LICENSE.txt`.

## 7. Quick start

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements-lock.txt
export FNEO_NEO4J_PASSWORD='choose-a-disposable-password'
make reproduce-clean
```

## 8. Environment requirements

| Component | Pin |
| --- | --- |
| Python | 3.12.13 |
| RDFLib | 7.6.0 |
| pySHACL | 0.40.2 |
| Neo4j | 5.9.0, disposable, port 17689 |
| ROBOT | 1.9.11 |
| HermiT | bundled with ROBOT 1.9.11 |
| Java | 17 in the validation image |

Other Python dependencies are pinned in `requirements-lock.txt`. No
credential is stored in the package. The disposable Neo4j password comes
from the environment only.

## 9. Operational input

`inputs/operational/textgraphs/` has one JSON file for each of the 30 English
stock-market documents and `_store_supplement.json` (4 PhaseRun nodes and 432
cross-document relationships). The recorded store totals are 27,126 nodes and
121,539 relationships. `contains_meantime_annotation` is `no` for every
document.

## 10. Baseline and refined configurations

`configs/baseline/market_change_rules.json` has no blocking condition.
`configs/refined/market_change_rules.json` adds
`negative_market_not_undergoer_of_trigger` to `FE-MCE-001`. That is the only
scientific difference between the two market-change files.

## 11. Clean reproduction command

```bash
make reproduce-clean
```

The command verifies the 30 graphs and the input checksums, imports them
into disposable Neo4j 5.9.0 on port 17689, and regenerates the decision
files. It does not use bolt://localhost:7687. If a checksum or headline
fraction differs from the reference, the run fails. Do not edit the expected
fractions to force a pass.

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

## 13. Validation

`make validate-ontology` parses the Turtle, checks metadata, reruns
competency questions, and runs SHACL. ROBOT 1.9.11 profile validation and
HermiT consistency run in `docker/ontology-validation`. Reports are under
`validation/`.

## 14. Competency questions

FDQ-001 through FDQ-005 are in `competency_questions/queries/feo017/`.

## 15. Licensing

This repository is not one licence. Code is MIT (`LICENSE-CODE`). Authored
ontology, shapes, mappings, rules, queries, and documentation are CC BY 4.0
(`LICENSE-CONTENT`). Wikinews text and source-bearing TextGraphs are
CC BY 2.5. MEANTIME packaging metadata is CC BY 4.0. See `LICENSING.md`.

## 16. Attribution

The 30 operational TextGraphs were generated by TextGraphX from the raw Wikinews articles and retained source-file metadata. No manual MEANTIME annotations were used to generate the TextGraphs or evaluate semantic projection in this study.

The original MEANTIME CC BY 4.0 licence file was retrieved from the annotated dataset archive and preserved unchanged in third_party/MEANTIME/LICENSE.txt. The annotated files are not redistributed. MEANTIME attribution applies to retained corpus-packaging metadata, while the source-bearing operational TextGraphs derive from Wikinews articles distributed under CC BY 2.5.

## 17. Citation

See `CITATION.cff`. Prefer: Hur, Ali. Financial News Event Ontology,
development release candidate 0.1.0-rc2. ORCID
https://orcid.org/0000-0001-9537-2648. No DOI and no public release date are
assigned.

## 18. Troubleshooting

- Input verification failure: restore the graph from `inputs/operational/SHA256SUMS`. Do not edit a graph in place.
- A headline mismatch is a scientific discrepancy. Do not replace the fraction.
- Java is required only for HermiT. Decision counts do not depend on Java.
- Set `FNEO_NEO4J_PASSWORD` before `make reproduce-clean`.

## 19. Contact

Ali HUR, https://orcid.org/0000-0001-9537-2648

## 20. Release status

Repository URL: TO BE ADDED AT PUBLIC RELEASE

DOI: TO BE ADDED AT PUBLIC RELEASE

Release date: TO BE ADDED AT PUBLIC RELEASE

W3ID: TO BE ADDED AT PUBLIC RELEASE

Prepared GitHub workflow files under `.github/workflows/` do not run until a
maintainer reviews them after a repository exists. GitHub Pages is not
claimed to exist. The W3ID redirect in `w3id/fneo/` is UNREGISTERED and
UNTESTED.
