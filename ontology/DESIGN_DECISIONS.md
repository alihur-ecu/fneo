# Design decisions

These notes describe release candidate 0.1.0-rc2 as it is serialized, together
with the semantic-projection experiment that populates it. A bullet that the
files do not establish is marked as an author decision.

## Competency-question-driven scope

The ontology states a competency-question catalogue pointer and a scope note
that limits the model to financial-news reports. It excludes trading
recommendations, investment advice, portfolio construction, accounting,
regulation, live market systems, and predictive analytics. The manuscript
states that the profile includes distinctions required by the competency
questions and supported by the corpus evidence used for the study. The
catalogue file itself is not embedded in the ontology. The pointer is the
release-relative path `competency_questions/catalogue/cq_to_ontology_requirements.csv`.

## Operational versus domain-model separation

TextGraphX operational TextGraphs are the input. FNEO is the domain model for
the projected assertions. The ontology does not import the operational schema,
and the experiment does not treat every operational edge as a domain fact.
Population is a separate, status-gated projection.

## Qualified-assertion pattern

`RelationAssertion` carries statement-level metadata. `assertionPredicateIRI`
is a datatype property with range `xsd:anyURI`. The predicate IRI is stored as
a literal on the assertion resource. A direct triple, when the publication
policy emits one, uses that predicate in predicate position. The ontology text
says this avoids punning a property as an individual.

## Direct versus qualified publication

The ontology defines both direct object properties and qualified assertion
resources. Which combination is written is a population policy, checked by
SHACL profiles rather than by an OWL cardinality axiom on every policy. The
implemented policies in the experiment are structural-direct,
direct-and-qualified, and none. Accepted structural-direct decisions emit a
direct triple and no qualified assertion. Accepted direct-and-qualified
decisions emit both. Requires-review and rejected direct-and-qualified
decisions emit a qualified assertion and no direct triple. Policy none emits
neither. Those publication rules are implemented behaviour of the projection,
not new OWL axioms in this candidate.

## Decision versus assertion co-representation

The ontology defines no `Decision` class. Conceptually the semantic decision
and the qualified assertion are distinct. The decision is a judgement over a
candidate, whereas the qualified assertion represents the mapped proposition
with statement-level metadata. The current RDF serialization co-represents
these roles using one assertion resource, while the decision store retains its
identifier separately. This paragraph records that design. It does not add a
`Decision` class.

## Document-scoped identity

A source-document identifier on a financial news document is provenance, not
the identity of the ontology individual. The ontology does not assert
automatic cross-document identity. Coreference, where present, is an optional
identity link, and symmetry and transitivity are not declared on it.

## No event-value inference from co-occurrence

A numerical value linked from a value mention is not thereby an event
attachment. The ontology does not infer an event-value relation from
co-occurrence. Whether a particular population rule may still propose one is
an author decision about the rules, not an OWL entailment. The ontology
itself does not contain such an entailment.

## No event-time inference from publication time

`hasPublicationTime` relates a document to its publication time. It is not
functional in the sense of an OWL functional characteristic on the event-time
properties, and the ontology does not infer an event time from the publication
time. Document-creation times in the operational graphs are metadata times.

## No automatic cross-document identity

No axiom equates individuals because they share a surface form or a
cross-document operational link. The store supplement holds cross-document
operational relationships. Those relationships are not OWL identity.

## No automatic conversion from semantic role to financial relation

`sourceRoleLabel` stores a source semantic-role label on an event
participation. The scope note says it is not a financial-domain role and not
a public object property. A source role is not automatically a financial
relation.

## RDF status vocabulary is coarser than the decision layer

The ontology's validation individuals are `Accepted`, `RequiresReview`,
`Rejected`, and `Suppressed`. The manual-review individuals include
`ReviewRequired`, which is a different individual from `RequiresReview`. The
decision store additionally uses statuses and policies such as
`insufficient_evidence` and `structural_direct` that are not ontology
individuals. The RDF vocabulary is coarser than that decision layer.

## Experimental temporal semantics

Extension temporal relations (`precedes`, `follows`, `simultaneousWith`,
`occursDuring`, `includes`) are marked experimental in the ontology metadata
and in the module comment. Two inverse pairs are declared. `simultaneousWith`
is not declared symmetric. A reasoner entailment of an inverse temporal triple
is not independently extracted evidence. Symmetry of `simultaneousWith` and of
coreference is not asserted in this candidate.
