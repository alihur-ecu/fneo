# Evaluation methodology

The fractions below are the recorded evaluation results. This note does not compute a new semantic precision or recall.

## Ontology quality

OWL 2 DL profile conformance, HermiT consistency, and the absence of named classes equivalent to `owl:Nothing` are recorded under `validation/owl/`. The canonical graph checksum matches the ontology file those reports name.

## Population

Thirty documents were processed. The corrected SHACL register marks 30 of 30 as release-eligible. Release eligibility is a validation status, not a correctness rate. Two population runs of the frozen rules produced the same semantic files (240 files compared, 0 different).

Three adapter defects were closed before that population: duplicate mention denotation, temporal span conflation as a shape failure, and cross-document identifier collision. The twelve collision rows stay outside scored denominators. They are not true negatives.

## Semantic metrics

MarketIndex precision and EquityMarket precision are the accepted-decision rates 61/64 and 12/15.

Market-change event precision is reported twice. The baseline is 31/50. The frozen-reference and post-adjudication views of the later rule cycle are both 25/26. Scoped recall stays 21/24. The two views agree because the labels that differ sit on decisions the later run does not accept.

Affected-market precision is 29/50 at baseline and 23/26 after the rule cycle. Scoped recall stays 6/19.

Precision and scoped recall use different universes. F1 is undefined. Corpus-wide recall is not claimed.

Value typing is a stratified sample: 188/207 rows labelled correct type and value. It is not corpus recall.

## Competency questions

FDQ-001 through FDQ-004 answer correctness is the review of the deduplicated graph. FDQ-005 on that graph judged trigger spans. The assertion-evidence FDQ-005 is 22/25 on the 27 assertion paths. Reviewed-reference alignment coverage is a separate completeness fraction and is not answer correctness. The five questions are not combined. Public labels are under `evaluation/public/`.
