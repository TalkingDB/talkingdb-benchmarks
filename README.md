# TalkingDB benchmarks

Open benchmarks for [TalkingDB](https://talkingdb.io/) tools, on public documents, scored exactly against expected rows and pages. No language model writes or judges the results.

Free to use and open source under [AGPL-3.0](LICENSE). Rerun them, change them, or point them at your own documents, and tell us where they break.

| Benchmark | What it tests | Result |
| :--- | :--- | :--- |
| [railway-tables](railway-tables) | Tables that run across PDF pages, on a public UK rail safety index | Standard extraction keeps 10 of 13 expected rows; with the TalkingDB page break fix, 13 of 13 |
| [ecommerce-rag](ecommerce-rag) | What a customer support RAG bot retrieves, on Indian consumer law and store policies | All primary evidence reaches the top 20 for 40 of 64 questions, and the final top 4 for 31.8% |

Built on the open source TalkingDB tools, starting with [module-ttt](https://github.com/TalkingDB/module-ttt).
