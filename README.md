# TalkingDB benchmarks

Open benchmarks for [TalkingDB](https://talkingdb.io/) tools, on public documents, scored exactly against expected rows and pages. No language model writes or judges the results.

Free to use and open source under [AGPL-3.0](LICENSE). Rerun them, change them, or point them at your own documents, and tell us where they break.

| Benchmark | What it tests | Result |
| :--- | :--- | :--- |
| [railway-tables](railway-tables) | Tables that run across PDF pages, on a public UK rail safety index | Standard extraction keeps 10 of 13 expected rows; with the TalkingDB page break fix, 13 of 13 |

Built on the open source TalkingDB tools, starting with [module-ttt](https://github.com/TalkingDB/module-ttt).
