# Assertion materialisation policy

Direct triples are materialised only for accepted assertions.

| Status | Direct triple | Where it is stored |
| --- | --- | --- |
| Accepted | Required | System-accepted graph, and the human-validated graph only when the human label supports it |
| RequiresReview | Prohibited | Review-required overlay |
| Rejected | Prohibited | Rejected graph |
| Suppressed or proposed temporal | Prohibited | Not part of the accepted graph. The experimental profile is empty |

Literal-object assertions follow the same rule and are checked by the supplemental shapes. An accepted literal assertion exposes the datatype triple named by `assertionPredicateIRI`. A rejected literal assertion must not.

The human-validated projection does not keep an accepted qualified assertion after removing its direct triple. Both the triple and the qualifying assertion leave that derived graph together. The system-accepted graph keeps both.

Candidate validation checks the prohibition on the combined bundle. It does not promote a review-required assertion to Accepted.
