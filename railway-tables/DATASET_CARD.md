---
license: other
license_name: ogl-uk-3.0
license_link: https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/
pretty_name: "Railway tables: rows lost at a page break"
language:
  - en
size_categories:
  - n<1K
task_categories:
  - table-question-answering
---

# Railway tables: rows lost at a page break

The data for the TalkingDB railway table benchmark: two public UK rail documents and the saved table extraction output. The questions, expected answers, code and results are on GitHub: [talkingdb-benchmarks/railway-tables](https://github.com/TalkingDB/talkingdb-benchmarks/tree/main/railway-tables).

| File | What it is | Source | SHA-256 |
| :--- | :--- | :--- | :--- |
| `documents/raib-recommendations-index.pdf` | Index of RAIB recommendations, Rail Accident Investigation Branch. The benchmark uses pages 1 to 4 | [GOV.UK](https://www.gov.uk/government/publications/index-of-raib-recommendations) | `e07edb0f606e86cbdc2e75e845703251fb484f8952f3df6ab0a8000ee82e706f` |
| `documents/orr-passenger-rail-usage-oct-dec-2025.pdf` | Passenger rail usage, October to December 2025, Office of Rail and Road | [ORR data portal](https://dataportal.orr.gov.uk/media/2hto1os3/passenger-rail-usage-oct-dec-2025.pdf) | `aa769ae7dac8525a3625dc9db3a01486431313b30d8d0d74700b9df173351a10` |
| `results/extraction-raib-pages-1-4.json` | Tables read from pages 1 to 4 of the RAIB index by an open source PDF table extractor, cell by cell, with the page and the column name marks | Derived from the RAIB index | `cfbb2b5d38e2f6623fefa5f990aee0f2bf37dd99e0c314ce554d392e2d3c755d` |

Contains public sector information licensed under the Open Government Licence v3.0. The extraction output is derived from that information and carries the same licence.

To get the files with their hashes checked, run `python3 fetch_data.py` from the GitHub folder.
