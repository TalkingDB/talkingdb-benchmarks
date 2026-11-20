# TalkingDB benchmarks

Open benchmarks for [TalkingDB](https://talkingdb.io/) tools on public documents. The benchmarks score results against explicit evidence, without a language model as judge.

Free to use and open source under [AGPL-3.0](LICENSE). Rerun them, change them, or point them at your own documents, and tell us where they break.

| Benchmark | What it tests | Result |
| :--- | :--- | :--- |
| [railway-tables](railway-tables) | Tables that run across PDF pages, on a public UK rail safety index | Standard extraction keeps 10 of 13 expected rows; with the TalkingDB page break fix, 13 of 13 |
| [telecom-acronyms](telecom-acronyms) | Acronyms with conflicting meanings across 3GPP specifications | 13 of 40 grounded answers from a prompt glossary, 11 of 40 using TalkingDB Text-to-Tree and 61% fewer input tokens |

Built on the open source TalkingDB tools, starting with [module-ttt](https://github.com/TalkingDB/module-ttt).
