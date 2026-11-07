# Human-validated graph validation

The projection policy is `human_validated_projection_policy.md`. Parsed triples: 51,255. SHA-256 of the derived Turtle file is recorded in `provenance/build_counts.json`.

Portable core shapes, pySHACL 0.40.2: conforms=True, violations=0, warnings=1342, information=92.

Retained MarketIndex, EquityMarket, MarketChangeEvent, and hasAffectedMarket resources match a `correct_answer` label. Retained assertion-evidence paths match `correct_answer`. No RequiresReview or Rejected status is present. The discarded duplicate event is absent. This note does not calculate a new system precision from the cleaned graph.

Policy problems recorded by the checker: none.
