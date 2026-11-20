# Result: openai

Run `openai`, 2026-11-20: `gpt-4o-mini` (openai), `text-embedding-3-small` embeddings, LLM reranker (`gpt-4o-mini`), 20 candidates, top 4, rerank cutoff 0.4, 3 runs ([config](results/openai/config.json)).

| Stage | Questions | Result |
| :--- | :--- | :--- |
| Top 20, after vector search | 64 | 40 (62.5%) have all primary evidence: PASS 40, PARTIAL 13, FAIL 11 |
| Top 4, after the reranker (what the bot answers from) | 64 | 31.8% per run (20 to 21 of 64): PASS 21, FAIL 43 by most runs |
| No answer in the documents | 6 | 3 declined; 3 let passages through to the answer step (RISK) |

In 24 of the 64 questions, search never puts a primary piece of evidence in the top 20, so no reranker could keep it. In 19 more, every primary piece is in the top 20 but the reranker drops at least one. The top 4 changed between runs for 32 of the 70 questions, so a question can pass in one run and fail in the next.


Per question, with each stage's verdict and the passages returned: [per_question.csv](results/openai/per_question.csv). Every metric, mean and range over the runs: [summary.json](results/openai/summary.json).

## All metrics

| Metric | Mean | Range over runs |
| :--- | ---: | :--- |
| All primary evidence in top 20 | 62.5% | 62.5% to 62.5% |
| Primary recall in top 20 | 72.7% | 72.7% to 72.7% |
| All primary evidence in top 4 (headline) | 31.8% | 31.2% to 32.8% |
| Primary recall in top 4 | 48.4% | 47.7% to 50.0% |
| All primary in top 4 by vector order alone | 27.1% | 26.6% to 28.1% |
| Evidence recall in top 4, capped at 4 | 40.3% | 39.8% to 41.1% |
| Top 4 passages that are evidence | 34.7% | 34.2% to 35.4% |
| Mean reciprocal rank of first primary passage | 0.489 | 0.474 to 0.516 |
