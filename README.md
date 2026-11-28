<!-- short-readme -->
<h1 align="center">TalkingDB benchmarks</h1>

<p align="center"><b>Open benchmarks for TalkingDB tools, scored exactly. No language model judges anything.</b></p>

<p align="center"><a href="#try-it">Try it</a> · <a href="docs/reference.md">Full reference</a></p>

<p align="center"><a href="https://github.com/TalkingDB/talkingdb-benchmarks/stargazers"><img src="https://img.shields.io/github/stars/TalkingDB/talkingdb-benchmarks?style=social" alt="GitHub stars"></a> <a href="https://www.gnu.org/licenses/agpl-3.0.html"><img src="https://img.shields.io/badge/license-AGPL--3.0-blue" alt="AGPL-3.0"></a></p>

<p align="center">
  <img src="docs/images/demo.gif" alt="Animated demo: a railway safety question, the row standard PDF extraction loses at a page break, the same query with and without the fix (2 of 3 rows against 3 of 3), the whole table scored, and the ecommerce-rag result of 40 of 64">
</p>
<p align="center"><sub>Every figure is read from the results files in this repo, with its denominator.</sub></p>

Each benchmark runs on public documents and checks the output row by row and page by page against expected answers. Rerun them, change them, or point them at your own documents.

## What it does

- [railway-tables](railway-tables): rows that standard PDF table extraction loses at page breaks, and the fix.
- [ecommerce-rag](ecommerce-rag): what a support bot actually retrieves, question by question.
- Every figure comes with its denominator, in the results files.

## Try it

```bash
git clone https://github.com/TalkingDB/talkingdb-benchmarks.git
cd talkingdb-benchmarks/railway-tables    # or ecommerce-rag
bash setup.sh
bash run.sh
```

How to read a result and add a benchmark are in the [full reference](docs/reference.md).

## Where it fits

Runs [module-ttt](https://github.com/TalkingDB/module-ttt) and related tools against public documents.

## Learn more

| Page | Read it to |
| :--- | :--- |
| [Full reference](docs/reference.md) | read everything that used to be on this page |

## Support TalkingDB

If talkingdb-benchmarks saved you time, please [give it a star](https://github.com/TalkingDB/talkingdb-benchmarks) ⭐. Stars help other developers find the project.

Found a bug, or a document it gets wrong? [Open an issue](https://github.com/TalkingDB/talkingdb-benchmarks/issues/new). We are always here to help and open to a conversation. Explore the TalkingDB applications at [talkingdb.io](https://talkingdb.io/#applications).
