# Wikinews attribution

The 30 operational TextGraphs contain Wikinews article text under CC BY 2.5. `document_manifest.tsv` records the title, contributor, publication date, source URL, licence, and transformation notice. MEANTIME packaging metadata is recorded separately under CC BY 4.0. Annotated MEANTIME files are not included.

Each of the 30 graphs corresponds to one English Wikinews article in the
stock-market topic. `document_manifest.tsv` records the title, URL,
publication date, Wikinews author, graph checksum, and the statement that the
graph does not contain MEANTIME manual annotations.

Attribute the article when reusing a graph or a source-bearing file:

> "<title>" by <Wikinews author>, Wikinews, <publication date>, <URL>. Licensed under Creative Commons Attribution 2.5.

Authors recorded from the retained file metadata: Bawolff, Blood Red Sandman,
Cirt, Diego Grez Bot, Pi zero, Tempodivalse, Tom Morris, and TUFKAAP.

The raw text compared for this record is the `<raw>` element of each
MEANTIME raw NAF file. Those files contain no annotation layers. Graph text
matches that raw text after the pipeline joins the title, date, and body with
sentence punctuation. Two documents (131162 and 141225) differ only by that
punctuation, not by a different article. All 30 titles, URLs, authors, and
creation times match.

Checksums of the raw NAF files are in `raw_naf_checksums.tsv`. Those files are
not copied into the package. The source text that is copied is inside the
operational TextGraphs.
