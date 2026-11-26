# TalkingDB benchmarks

Open benchmarks for [TalkingDB](https://talkingdb.io/) tools on public documents. The benchmarks score results against explicit evidence, without a language model as judge.

Free to use and open source under [AGPL-3.0](LICENSE). Rerun them, change them, or point them at your own documents, and tell us where they break.

| Benchmark | What it tests | Result |
| :--- | :--- | :--- |
| [railway-tables](railway-tables) | Tables that run across PDF pages, on a public UK rail safety index | Standard extraction keeps 10 of 13 expected rows; with the TalkingDB page break fix, 13 of 13 |
| [ecommerce-rag](ecommerce-rag) | What a customer support RAG bot retrieves, on Indian consumer law and store policies | All primary evidence reaches the top 20 for 62.5% of questions, and the final top 4 for 31.8% |
| [telecom-acronyms](telecom-acronyms) | Acronyms with conflicting meanings across 3GPP specifications | TalkingDB Text-to-Tree shows an accepted definition row for 38 of 40 questions with 61% fewer input tokens than a prompt glossary; the small answer model picked by letter, so answer quality is not measured |

Built on the open source TalkingDB tools, starting with [module-ttt](https://github.com/TalkingDB/module-ttt).
