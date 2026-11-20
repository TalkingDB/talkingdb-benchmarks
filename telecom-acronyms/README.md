# TalkingDB Telecom Acronym Benchmark

When one acronym has two valid meanings, can a system choose the right expansion and cite the specification that supports it? This pilot compares a glossary in the system prompt with TalkingDB Text-to-Tree, lexical retrieval, dense retrieval and a scoped prototype. Every arm uses the same small answer model and fixed choices.

## Results

**TalkingDB Text-to-Tree used 61% fewer input tokens** than the budgeted prompt glossary. It got 11 grounded answers and the glossary got 13. The quality difference is uncertain. Both guessed on 10 of 13 controls.

| Arm | Grounded answers, out of 40 | Correct abstentions, out of 13 | Mean input tokens |
| :--- | ---: | ---: | ---: |
| No glossary | 0 | 3 | 139.9 |
| Glossary in system prompt | **13** | 3 | 529.9 |
| TalkingDB Text-to-Tree | 11 | 3 | **205.5** |
| Full glossary | 12 | 3 | 629.1 |
| BM25 | 11 | 3 | 218.0 |
| BGE dense | 12 | 3 | 218.9 |
| Scoped prototype | 12 | 3 | 217.4 |

- TTT found an accepted source among its top three elements in **38 of 40** answerable cases. The two misses were both named SCS questions. Against the glossary, TTT had 0 paired wins, 2 losses and 38 ties. Its family bootstrap interval relative to the glossary was −12.5 to 0 percentage points. [TTT summary](results/ttt/scored/summary.json) · [Raw TTT retrieval](results/ttt/rankings.json) · [TTT decisions](results/ttt/scored/per-case.jsonl)
- On the 20 named questions, the budgeted glossary and scoped prototype each got 7 right. On the 20 domain clue questions, the glossary got 6 and the prototype got 5. The prototype had 0 paired wins, 1 loss and 39 ties. Its family bootstrap interval relative to the glossary was −7.5 to 0 percentage points.
- BM25 and the scoped prototype each found an accepted citation in their first three rows for all 40 answerable cases. Even with that evidence available, the model frequently chose the wrong expansion or abstained. Each arm guessed on 10 of 13 controls. A grounded production answer would need a check that the cited row was actually supplied and applicable.
- The [summary](results/evaluation/summary.json) includes the wrong expansions, citation errors, breakdown by case type, paired results and local timing. The [318 individual decisions](results/evaluation/per-case.jsonl) record the visible evidence and scored options. Timing includes selection and prompt construction. It excludes model loading and the up front BGE encoding. The local run made zero paid API calls.

## Repeat the evaluation

Use Python 3.13 and `curl`. The downloads include publicly available standards and model weights. They stay in `.cache/`.

```sh
python -m pip install -r requirements.txt
python sources.py --fetch --model
python -m unittest -v
```

For the dense comparison, install `sentence-transformers==5.2.0` and `torch==2.9.1` with a CPU build of PyTorch. Download the pinned BGE repository to `.cache/bge` using `hf download BAAI/bge-small-en-v1.5 --revision 5c38ec7c405ec4b44b94cc5a9bb96e735b38267a --local-dir .cache/bge`. Then run:

```sh
python benchmark.py --dense-dir .cache/bge --threads 8 --out results/repeat
```

Use a fresh output directory for each run. Omit `--dense-dir` to run the other arms. Use `--retrieval-only` for an evidence ranking check without the answer model. `--split development` selects the development families.

## Run TalkingDB Text-to-Tree

Use the [railway setup](../railway-tables/README.md) on Linux or WSL. The runner checks the five source checkouts against the [same pins](../railway-tables/TTT_COMMITS.txt). From `telecom-acronyms/`, rank the evidence with that environment, then score the answers using the pinned model set up above.

```sh
../railway-tables/.venv-ttt/bin/python ttt_rank.py \
  --ttt-src ../railway-tables/ttt-src --out results/ttt-repeat/rankings.json
python ttt_evaluate.py --rankings results/ttt-repeat/rankings.json --out results/ttt-repeat/scored
```

TTT indexes the same 42 verified abbreviation rows as nine separate tables. The benchmark uses the named specification to choose a graph when the question supplies it. Otherwise, TTT ranks over all nine graphs. It takes up to three evidence rows from TTT’s first three returned elements. The answer model and scorer are shared across the experiments. This measures the existing TalkingDB retrieval engine on prepared glossary rows. Whole PDF ingestion is outside this comparison.

## Cases and evidence

- **80 cases across 15 acronym families.** There are 60 questions with answers and 20 controls. The evaluation has **53 cases in 10 families**. Of these, 20 name the specification, 20 give a domain clue, 10 lack enough context to disambiguate and 3 lack evidence in the named scope.
- **42 verified definition rows across nine ETSI versions of 3GPP specifications.** The [manifest](sources.json) pins official URLs, editions and file hashes. Each [definition](definitions.json) records its clause, one based PDF page and printed page. The verifier checks the text and pagination against the PDFs. The PDFs are downloaded from ETSI and kept out of Git.
- **Example collision.** CA is Carrier Aggregation in [TS 38.521-2 v19.2.0, clause 3.3, printed page 23](https://www.etsi.org/deliver/etsi_ts/138500_138599/13852102/19.02.00_60/ts_13852102v190200p.pdf#page=24) and Certification Authority in [TS 33.310 v18.4.0, clause 3.2, printed page 12](https://www.etsi.org/deliver/etsi_ts/133300_133399/133310/18.04.00_60/ts_133310v180400p.pdf#page=13).

## What each arm sees

All arms receive the same question and shuffled expansion and citation options, including `NONE`. The options come from the known definitions for that acronym. The model chooses a letter from the options. This measures controlled selection with citations.

| Arm | Evidence in the prompt |
| :--- | :--- |
| No glossary | The options only. Choosing an expansion without supplied evidence earns no grounded credit. |
| Glossary in system prompt | All available definitions for the named scope, or the mixed glossary when scope is implicit. Under the budget, rows for the requested acronym go first, including competing meanings. |
| Full glossary | The same glossary at its natural size, with the definitions grouped by specification. |
| BM25 | The three highest ranked definition rows. BM25 searches the acronym, expansion and document scope summary. |
| BGE dense | The three highest cosine matches over the same evidence pool. |
| TalkingDB Text-to-Tree | Up to three definition rows from the first three results returned by the pinned TTT engine. |
| Scoped prototype | An exact acronym filter followed by BM25 ranking. The named specification is a hard scope boundary. Without a named scope, competing senses stay eligible. |

The budgeted arms have a 768 input token cap, including instructions, options and the glossary. Full glossary is the natural size control. All retrievers use named scope when the question provides it. For implicit queries, the retriever can use only the question and shared corpus metadata.

## Annotated example

**Question (AMF-04).** “In the bits carried by AUTN during AKA, what does AMF stand for?”

| Arm | Evidence and answer |
| :--- | :--- |
| Glossary in system prompt | Saw both definitions. Selected **Authentication Management Field** and cited E10. Correct. |
| TalkingDB Text-to-Tree | Returned both AMF definitions in TS 33.501. The model selected **Access and Mobility Management Function** and cited E09. Incorrect for AUTN. |
| Scoped prototype | Ranked E10 first. Selected **Access and Mobility Management Function** and cited E06, which was absent from the supplied rows. Incorrect. |

E09 and E10 are both in [TS 33.501 clause 3.2, printed page 27](https://www.etsi.org/deliver/etsi_ts/133500_133599/133501/18.11.00_60/ts_133501v181100p.pdf#page=28). E06 is in [TS 23.501 clause 3.2, printed page 37](https://www.etsi.org/deliver/etsi_ts/123500_123599/123501/18.07.00_60/ts_123501v180700p.pdf#page=38). For TTT and the prototype, the model had the correct source in view and picked the wrong meaning.

## Scoring and limits

The primary metric is the count of correct expansions with a supporting citation, out of the 40 answerable evaluation questions. The cited row must have been shown to the model. We track correct abstentions and guesses separately. Evidence recall checks whether a correct citation is in the first three rows of the evidence ranking. The analysis compares paired results by acronym family and reports a bootstrap interval over the ten evaluation families. The working margin for a quality advantage is five percentage points with an interval above zero.

We use the pinned [SmolLM2 360M Instruct](https://huggingface.co/HuggingFaceTB/SmolLM2-360M-Instruct/tree/a10cc1512eabd3dde888204e902eca88bddb4951) ONNX Q4 checkpoint on CPU. The same model and option rule apply to every arm. The runner records actual input tokens, local timing and the selected citation. The pilot uses authored questions and selected abbreviation rows. Development and evaluation families are disjoint, and the evaluation labels still need an independent domain review. Free form generation is outside the measured comparisons.

## Connection to the paper

Soman and Roychowdhury used the IEEE wireless LAN and stationary battery standards, MPNet embeddings and Llama 2 7B chat. They report on 42 representative queries. Their separation of terms and definitions helped in 22 of 30 applicable queries (H1). In 15 of 16 examples, they found limitations in generated answers about acronyms (H6). That motivates our scope and citation checks. This 3GPP pilot uses different documents, questions, models and scoring. [ICLR Tiny Paper](https://arxiv.org/html/2404.00657v1#S3.T1)
