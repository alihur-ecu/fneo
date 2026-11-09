# Licensing evidence for the NewsReader MEANTIME corpus

This note records what was consulted. It does not state a legal conclusion
beyond those documents.

## Source files checked for a licence

The raw NAF articles used to check the 30 stock-market documents did not contain a licence file or a corpus README. No CC BY 4.0 licence file was recovered from that article archive.

The experiment uses the 30 files in `corpus_stock/`. Their document
identifiers, titles, URLs, and dates are listed in `document_manifest.tsv`
at the root of this package. Those 30 documents are the complete English
stock-market topic.

## Public licensing evidence

Accessed 5 November 2026.

1. NewsReader project data page, "The NewsReader MEANTIME corpus",
   `http://www.newsreader-project.eu/results/data/wikinews/`.
   The live host returned HTTP 503 on 5 November 2026. The same page was
   read from the Internet Archive capture
   `https://web.archive.org/web/20160315000000/http://www.newsreader-project.eu/results/data/wikinews/`.
   Quoted statement:

   > The NewsReader MEANTIME corpus is licensed under a Creative Commons Attribution 4.0 International License.

   The page links to `http://creativecommons.org/licenses/by/4.0/`.
   This quotation is preserved provider documentation. It is not a licence
   file recovered from the local archive, and it is not represented here as
   a README that was inside the local NAF directory.

2. LINGUIST List 27.1177, 7 March 2016, Manuela Speranza,
   `https://linguistlist.org/issues/27/1177/`.
   Quoted statement:

   > Developed within the EU-funded project NewsReader, it is licensed under a Creative Commons Attribution 4.0 International License.

3. Fondazione Bruno Kessler NLP research group,
   `https://nlplab.fbk.eu/tools-and-resources/lexical-resources-and-corpora/newsreader-meantime-corpus`.
   Quoted statement:

   > Distribution: The NewsReader MEANTIME corpus is licensed under a CC-BY license from the dedicated page on the NewsReader website.

   This page names CC-BY and points to the NewsReader page. It does not
   itself print the version string "4.0".

4. WITAC distribution note, the Italian section of MEANTIME,
   `https://nlplab.fbk.eu/tools-and-resources/lexical-resources-and-corpora/witac`.
   Quoted statement:

   > As part of the NewsReader MEANTIME corpus, WItaC is licensed under a Creative Commons Attribution 4.0 International License.

## What this evidence supports in the package

Those quotations describe the annotated MEANTIME distribution. This repository includes packaging metadata and the byte-copied `LICENSE.txt` only. See `SOURCE_RECORD.md`. Operational TextGraphs contain Wikinews text under CC BY 2.5 and are not placed under MIT or CC0. Study code is under `LICENSE-CODE`.
