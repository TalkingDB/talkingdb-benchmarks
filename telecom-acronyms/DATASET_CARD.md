---
license: agpl-3.0
pretty_name: "Telecom acronyms: pick the right meaning, and cite it"
language:
  - en
size_categories:
  - 1K<n<10K
task_categories:
  - question-answering
configs:
  - config_name: outcomes
    data_files: outcomes.csv
    default: true
  - config_name: rerun_decisions
    data_files: results/balanced/per-run.jsonl
  - config_name: published_decisions
    data_files: results/evaluation/per-case.jsonl
  - config_name: published_text_to_tree_decisions
    data_files: results/ttt/scored/per-case.jsonl
---

# Telecom acronyms: pick the right meaning, and cite it

The data for the TalkingDB telecom acronym benchmark. One acronym can mean two different things in two 3GPP specifications; the benchmark asks whether a system puts the row that defines the right meaning in front of a model, and whether the model then chooses that meaning and cites the row. The method, code, images and summaries are on GitHub: [talkingdb-benchmarks/telecom-acronyms](https://github.com/TalkingDB/talkingdb-benchmarks/tree/main/telecom-acronyms).

**What the results show.** TalkingDB Text-to-Tree put an accepted definition row in front of the answer model for 38 of 40 answerable questions, with 205.5 input tokens per question against 529.9 for a glossary in the prompt. The small answer model chose whatever option sat at letter C in 359 of 371 published decisions, and in 1,377 of 1,449 decisions after every option was moved through every letter, so this data cannot compare methods on answer quality.

| File | What it is |
| :--- | :--- |
| `outcomes.csv` | One row per question and method (371 rows): the question, the expected answer and its PDF page, the rows shown, the published choice and verdict, and the rerun's choices. The default view. |
| `results/balanced/per-run.jsonl` | The 1,449 rerun decisions: every option at every letter once, with the option order, the rows shown, every option score, the choice and the verdict |
| `results/evaluation/per-case.jsonl` | The 318 published decisions for six methods |
| `results/ttt/scored/per-case.jsonl` | The 53 published decisions for TalkingDB Text-to-Tree |
| `results/ttt/rankings.json` | The rows Text-to-Tree returned for each question |
| `cases/evaluation.json`, `cases/development.json` | 53 evaluation questions in 10 acronym families (20 name the specification, 20 give a clue, 13 controls) and 27 development questions in 5 other families |
| `definitions.json` | 42 definition rows: acronym, expansion, specification, clause and page, each checked against the official PDF |
| `sources.json` | The nine ETSI editions of the 3GPP specifications, with URL, version and SHA-256 |

The specification PDFs are not included; they are free to download from ETSI but are not ours to republish. `python sources.py --fetch` in the GitHub folder downloads them and checks each one by SHA-256.

To get these files with their hashes checked, run `python fetch_data.py` from the GitHub folder. Then `python verify.py` rebuilds every decision from its saved option scores, recomputes every summary, and checks that `outcomes.csv` matches the raw decisions byte for byte. It needs no model and no network.

Licensed under AGPL-3.0, the same licence as the benchmark code.
