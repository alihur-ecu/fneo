# Changelog

This file records ontology history that used to sit in ontology comments.
`dcterms:modified` `2026-11-06` is the metadata-revision date. The artefact
DOI https://doi.org/10.5281/zenodo.24047774 belongs to release v0.1.1 and is
not written into the ontology file.

## 0.1.0-rc2

Ontology IRI: `https://w3id.org/fneo/ontology`

Version IRI: `https://w3id.org/fneo/ontology/0.1.0-rc2`

`owl:priorVersion`: `https://w3id.org/fneo/ontology/0.1.0-rc1`

Version 0.1.0-rc2 follows 0.1.0-rc1. Artefact release v0.1.1 publishes this version.

Relative to 0.1.0-rc1, the OWL range of `hasAffectedMarket` is the union of
`FinancialMarket` and `MarketIndex`. The core SHACL profile stays narrower:
a populated value is still required to be a `MarketIndex` or an `EquityMarket`.
That profile check is not the OWL range.

Metadata revision on 2026-11-06, with no change to class axioms, property
characteristics, domains, ranges, individuals, or public term IRIs:

- creator is `https://orcid.org/0000-0001-9537-2648` (Ali HUR)
- `rdfs:label` "Financial News Event Ontology"
- catalogue annotation uses a release-relative path rather than a workspace path
- development identifiers removed from annotations and comments
- extension temporal relations marked experimental in ontology metadata
- duplicate module comment removed

The namespace `https://w3id.org/fneo/` is the identifier used in the file. W3ID registration is pending, so the namespace does not yet resolve.

## 0.1.0-rc1

Version IRI: `https://w3id.org/fneo/ontology/0.1.0-rc1`

`owl:priorVersion` points to `https://w3id.org/fneo/ontology/0.1.0`.
The recorded difference from 0.1.0 is the OWL range of `hasAffectedMarket`,
which 0.1.0-rc1 narrowed and 0.1.0-rc2 restored to the union of
`FinancialMarket` and `MarketIndex`.

`dcterms:issued` on these versions is `2026-10-30`.

## 0.1.0

Version IRI: `https://w3id.org/fneo/ontology/0.1.0`

This version is the prior version recorded by 0.1.0-rc1. It is not published as a separate file in this repository.
