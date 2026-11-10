# W3 verification results

Product revision: `3076d3dd`. Only tools/tests and the append-only W3 log change.

Independent profile verification of a controlled EXReader DOCX export: **4 PASS, 8 FAIL, 2 WARN**. The same statuses occur for all three real output DOCX files.

| Check | Result |
| --- | --- |
| package_xml | PASS |
| content_types | PASS |
| root_relationship | PASS |
| section_present | PASS |
| section_nonempty | FAIL |
| paragraph_properties | FAIL |
| double_spacing | FAIL |
| font_times_new_roman | FAIL |
| font_size_12pt | FAIL |
| letter_page_size | FAIL |
| one_inch_margins | FAIL |
| header_part | WARN |
| header_used | WARN |
| header_page_field | FAIL |

Full controlled-sample failure XML: [profile.txt](evidence/profile.txt).

## Real DOCX round trips

Values are independent original ZIP/XML -> exported ZIP/XML. FAIL includes increases; none are treated as equivalent.

| Document | Paragraphs | Characters | Tables | Images | Footnotes | Section margins | Failed metrics |
| --- | --- | --- | --- | --- | --- | --- | --- |
| minitab-ch10 | 336 -> 189 | 13865 -> 13721 | 10 -> 0 | 17 -> 0 | 0 -> 0 | 1 sections with explicit margins -> 1 with all four absent | 5/6 |
| soci-syllabus | 117 -> 103 | 5555 -> 5557 | 2 -> 0 | 0 -> 0 | 0 -> 0 | 5 sections with explicit margins -> 1 with all four absent | 4/6 |
| ohchr-40-69 | 209 -> 208 | 71205 -> 71315 | 2 -> 0 | 0 -> 0 | 5 -> 0 | 1 sections with explicit margins -> 1 with all four absent | 5/6 |

**14/18 comparisons FAIL**: 12 reductions/lost-margin comparisons plus two character-count increases.

| Document | Metric | Exact loss or drift |
| --- | --- | --- |
| minitab-ch10 | paragraphs | delta=-147; count reduction=147 |
| minitab-ch10 | characters | delta=-144; count reduction=144 |
| minitab-ch10 | tables | delta=-10; count reduction=10 |
| minitab-ch10 | images | delta=-17; count reduction=17 |
| minitab-ch10 | section_margins | lost sections=0; changed/missing section indices=[1]; every output margin attribute is absent |
| soci-syllabus | paragraphs | delta=-14; count reduction=14 |
| soci-syllabus | characters | delta=+2; count reduction=0 |
| soci-syllabus | tables | delta=-2; count reduction=2 |
| soci-syllabus | section_margins | lost sections=4; changed/missing section indices=[1, 2, 3, 4, 5]; every output margin attribute is absent |
| ohchr-40-69 | paragraphs | delta=-1; count reduction=1 |
| ohchr-40-69 | characters | delta=+110; count reduction=0 |
| ohchr-40-69 | tables | delta=-2; count reduction=2 |
| ohchr-40-69 | footnotes | delta=-5; count reduction=5 |
| ohchr-40-69 | section_margins | lost sections=0; changed/missing section indices=[1]; every output margin attribute is absent |

Margin tuple order: **top / right / bottom / left**, in twips.

| Document | Original per-section margins | Exported |
| --- | --- | --- |
| minitab-ch10 | S1=1440/2160/1440/3240 | S1=null/null/null/null |
| soci-syllabus | S1=1440/1440/1440/1440; S2=1440/1440/1440/1440; S3=1440/1440/1440/1440; S4=1440/1440/1440/1440; S5=1440/1440/1440/1440 | S1=null/null/null/null |
| ohchr-40-69 | S1=1417/1134/1134/1134 | S1=null/null/null/null |

All three SDK read -> export -> re-read text hashes PASS. All three independent original/export text hashes differ. The manual loses all 17 image payloads. Tables and footnotes are flattened into text: equal SDK text hashes hide those losses. Paragraph counts include empty paragraphs, so a paragraph-count reduction is structural drift, not a claim that every removed paragraph contained text.

Source hashes and coverage: [corpus.json](corpus.json). Full count/hash evidence: [roundtrip.json](evidence/roundtrip.json). Inputs remain local; no source DOCX text is committed. The public UN report is [A/HRC/40/69](https://www.ohchr.org/sites/default/files/HRBodies/HRC/RegularSessions/Session40/Documents/A_HRC_40_69.docx).

## PDF equivalence and self-tests

LibreOffice/PDF text comparison: **SKIP**. Neither `soffice` nor `pdftotext` is available. The optional comparison path has a mocked self-test for page-count and later-page text differences; this is not a LibreOffice execution result.

Self-tests: **8/8 PASS**, including valid DOCX -> CLI exit 0, deliberately removed page size -> CLI exit 1 plus failure XML, per-requirement mutations, all six intentional metric losses, same-length text substitution and PDF comparison logic. [Self-test log](evidence/selftest.txt).

## Protected regression

19/19 real books, **11,318 pages**, 8,648,571 glyphs; **0 changed page counts, 0 changed page hashes** against the pre-existing integrated baseline. Full per-page hashes are retained in [before](evidence/realbooks-before.json.gz) and [after](evidence/realbooks-after.json.gz); [comparison](evidence/realbooks.diff.json).

Layer audit: PASS, 119 objects, zero inverse symbol references/includes. [Provenance and reproduction commands](evidence/provenance.json).

Full native CTest: **249/250 PASS** in 309.71 s. The sole failure is `sdk-release`: the MinGW SDK has `libexreader.dll.a`, while the packaged README quickstart invokes MSVC and requests `lib\exreader.lib` (`LNK1181`). No release/product files were changed. [Complete native test log](evidence/native-ctest.txt).
