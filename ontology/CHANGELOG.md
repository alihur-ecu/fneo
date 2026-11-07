# Changelog

This file records development history that used to sit in ontology comments.
`dcterms:modified` `2026-11-06` is the metadata-revision date for the notes
below. It is not a public release date. No DOI is assigned.

## 0.1.0-rc2 — development release candidate

Ontology IRI: `https://w3id.org/fneo/ontology`

Version IRI: `https://w3id.org/fneo/ontology/0.1.0-rc2`

`owl:priorVersion`: `https://w3id.org/fneo/ontology/0.1.0-rc1`

Release candidate 0.1.0-rc2 follows development candidate 0.1.0-rc1. No stable
public release precedes 0.1.0.

Relative to 0.1.0-rc1, the OWL range of `hasAffectedMarket` is the union of
`FinancialMarket` and `MarketIndex`. The core SHACL profile stays narrower:
a populated value is still required to be a `MarketIndex` or an `EquityMarket`.
That profile check is not the OWL range.

Metadata revision on 2026-11-06, with no change to class axioms, property
characteristics, domains, ranges, individuals, or public term IRIs:

- creator is `https://orcid.org/0000-0001-9537-2648` (Ali HUR)
- `rdfs:label` "Financial News Event Ontology"
- repository-local catalogue path replaced by the release-relative path
  `competency_questions/catalogue/cq_to_ontology_requirements.csv`
- internal task identifiers removed from annotations and comments
- extension temporal relations marked experimental in ontology metadata
- duplicate module comment removed

The namespace `https://w3id.org/fneo/` is not registered. This candidate does
not claim that it resolves.

## 0.1.0-rc1 — development release candidate

Version IRI: `https://w3id.org/fneo/ontology/0.1.0-rc1`

Authoring file: `ontology/feo007/release_candidate/fneo-0.1.0-rc1.ttl`

That file sets `owl:priorVersion` to `https://w3id.org/fneo/ontology/0.1.0`.
Its recorded difference from 0.1.0 is the OWL range of `hasAffectedMarket`,
which 0.1.0-rc1 narrowed and 0.1.0-rc2 restored to the union of
`FinancialMarket` and `MarketIndex`.

`dcterms:issued` on both candidates is the previously recorded date
`2026-10-30`. That date is not a public deposit date.

## 0.1.0 — development version, not a stable release

Version IRI: `https://w3id.org/fneo/ontology/0.1.0`

Authoring file: `ontology/feo006/ontology/fneo.ttl`

The file describes itself as a development version and not a stable release.
No stable public release precedes 0.1.0.

## Not updated

`release/fneo-rc1/ontology/fneo-0.1.0-rc2.ttl` is a misnamed copy that was
byte-identical to this candidate before the metadata revision. It was left
unchanged. The package copy is `release/fneo-rc2/ontology/fneo.ttl`.
