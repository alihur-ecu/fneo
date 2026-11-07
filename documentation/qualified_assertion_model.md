# Qualified assertion model

A qualified assertion is a `RelationAssertion`. It states:

- `assertionSubject`
- `assertionPredicateIRI`, an `xsd:anyURI` literal, so the predicate is not used as an individual
- `assertionObject` or `assertionObjectLiteral`
- `hasValidationStatus`
- confidence and rule or population provenance when the status is Accepted

An accepted assertion is accompanied by the direct triple whose predicate is the IRI literal. A RequiresReview, Rejected, or Suppressed assertion must not be accompanied by that direct triple. Those two constraints are in the core shapes.

Event participations are relation assertions that also name `participationEvent` and `participatingEntity`. In the system-accepted graph the affected-market participations are accepted and the direct `hasAffectedMarket` triple is present. In the review-required graph the participations are RequiresReview and the direct triple is absent.

The human-validated projection removes a qualified assertion from that derived graph when the direct fact it materialises is excluded. The assertion remains in the system-accepted graph as the historical system record. Its status is not rewritten.
