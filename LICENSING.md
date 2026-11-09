# Licensing

This repository is not under one licence. The first matching row below is the
classification of a path. A file that contains Wikinews source text stays in
the source-text class even if it also contains authored labels or graph
structure.

The 30 operational TextGraphs were produced by TextGraphX from raw Wikinews articles and retained source-file metadata. They do not contain MEANTIME manual annotations. Article text is CC BY 2.5. MEANTIME packaging metadata is CC BY 4.0. The unchanged MEANTIME distribution licence is `third_party/MEANTIME/LICENSE.txt`. See `inputs/operational/SOURCE_NOTICE.md`.

Do not apply MIT or CC0 to source-bearing TextGraphs. Do not relicense a fixture whose header says CC0.

| Path pattern | Content type | Creator or source | Licence | Source text present | Third-party content present | Public release eligibility | Required attribution |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `src/**`, `scripts/**`, `reproduction/**`, `docker/**`, `*.py`, `*.sh` | Authored executable code | Ali HUR | MIT (`LICENSE-CODE`) | No | No | Eligible | Copyright (c) 2026 Ali HUR and the MIT notice |
| `research/financial_event_ontology/**` | Reproduction implementation imported by `reproduction/reproduce_clean.py` | Ali HUR | MIT (`LICENSE-CODE`) | No | No | Included as code | Copyright (c) 2026 Ali HUR and the MIT notice |
| `ontology/**`, `shapes/**`, `mappings/**`, `rules/**`, `queries/**`, `documentation/**`, `examples/**`, `competency_questions/**` | Authored semantic and research content | Ali HUR | CC BY 4.0 (`LICENSE-CONTENT`) | No | Vocabulary namespaces remain under their own terms | Eligible | Ali HUR, CC BY 4.0, indicate changes |
| `configs/**` | Study configuration | Ali HUR | CC BY 4.0 | No | No | Eligible | Ali HUR, CC BY 4.0 |
| `inputs/operational/textgraphs/**` | Operational TextGraphs | TextGraphX transformation of Wikinews articles; MEANTIME packaging metadata only | Article text CC BY 2.5; packaging metadata CC BY 4.0 | Yes | Yes | Eligible with article-level attribution | Article title, author, date, URL, CC BY 2.5; MEANTIME packaging separately; no endorsement |
| `population/**` | Publication views that may copy source spans | Study projection of the operational graphs | Same split as the operational graphs | Yes | Yes | Eligible with the same attribution | Wikinews CC BY 2.5 plus MEANTIME packaging notice |
| `evaluation/public/**` | Public evaluation labels without source passages | Ali HUR | CC BY 4.0 | No | No | Eligible | Ali HUR, CC BY 4.0 |
| `expected/**`, `validation/**`, `supplement/**` | Reference checksums, validation reports, store supplement metadata | Study outputs | CC BY 4.0 except where a file embeds source text, which stays CC BY 2.5 | Only if a retained literal is present | MEANTIME packaging fields where recorded | Eligible | As for the embedded class |
| `fixtures/**` | Synthetic fixtures | As stated in each file header | The header licence. CC0 headers stay CC0 | No | No | Eligible under the header | As stated in the header |
| `third_party/WIKINEWS/**` | Article-level attribution notices | Wikinews contributors, compiled here | Notice text CC BY 4.0; articles remain CC BY 2.5 | Attribution strings only | Yes | Eligible | Per-article CC BY 2.5 notice |
| `third_party/MEANTIME/LICENSE.txt` | Unchanged MEANTIME distribution licence | MEANTIME / NewsReader | CC BY 4.0, byte-unchanged | No | Yes | Eligible | Do not modify the file |
| `third_party/MEANTIME/**` except `LICENSE.txt` | Packaging attribution and citation | MEANTIME, with notes by Ali HUR | CC BY 4.0 | No | Yes | Eligible | Minard et al. 2016 and CC BY 4.0 |
| `reports/clean_reproduction.json` | Reproduction record | Study output | CC BY 4.0 | No | No | Included | Ali HUR, CC BY 4.0 |

Synthetic fixture headers remain authoritative for those files.
