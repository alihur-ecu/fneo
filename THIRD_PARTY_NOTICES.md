# Third-party notices

## Wikinews

Article text in the operational TextGraphs is Wikinews text under CC BY 2.5. See `inputs/operational/SOURCE_NOTICE.md` and `third_party/WIKINEWS/`.

Article-level records are also in `third_party/WIKINEWS/`.

## NewsReader MEANTIME corpus

MEANTIME supplies packaging metadata for the 30-document English stock-market topic, including public identifiers and corpus filenames. That metadata is CC BY 4.0. The copied distribution licence is `third_party/MEANTIME/LICENSE.txt`. Annotated MEANTIME files are not included.

The English stock-market topic is one of four 30-document English topics. It is not the complete MEANTIME corpus. MEANTIME manual annotations were used in earlier published TextGraphX evaluation work. That prior evaluation is not repeated here.

`third_party/MEANTIME/SOURCE_RECORD.md` records the byte-for-byte copy of the original distribution licence into `third_party/MEANTIME/LICENSE.txt` on 2026-11-07. This notice is not that file. The annotated MEANTIME files are not included in the release.

## TextGraphX

TextGraphX produced the operational nodes, edges, deterministic identifiers,
derived features, and graph structures (Hur, Janjua, and Ahmed 2024, Expert
Systems with Applications, 239, 122269). Those structures are transformed
research outputs. Where they carry Wikinews text or MEANTIME packaging
metadata, the corresponding attribution still applies. This package does not
include the TextGraphX pipeline and does not regenerate the operational graphs
from the articles.

## Ontology vocabulary namespaces

The ontology uses W3C RDF, RDFS, OWL, and Dublin Core terms, plus a FOAF
prefix for the creator resource. Those vocabularies remain under their own
terms. `https://w3id.org/fneo/` is not registered.
