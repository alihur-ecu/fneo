# Publication-invariant tests

Status: existing shapes and fixtures were checked. No new SHACL publication
condition was added. A metadata-only ontology edit must not change the
publication rules.

## Already enforced by the packaged shapes and fixtures

| Behaviour | Where it is enforced |
| --- | --- |
| Accepted direct materialisation and missing-direct negative cases | `validation/fixtures/expectations.csv` rows for accepted literal and committed temporal fixtures, plus core and supplemental shapes |
| Requires-review or rejected materialisation must not keep a direct triple | Fixture rows `requires-review-with-direct`, `rejected-with-direct`, `rejected-literal-with-direct` in the validation runner |
| Suppressed temporal candidate must not materialise `precedes` | `suppressed-temporal-direct-triple` |
| Qualified assertion metadata on an accepted assertion | `accepted-assertion-missing-metadata` |
| `denotes` class and cardinality for in-profile mentions | Core shapes on entity, event, and time mentions, including `entity-mention-two-denotes` |
| Resource object and literal object are not both the ordinary case | Supplemental shapes check `assertionObjectLiteral`; the core direct-triple constraint checks individual objects. The ontology scope note forbids using both for one assertion |
| Separate graph files for accepted, review-required, rejected, extension, and experimental temporal views | `reproducibility/run_validation.py` policy checks |

The decision-store policies structural-direct, direct-and-qualified, and none
are implemented by the projection engine. The packaged fixtures cover the RDF
consequences of accepted, requires-review, rejected, and suppressed
materialisation. They were not rewritten.

## Not added

| Requested test | Why it was not added |
| --- | --- |
| Numeric confidence bounds such as 0 to 1 | `fneo:confidence` has range `xsd:decimal`. The scope note says scales are not comparable across components and a missing value is unknown, not zero. No tighter range is implemented. |
| `hasMention` must agree with `denotes` as an inverse | The ontology does not declare `denotes` inverse of `hasMention`. Adding that check would be a new publication condition. |
| Every direct triple traces to an accepted decision, and every completed decision has an audit record | Those records live in the decision store, not as an OWL or SHACL axiom on the domain graph. The existing policy checks already reject review-required and rejected direct triples in the System-Accepted Graph. A new shape was not added. |
| Evidence resources must retain a source-document filesystem path | The ontology uses `sourceDocumentIdentifier` as a string on the document. It does not require a filesystem path. The operational graphs retain `uri` and `filename` as metadata. A new path requirement was not added. |

Policy `none` emitting no RDF assertion is engine behaviour. It is not a new
shape over the six publication views, which by construction contain the
assertions the policies did emit.
