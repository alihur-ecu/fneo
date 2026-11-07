# Graph profiles

Each profile is a separate RDF graph. Loading one file does not load the others.

## Core accepted profile

The system-accepted graph materialises direct triples only for assertions whose validation status is Accepted. It contains 26 market-change events, 26 `hasAffectedMarket` triples, 65 market-index individuals, and 15 equity-market individuals. It also contains the linguistic layer: documents, mentions, textual evidence, values, and qualified assertions.

The human-validated graph is the same profile after the projection in `population/human-validated/human_validated_projection_policy.md`. It contains 23 market-change events, 23 affected-market triples, 61 market indices, and 12 equity markets.

## Review-required profile

1,751 relation assertions have status RequiresReview. They do not carry Accepted status. Direct domain triples for those assertions are not materialised. The profile is an overlay. Validate it with the candidate shapes on the combined bundle, not with the accepted-fact shapes on the overlay alone.

## Rejected profile

The rejected union contains 726 triples. Resources in it use status Rejected. They are absent from the accepted graph.

## Extension profile

The extension graph contains 808 triples, including market-direction assertions. Direction is optional in the core profile. The extension graph is not merged into the accepted graph.

## Experimental temporal profile

No experimental temporal assertion was emitted. The union has 0 triples. A validator that reports conformance on that file is reporting the vacuous case.

## Separation checks

The system-accepted graph has no RequiresReview status and no Rejected status. The human-validated graph likewise has none. The review-required union is stored as its own file. Market direction is counted on the extension graph and is not a core accepted predicate in the system-accepted graph. These checks are repeated by `reproducibility/run_validation.py`.
