# Namespace and W3ID readiness

## Identifiers in the ontology file

| Item | Value | Source |
| --- | --- | --- |
| Prefix | `fneo:` | Ontology header |
| Namespace | `https://w3id.org/fneo/` | Ontology header |
| Ontology IRI | `https://w3id.org/fneo/ontology` | `owl:Ontology` subject |
| Version IRI | `https://w3id.org/fneo/ontology/0.1.0-rc2` | `owl:versionIRI` |
| Shapes stem | `https://w3id.org/fneo/shape/` | Shape files. This is not a second term namespace. |

The ontology file states that the title, acronym, and namespace are provisional and that the W3ID has not been registered.

## Lookup

On 2026-10-31 a request to `https://w3id.org/fneo/` returned HTTP 404. The stem is not registered and not operational. An unchecked or failed lookup is not treated as registration. This candidate does not claim that the IRI resolves.

## Content negotiation

No content negotiation is deployed. The proposed targets, once a repository and a W3ID redirect exist, are:

| Request | Proposed target |
| --- | --- |
| HTML documentation | A public documentation page for the ontology |
| `text/turtle` | `ontology/fneo.ttl` |
| `application/rdf+xml` | `ontology/fneo.owl` |
| `application/ld+json` | `ontology/fneo.jsonld` |

Those files are in this candidate. They are not served from `w3id.org`.

## Repository and redirect

The public repository URL is `REQUIRED_BEFORE_PUBLIC_RELEASE_REPOSITORY`. A proposed redirect configuration is in `reproducibility/w3id-proposal/`. It has not been submitted to the W3ID maintainers.

## Registration prerequisites still open

1. A confirmed personal or organisational author record.
2. A public repository that will host the vocabulary files.
3. Approval of the licence split, including corpus-derived graphs.
4. A decision to register `https://w3id.org/fneo/` or to change the namespace before registration.
5. Redirect rules from the ontology IRI and the version IRI to the hosted serialisations.
6. A final check that the registered redirect returns the ontology document rather than 404.

Until those items are done, the namespace status is `REQUIRED_BEFORE_PUBLIC_RELEASE_W3ID_STATUS`: checked, HTTP 404, not registered.
