# Financial News Event Ontology

FNEO is an OWL ontology for entities, events, participant roles, financial objects, values, times, qualified assertions, and textual evidence in financial news. This repository publishes artefact release `v0.1.1`. The ontology version in that artefact is `0.1.0-rc2`.

The accompanying article is *Decision-to-Publication Semantics for Operational Text Graphs: A Financial-News Case*.

| Item | Value |
| --- | --- |
| Creator | Ali HUR |
| ORCID | https://orcid.org/0000-0001-9537-2648 |
| Repository | https://github.com/alihur-ecu/fneo |
| Documentation | https://alihur-ecu.github.io/fneo/ |
| Artefact release | `v0.1.1` (2026-11-08) |
| DOI | https://doi.org/10.5281/zenodo.24047774 |
| Ontology IRI | https://w3id.org/fneo/ontology |
| Ontology version IRI | https://w3id.org/fneo/ontology/0.1.0-rc2 |
| Namespace | https://w3id.org/fneo/ |

Registration of `https://w3id.org/fneo/` is pending with the W3ID maintainers ([perma-id/w3id.org#7103](https://github.com/perma-id/w3id.org/pull/7103)). Until that pull request is merged, use the files in this repository and on GitHub Pages. The ontology IRIs are the identifiers used in the data.

## Study

The accompanying experiment projects 30 operational TextGraphs, one document at a time, into status-gated domain graphs.

```text
raw Wikinews text and source metadata
    -> TextGraphX processing
    -> operational TextGraphs
    -> status-gated semantic projection
    -> FNEO domain graph views
```

The study provides a governed semantic-publication lifecycle, a financial-news instantiation of that lifecycle, and a bounded comparison of two operating points on the same 30 documents.

Reproduction starts from the frozen operational input and regenerates semantic projection, SHACL validation, competency questions, and evaluation summaries. It does not reproduce TextGraph construction from the source articles, and it is not an independent replication or an unseen-document evaluation.

## Contents

The ontology, SHACL profiles, baseline and refined configurations, competency questions FDQ-001 through FDQ-005, the 30 operational TextGraphs, publication graphs, public evaluation registers, and validation reports.

Annotated MEANTIME files are not included. Article text and source-bearing graphs stay under CC BY 2.5. See `LICENSING.md` and `inputs/operational/SOURCE_NOTICE.md`.

## Quick start

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements-lock.txt
export FNEO_NEO4J_PASSWORD='choose-a-disposable-password'
make reproduce-clean
```

| Component | Pin |
| --- | --- |
| Python | 3.12.13 |
| RDFLib | 7.6.0 |
| pySHACL | 0.40.2 |
| Neo4j | 5.9.0, disposable, port 17689 |
| ROBOT | 1.9.11 |
| HermiT | bundled with ROBOT 1.9.11 |
| Java | 17 in the validation image |

Other Python dependencies are pinned in `requirements-lock.txt`. The disposable Neo4j password comes from the environment only.

`inputs/operational/textgraphs/` has one JSON file for each of the 30 English stock-market documents and `_store_supplement.json` (4 PhaseRun nodes and 432 cross-document relationships). The recorded store totals are 27,126 nodes and 121,539 relationships. `contains_meantime_annotation` is `no` for every document.

`configs/baseline/market_change_rules.json` has no blocking condition. `configs/refined/market_change_rules.json` adds `negative_market_not_undergoer_of_trigger` to `FE-MCE-001`. That is the only difference between the two market-change files.

`make reproduce-clean` verifies the 30 graphs and the input checksums, imports them into disposable Neo4j 5.9.0 on port 17689, and regenerates the decision files. It does not use `bolt://localhost:7687`. If a checksum or headline fraction differs from the reference, the run fails.

## Expected results

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

`make validate-ontology` parses the Turtle, checks metadata, reruns competency questions, and runs SHACL. ROBOT 1.9.11 profile validation and HermiT consistency run in `docker/ontology-validation`. Reports are under `validation/`.

FDQ-001 through FDQ-005 are in `competency_questions/queries/feo017/`.

## Licensing and citation

Code is MIT (`LICENSE-CODE`). Authored ontology, shapes, mappings, rules, queries, and documentation are CC BY 4.0 (`LICENSE-CONTENT`). Wikinews text and source-bearing TextGraphs are CC BY 2.5. MEANTIME packaging metadata is CC BY 4.0. See `LICENSING.md`.

Artefact: Hur, Ali. *FNEO: Governed Semantic Publication from Operational Text Graphs*. Version 0.1.1, 2026. https://doi.org/10.5281/zenodo.24047774

Article: *Decision-to-Publication Semantics for Operational Text Graphs: A Financial-News Case*.

## Contact

Ali HUR, https://orcid.org/0000-0001-9537-2648

If input verification fails, restore the graph from `inputs/operational/SHA256SUMS`. A headline mismatch is a discrepancy with the recorded result. Java is required only for HermiT. Set `FNEO_NEO4J_PASSWORD` before `make reproduce-clean`.
