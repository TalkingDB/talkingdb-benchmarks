# E-commerce RAG: what a support bot retrieves

A customer support bot answers questions about returns, refunds, warranties and consumer rights from six documents (Indian consumer law, Meesho store policies, a Havells product manual). This benchmark asks it a set of support questions and checks, word for word, whether the passages it retrieves hold the evidence each answer needs. It measures the pipeline as it is today; no fix is applied.

The documents and the questions are on Hugging Face: [TalkingDB/ecommerce-rag](https://huggingface.co/datasets/TalkingDB/ecommerce-rag).

## Run it

Linux, WSL or Git Bash on Windows, with `git` and [uv](https://docs.astral.sh/uv/) (uv provides Python).

```bash
git clone https://github.com/TalkingDB/talkingdb-benchmarks.git && cd talkingdb-benchmarks/ecommerce-rag
bash setup.sh
OPENAI_API_KEY=sk-... bash run.sh
```

`setup.sh` fetches the documents and questions from pinned dataset commits and checks them by SHA-256, checks out the bot's code at the commit in [AGENT_COMMIT.txt](AGENT_COMMIT.txt) and installs pinned dependencies. `run.sh` asks every question three times (about 20 minutes with the current set) and rewrites `results/openai/` and the result below.

| Option | What it does |
| :--- | :--- |
| `--runs 1`, `--only Q01,Q68` | A single run, or a few questions (written to `results/openai-partial/`) |
| `--reingest` | Rebuild the index |
| `--answers` | Also have the bot answer from the same top 4, and check each answer cites its evidence |
| `--local` | Use Ollama (`bge-m3`, `qwen3.5:9b`) instead of OpenAI; results go to `results/local/` |

No API key? `python3 fetch_data.py && python3 pipeline/score.py` re-scores the saved run with plain Python.

## How it works

The benchmark runs the bot's own code ([ecommerce-rag-agent](https://github.com/TalkingDB/ecommerce-rag-agent)), unchanged:

1. **Index.** The PDFs are cut into passages of about 1,000 characters (277 in all) and embedded into a local Qdrant index.
2. **Rewrite follow-ups** into standalone questions using the conversation so far.
3. **Search.** Vector search returns the 20 closest passages.
4. **Rerank.** A language model scores the 20; the best 4 above the cutoff are what the bot answers from.

Both the top 20 and the final top 4 are recorded and scored for every question and run.

## The result

<!-- result:start -->
Run `openai`, 2026-11-20: `gpt-4o-mini` (openai), `text-embedding-3-small` embeddings, LLM reranker (`gpt-4o-mini`), 20 candidates, top 4, rerank cutoff 0.4, 3 runs ([config](results/openai/config.json)).

| Stage | Questions | Result |
| :--- | :--- | :--- |
| Top 20, after vector search | 64 | 40 (62.5%) have all primary evidence: PASS 40, PARTIAL 13, FAIL 11 |
| Top 4, after the reranker (what the bot answers from) | 64 | 31.8% per run (20 to 21 of 64): PASS 21, FAIL 43 by most runs |
| No answer in the documents | 6 | 3 declined; 3 let passages through to the answer step (RISK) |

In 24 of the 64 questions, search never puts a primary piece of evidence in the top 20, so no reranker could keep it. In 19 more, every primary piece is in the top 20 but the reranker drops at least one. The top 4 changed between runs for 32 of the 70 questions, so a question can pass in one run and fail in the next.


Per question, with each stage's verdict and the passages returned: [per_question.csv](results/openai/per_question.csv). Every metric, mean and range over the runs: [summary.json](results/openai/summary.json).
<!-- result:end -->

To read the questions and their evidence, open [questions-with-chunks.xlsx](results/openai/questions-with-chunks.xlsx): it lists the chunk labels for each stage, and the text of every chunk is in its Chunks tab. Its top 20, top 4 and verdict columns are from an earlier run (top 4: 33.3%); for this run, use [per_question.csv](results/openai/per_question.csv).

## Scoring

Each question lists **primary** evidence (what the answer cannot do without) and **supporting** evidence (reported, not required), each as a document, page and exact quote. A retrieved passage counts only when it comes from the same document and contains the quote word for word, ignoring whitespace. Matching by quote, not passage number, keeps the evidence valid if the chunker or embedding model changes.

| Stage | PASS | PARTIAL | FAIL |
| :--- | :--- | :--- | :--- |
| Top 20 (search) | every primary piece found | some found | none found |
| Top 4 (after reranking) | every primary piece kept, in most runs | | otherwise |

Some questions have no answer in the documents: they pass when nothing gets through the reranker, and are a RISK when passages still get through. No language model writes or judges the score; `pipeline/score.py` has a self check and re-scores the saved run to the same [summary.json](results/openai/summary.json).

## Limits

1. A small question set: each question with evidence moves the score by 100 divided by their number (1.6 points with the current set), so treat differences of a few questions as noise.
2. The evidence was chosen by one team and reviewed once; some choices are judgement calls.
3. Strict scoring: a near-duplicate of the primary passage does not count, so real retrieval is somewhat better than the headline.
4. Retrieval only. `--answers` checks that answers cite their evidence, not that they are right.
5. OpenAI models change over time and are not fully repeatable; a rerun lands near the published numbers, not on them.

## Files

| Path | What it is |
| :--- | :--- |
| `pipeline/` | `benchmark.py` runs the questions, `score.py` scores them, `report.py` writes the result section |
| `results/openai/` | The published run: index, raw runs, config, summary, per-question verdicts, spreadsheet |
| `documents/sources.json` | Document titles and links; the PDFs are fetched into `documents/` |
| `setup.sh`, `run.sh`, `requirements.txt`, `AGENT_COMMIT.txt` | Setup and run, pinned |
| `fetch_data.py`, `DATA.txt`, `DATASET_CARD.md` | Data files on Hugging Face with their SHA-256 and dataset commit, and the dataset card |

Built by [TalkingDB](https://talkingdb.io/). Code under [AGPL-3.0](../LICENSE).
