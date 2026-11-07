# Future changes

Candidates for ontology version 0.2.0. None of these changes are implemented
in 0.1.0-rc2.

- Boolean or controlled representation for `materialisationEligibility`, which
  is currently an `xsd:string` datatype property.
- IRI-valued canonical temporal relation, in place of the string-valued
  `canonicalPublicRelation`.
- Possible separate `InsufficientEvidence` and `OutOfScope` status
  individuals. They are not in the 0.1.0-rc2 controlled lists.
- Review of `RequiresReview` versus `ReviewRequired`. Both individuals exist
  and are not the same resource.
- Review of coreference symmetry. Symmetry is not declared.
- Review of `simultaneousWith` symmetry. Symmetry is not declared, and the
  temporal extension is experimental.
- Stronger PROV-O alignment. Local provenance properties are not replaced by
  PROV-O in this candidate.
- Possible evidence-to-document relation beyond the current evidence and
  document resources.
- Possible SKOS or VANN metadata migration. Local annotation properties stand
  in for definition, scope note, and example, and the preferred-namespace
  metadata is local rather than VANN.
- Possible physical separation of the temporal module. The temporal vocabulary
  remains in the same ontology file.
