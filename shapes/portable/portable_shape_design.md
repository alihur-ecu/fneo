# Portable shape design

## Problem

The original core, extension, and supplemental shapes state `sh:severity` for many SPARQL checks on the blank node that is the object of `sh:sparql`. The project-local checker reads that nested severity. pySHACL 0.40.2 reads `sh:severity` on the shape that produces the validation result. When the node shape has no severity, pySHACL 0.40.2 applies `sh:Violation`.

That is why an earlier packaging run reported the same 1,454 system-accepted results as 0 violations, 1,350 warnings, and 104 informational results in the local checker, and as 1,454 violations in pySHACL 0.40.2. The messages were the same. The severity assignment differed. Property-shape constraints already carry `sh:severity` on the property shape and were not the source of that discrepancy.

## Normative interpretation used here

For pySHACL 0.40.2, the effective severity is `sh:severity` on the node shape or property shape that produces the result. Severity on a nested SPARQL constraint resource is not what that engine applies.

For the project-local checker, the effective severity of a SPARQL constraint is `sh:severity` on the constraint resource. The effective severity of a property constraint is `sh:severity` on the property shape.

## Rewrite

Warning and information SPARQL checks are moved to a dedicated node shape:

- the same `sh:targetClass`;
- the same SELECT text;
- the same message;
- `sh:severity` on the new node shape;
- the same `sh:severity` repeated on the nested SPARQL constraint, so both engines assign the warning or information severity.

The derived shape IRI is `https://w3id.org/fneo/shape/portable-{originalLocalName}-{queryHash12}`.

Violation SPARQL checks stay on their original shapes. pySHACL already treats them as violations, and the local checker reads `sh:Violation` from the nested constraint. They are not weakened and are not relabelled as warnings.

No SELECT query, path, prefix intent, or message was edited. The analysis table is `validation/reports/shacl_portability_analysis.csv`. The IRI mapping is `original_to_portable_shape_crosswalk.csv`.

The candidate shapes in `fneo-candidate-shapes-portable.ttl` are new. There was no original candidate shape file to port. They also state severity on the producing shape and on the nested constraint.

## What the rewrite does not do

It does not convert warnings or informational findings into violations. It does not drop results. It does not change which focus nodes the original SELECT text returns. A difference in the result-shape IRI is expected, because the producing shape is the new dedicated shape. A difference in the focus node, message, or severity category is not expected on the same data graph.

The shapes use SHACL 1.0 constructs already present in the original files: `sh:NodeShape`, `sh:targetClass`, `sh:property`, `sh:sparql`, `sh:select`, `sh:severity`, and `sh:message`. They do not require SHACL-AF or SHACL 1.2.

Original files under `validation/original/` are byte-identical copies. This directory does not replace them.
