# E-commerce RAG: what a support bot retrieves

A customer support bot answers questions about returns, refunds, warranties and consumer rights from six documents: Indian consumer law, Meesho store policies and a Havells product manual. This benchmark asks it 70 real support questions and checks, word for word, whether the passages it retrieves contain the evidence each answer needs. It measures the pipeline as it is today; no fix is applied.

## Try it in three steps

Linux or WSL, a few minutes ([what you need](#run-it-yourself)).

```bash
git clone https://github.com/TalkingDB/talkingdb-benchmarks.git && cd talkingdb-benchmarks/ecommerce-rag
bash setup.sh
OPENAI_API_KEY=sk-... bash run.sh
```

No API key? `python3 fetch_data.py && python3 pipeline/score.py` fetches the questions and re-scores the saved run with plain Python, nothing to install. Prefer local models? `bash run.sh --local` ([how](#use-local-models)).

More detail: [how it works](#how-it-works), [the result](#the-result), [the questions](#the-questions), [scoring](#scoring), [the documents](#the-documents), [limits](#limits-plainly).

## How it works

The benchmark runs the support bot's own code ([ecommerce-rag-agent](https://github.com/TalkingDB/ecommerce-rag-agent), pinned in [AGENT_COMMIT.txt](AGENT_COMMIT.txt)), unchanged:

1. **Index.** The six PDFs are read page by page, cut into overlapping passages of about 1,000 characters (277 in all), embedded and stored in a local Qdrant index.
2. **Rewrite follow-ups.** A follow-up such as "Where exactly is this written?" is rewritten into a standalone question using the conversation before it.
3. **Search.** Vector search returns the 20 passages closest to the question (cosine similarity 0.20 or more).
4. **Rerank and cut.** A language model scores how useful each of the 20 is (0, 4, 7 or 10 out of 10); the best 4 scoring at least 4 are kept. These 4 are what the bot answers from.

The benchmark records the top 20 and the final top 4 for every question, three times over, and scores both ([benchmark.py](pipeline/benchmark.py), [score.py](pipeline/score.py)). By default it stops before the answer is written; with `--answers` it also has the bot answer from that same top 4 and checks the answers ([below](#check-the-answers)).

## The result

<!-- result:start -->
Run `openai`, 2026-11-20: `gpt-4o-mini` (openai), `text-embedding-3-small` embeddings, LLM reranker (`gpt-4o-mini`), 20 candidates, top 4, rerank cutoff 0.4, 3 runs ([config](results/openai/config.json)).

| Stage | Questions | Result |
| :--- | :--- | :--- |
| Top 20, after vector search | 64 | 40 (62.5%) have all primary evidence: PASS 40, PARTIAL 13, FAIL 11 |
| Top 4, after the reranker (what the bot answers from) | 64 | 33.3% per run (21 to 22 of 64): PASS 22, FAIL 42 by most runs |
| No answer in the documents | 6 | 3 declined; 3 let passages through to the answer step (RISK) |

In 24 of the 64 questions, search never puts a primary piece of evidence in the top 20, so no reranker could keep it. In 18 more, every primary piece is in the top 20 but the reranker drops at least one. The top 4 changed between runs for 24 of the 70 questions, so a question can pass in one run and fail in the next.


Per question, with each stage's verdict and the passages returned: [per_question.csv](results/openai/per_question.csv). Every metric, mean and range over the runs: [summary.json](results/openai/summary.json).
<!-- result:end -->

Rerunning `bash run.sh` rewrites this section from the new run (`python3 pipeline/report.py`).

To read the published run question by question, with the text of every chunk in its top 20 and top 4, open [questions-with-chunks.xlsx](results/openai/questions-with-chunks.xlsx).

## The questions

70 questions written by Smarter.codes from customer support situations: change of mind, damaged or wrong items, refunds, warranties, cancellations, consumer rights, follow-ups that challenge an earlier answer, and questions the documents cannot answer. Q01 to Q30 are single situations; Q31 to Q71 combine two or three ([questions.json](https://huggingface.co/datasets/TalkingDB/ecommerce-rag/blob/92092b46c725d24d048b9a4ed62861d1c05761f5/questions.json) on Hugging Face, fetched to `cases/questions.json`).

| ID | Area | Question |
| :--- | :--- | :--- |
| Q01 | Change of Mind / No Questions Asked | I bought something yesterday but now I don't need it. Can I get my money back? |
| Q02 | Opened or Used Product | What if I have already opened the box and used it once? Can I still return it? |
| Q03 | Consumer Rights / Return Policy Conflict | But isn't there some law that says we can return anything within 7 days even if the website says no returns? |
| Q04 | Defective Product | My product stopped working after just 10 days and the seller is saying it's not their problem. Now what am I supposed to do? |
| Q05 | Missing Proof of Purchase | I don't have the bill anymore but I have the payment screenshot. Will that work for a refund? |
| Q06 | Missing or Incomplete Order | I ordered two things but received only one. Can I ask for a refund for the whole order? |
| Q07 | Refund Status / Delay | The company said they processed my refund last week. Can you tell me when exactly I'll get my money? |
| Q08 | Consumer Rights / No Refund Policy | If a company says no refunds, does that mean even consumer court can't do anything? |
| Q09 | Consumer Rights / Refund Timeline | I heard that online stores have to return your money within 48 hours. Is that actually true? |
| Q10 | Seller vs Manufacturer Responsibility | Why should I contact the manufacturer when I bought the product from the seller? Isn't it the seller's responsibility? |
| Q11 | Consumer Rights / Policy Conflict | So companies can make whatever return rules they want even if consumer law says something else? |
| Q12 | Sale or Discounted Product | I bought something on sale. Does that mean I can't complain or ask for a refund? |
| Q13 | Consumer Complaint / Compensation | If a company refuses my refund, can I ask consumer court to make them pay me double? |
| Q14 | Return Window | I ordered a phone last Monday. Can you tell me if I can still return it or if it's too late? |
| Q15 | Refund Status / Order Verification | My order number is 987654. Can you check if my refund is approved or still pending? |
| Q16 | Refund Amount / Dispute Resolution | How much money can I actually claim as a refund without going to court? |
| Q17 | Complaint Records / Unavailable Data | How many people have complained against this company this year? Can you check? |
| Q18 | Legal Updates / Dates | When did the government last change the rules for online shopping refunds? What's the exact date? |
| Q19 | Consumer Rights / False Legal Premise | I read that we can cancel any online order whenever we want. Where exactly is this written in consumer law? |
| Q20 | Defective Product / Disputed Misuse | I bought a mixer and used it just twice. Now it's smelling like something is burning. The seller says I damaged it. How can they even prove that? |
| Q21 | Warranty vs Return Window | My phone has a one-year warranty but the shop says returns are only allowed for 7 days. So what's the point of the one-year warranty? |
| Q22 | Wrong Product Delivered | I ordered a red shirt but they sent me a blue one which is actually more expensive. Can I keep it and still ask for my money back? |
| Q23 | Gift Return | I bought something for my friend. Can my friend return it directly or do I have to do it myself? |
| Q24 | Product Misuse / Warranty | My machine's manual says don't use it for more than 30 minutes. I used it for 45 minutes and it stopped working. Does that mean my warranty is gone? |
| Q25 | International Purchase / Jurisdiction | What if I buy something from a company outside India and they don't refund me? Can I still complain in India? |
| Q26 | Answer Challenge / Consistency | How many days do I have to return a product on Meesho? / then: Are you sure about this? Because I read something completely different online. |
| Q27 | Source Citation | Where exactly is this written? Can you tell me which document and page? (follow-up to Q26) |
| Q28 | Exact Source Verification | Can you show me the exact line where it says this? I want to read it myself. (follow-up to Q26) |
| Q29 | Policy Conflict / Source Authority | But the company's website says something completely different. So who am I supposed to believe? (follow-up to Q26) |
| Q30 | Source Grounding / Assumptions | Are you telling me this because it's actually written somewhere in the documents or are you just assuming this is how it works? (not scored) |
| Q31 | No Questions Asked; Opened Product; Non-Returnable | I bought a phone yesterday, opened it and used it for a few hours. Now I don't like it. The company says no questions asked returns but also says opened phones can't be returned. So can I return it or not? |
| Q32 | Sale Item; Defective Product; Refund | I bought a mixer on sale and it stopped working after 3 days. The seller says sale items can't be returned. But what if the product itself is faulty? |
| Q33 | Warranty; Return Window; Defective Product | My phone has a one-year warranty but the return period is only 7 days. It stopped working on day 6. So am I supposed to get a refund or only a repair? |
| Q34 | Wrong Product; Used Product; Exchange | I ordered a red shirt but received a blue one. I wore it once before noticing. Can I still ask them to exchange it? |
| Q35 | Missing Item; Damaged Product; Full Refund | I ordered two products and one was missing. The other one arrived damaged. Can I ask for a refund for the whole order? |
| Q36 | Change of Mind; Return Policy; Price Difference | I bought something yesterday and the price dropped today. Can I return it and buy it again at the lower price? |
| Q37 | Missing Invoice; Warranty; Defective Product | I lost my bill and the product stopped working after a week. I have the payment screenshot. Can the company reject my warranty claim? |
| Q38 | Non-Returnable; Wrong Product; Consumer Rights | I bought a non-returnable product but they delivered the wrong model. Does non-returnable mean I have to keep the wrong product too? |
| Q39 | Cancellation; Delivery; Return Charges | I cancelled my order before it was shipped but the company still delivered it. Now they're saying I have to pay return charges. Why should I? |
| Q40 | Gift Purchase; Opened Product; Warranty | I bought a product for my friend and they opened it. Now it doesn't work. Can my friend claim the warranty or do I have to do it? |
| Q41 | Product Misuse; Defect; Return Window | My machine stopped working after I used it for 45 minutes instead of the recommended 30. But it was only 2 days old. Can I still return it? |
| Q42 | Replacement; Repeated Defects; Refund | The company says no refunds, only replacements. But they've already replaced my product twice and both times it stopped working. Can I ask for my money back now? |
| Q43 | Damaged Product; Late Complaint; Consumer Rights | I bought a phone online and received a damaged one. I complained after 10 days because I was travelling. Can they refuse because I missed the 7-day return window? |
| Q44 | International Purchase; Damaged Product; Consumer Law | I ordered something from another country and it arrived broken. The seller says their country's rules apply. Can I still complain in India? |
| Q45 | Sale Item; Non-Returnable; Policy Conflict | I bought a product during a festival sale. It was marked non-returnable but the website also advertised easy 7-day returns. Which one am I supposed to follow? |
| Q46 | Defective Product; Refund Approval; Store Credit | I returned a defective product and the company approved my refund. Now they're saying they'll give me store credit instead of money. Can they do that? |
| Q47 | Used Product; Defect Dispute; Warranty | I bought a phone, used it for 5 days and noticed the battery drains too quickly. The seller says it's normal. How do I prove it's defective? |
| Q48 | Missing Accessory; Product Description; Refund | I ordered a product and it arrived without the charger. The seller says the charger isn't included, but the product photo clearly shows one. Can I ask for a refund? |
| Q49 | Cancellation; Refund; Unexpected Delivery | I ordered something online, cancelled it, and got a refund. But the product was still delivered. Can I keep it since they already refunded me? |
| Q50 | Warranty; Company Closure; Consumer Rights | I bought a product with a one-year warranty but the company shut down after 6 months. Who is supposed to repair or replace it now? |
| Q51 | Return Window; Conflicting Documents | The website says returns are allowed within 7 days of delivery, but the invoice says 7 days from purchase. My order took 5 days to arrive. Which date should count? |
| Q52 | Refund Promise; Written Policy; Evidence | I bought a product online and the seller promised a refund over WhatsApp, but the website says no refunds. Does their message count? |
| Q53 | Non-Returnable; Damaged Product; Failed Replacement | I bought a non-returnable product and it arrived damaged. The seller agreed to replace it but the replacement is also damaged. Can I ask for a refund instead? |
| Q54 | Return Deadline; Courier Delay; Refund | I returned a product within 7 days but the courier delivered it back to the company after 10 days. Now they're saying my return is late. Is that fair? |
| Q55 | Opened Product; Warranty; Defective Product | I bought a product and the company says the warranty is void because I opened it. But how was I supposed to know it was defective without opening it? |
| Q56 | Jurisdiction; Warranty Terms; Consumer Rights | Havells says any dispute about the purifier goes only to Delhi courts. I live in Chennai. Do I really have to travel to Delhi to file a consumer complaint? |
| Q57 | Warranty Exclusion; Property Damage; Product Liability | The Havells warranty says they aren’t responsible for any property damage from the purifier. My purifier leaked overnight and ruined my wooden cabinet. Can they really refuse to pay? |
| Q58 | Seller Penalty; Cancellation; Conflicting Documents | Meesho’s seller page says there’s no cancellation penalty, but another Meesho page says sellers get a penalty for cancelling. I cancelled an order because I ran out of stock. Will I be charged or not? |
| Q59 | Cancellation; Platform vs Consumer; Consumer Rights | Meesho cancelled my order on their own, but when I cancelled a different order they charged me a fee. Is that even allowed? |
| Q60 | Defective Product; Quality Check; Return Rejection | Meesho rejected my return at pickup because the delivery guy said the tag was torn. The product was defective anyway. Can they refuse a refund for a defective item just because of a tag? |
| Q61 | Instant Refund; Payment Method; False Premise | I heard Meesho gives instant refunds for UPI payments within 4 hours. I paid by UPI and it’s been a day. Why haven’t I got it? |
| Q62 | Grievance Redressal; Timeline; False Legal Premise | The e-commerce rules say every complaint must be fully resolved within 48 hours. Meesho took 10 days. Can I sue them for that? |
| Q63 | Seller Fees; Return Shipping; Unavailable Data | How much does Meesho charge the seller as return shipping fee for a 500g package? |
| Q64 | Spare Parts; Post-Warranty; Unavailable Data | What’s the price of a replacement UF membrane for the Havells Siphon after the warranty ends? |
| Q65 | Consumer Complaint; Legal Fees; Unavailable Data | What’s the court fee for filing a consumer complaint for a ₹2,000 product in Delhi? |
| Q66 | Warranty; Commercial Use; Bulk Purchase | I bought five Havells purifiers for my small café. One broke in four months. Is it still under warranty? |
| Q67 | Consumer Definition; Commercial Purpose; Self-Employment | I run a tailoring shop alone from home and bought a sewing machine online for my work. Does the Consumer Protection Act cover me, or is that “commercial purpose”? |
| Q68 | Instant Refund; Reseller; Eligibility | I bought something from a reseller on Meesho, not directly. Will I still get the instant refund? |
| Q69 | Consumer Complaint; Account Holder; Minor User | My kid ordered something on Meesho using my account. Can I file the consumer complaint myself, or does it have to be in the kid’s name? |
| Q70 | Pre-Ticked Consent; Add-on Charges; Refund | The Meesho checkout had the “all-return option” checkbox already ticked and I paid extra for it without noticing. Can I get that money back? |
| Q71 | Warranty Void; Unauthorised Installation; Service Delay | My Havells purifier was installed by a local plumber because the company technician didn’t turn up for a week. Now they say my warranty is void. Is that fair? |

Q26 is a two-turn conversation, and Q27 to Q29 are asked as follow-ups to it, so their search query is the bot's own rewrite. Q30 asks whether the bot is guessing and has no evidence of its own, so it is not scored.

## Scoring

Each question lists the evidence a complete retrieval must find ([questions.json](https://huggingface.co/datasets/TalkingDB/ecommerce-rag/blob/92092b46c725d24d048b9a4ed62861d1c05761f5/questions.json) on Hugging Face, fetched to `cases/questions.json`):

- **Primary evidence**: what the answer cannot do without, usually one or two passages.
- **Supporting evidence**: what makes the answer better. Reported, not required.

Each piece of evidence is a document, a page and an exact quote. A retrieved passage counts only when it comes from the same document and contains the quote word for word (runs of spaces and line breaks are ignored). When one clause is cut across two passages, either part counts. Matching by quote, not by passage number, means the same evidence holds if you change the chunk size, the chunker or the embedding model.

Two stages are scored for each question:

| Stage | PASS | PARTIAL | FAIL |
| :--- | :--- | :--- | :--- |
| Top 20 (search) | every primary piece found | some found | none found |
| Top 4 (after reranking) | every primary piece kept, in most runs | | otherwise |

Six questions have no answer in the documents (an order number lookup, complaint statistics, a fee amount, a spare part price, a court fee, a refund-then-delivered case). For these, the top 4 passes when nothing gets past the reranker, so the bot declines, and is a RISK when passages still get through and only the answer step can stop a made-up answer.

The bot reads the documents in file name order, which Linux and Windows sort differently, so the same passage can carry a different number on each; the text is the same, and scoring by quote is unaffected. The `chunk_ids` in the case file are labels from the published index.

No language model writes or judges the score. The same saved run always scores the same: `python3 pipeline/score.py` checks it against [summary.json](results/openai/summary.json).

## The documents

The documents the bot answers from, as provided by the client, with titles and original links in [documents/sources.json](documents/sources.json). Each remains under the terms of its publisher.

| Document | What it covers | SHA-256 |
| :--- | :--- | :--- |
| [Consumer Protection Act, 2019 (India)](documents/CP%20Act%202019_1732700731.pdf) ([source](https://www.indiacode.nic.in/bitstream/123456789/18964/1/cpa.pdf)) | Consumer rights, defects and deficiency, unfair contracts and trade practices, where and how to complain, remedies, product liability | `0ae7f82ab5b77d50087cd4cd2dd2dbc12755c0bdb31371fdefd042b020d50756` |
| [Consumer Protection (E-Commerce) Rules, 2020 (India)](documents/india_consumer_protection_ecommerce_rules_2020.pdf) ([source](https://taxguru.in/wp-content/uploads/2020/07/Consumer-Protection-E-Commerce-Rules-2020.pdf)) | Duties of online platforms and sellers: grievance officers, cancellation charges, refunds, taking back defective goods, foreign sellers | `e3c4bf5cb1a7189563e7aebea9f16e5e83ce14cdf7b2d45eda5d238cc53c0a41` |
| [Meesho Shipping, Delivery & Returns Policy (sellers)](documents/Learn%20More%20About%20Shipping%20&%20Delivery%20Charges%20for%20Meesho%20Supplier.pdf) ([source](https://supplier.meesho.com/shipping)) | For sellers: shipping timeline, the 7-day return window, return shipping fee, no cancellation penalty | `a67801f5e03dda4bfb37396f91ebe0146e191fbe8d484cae5faadbbe8409dd84` |
| [Meesho Returns, Exchange and Refunds Policy](documents/meesho.com_legal_returns,%20refunds%20and%20replacement_embed=true.pdf) ([source](https://www.meesho.com/legal/returns,%20refunds%20and%20replacement?embed=true)) | Return, exchange and refund policy: return options, quality checks, smartphone replacement rules, refund timelines, instant refunds | `3e31040490ade605610b09a47fa06c49e1b690989b51d416f33552fbbc54c2b4` |
| [Meesho Supplier Learning Hub: Penalty Structure](documents/Penalty%20Structure%20and%20Handling%20Incorrect%20Penalties%20_%20Meesho.pdf) ([source](https://supplier.meesho.com/learning-hub/lessons/how-to-handle-incorrect-penalties)) | For sellers: penalties for cancellations, direct shipping and wrong items, and how to dispute one | `b0d8be4a98b53d438b747de1c12857acf034c0696e5d52516de4600dcb268d32` |
| [Havells Siphon Water Purifier User Manual](documents/Siphon_WP_Manual_1.pdf) ([source](https://havells.com/media/wysiwyg/Siphon_WP_Manual_1.pdf)) | Havells Siphon water purifier manual: use, maintenance, service plans, warranty terms and exclusions | `43421721c336b9bfcacb045960599b9e10d74d47213c9acaa626684fd92a2a8d` |

The E-Commerce Rules PDF opens with the end of a Hindi notification, and the Havells manual has a diagram whose text extracts as unreadable characters; both are indexed as they come.

## Run it yourself

Linux or WSL, with `git`, `python3` and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/TalkingDB/talkingdb-benchmarks.git
cd talkingdb-benchmarks/ecommerce-rag
bash setup.sh
export OPENAI_API_KEY=sk-...
bash run.sh
```

`setup.sh` fetches the documents and the questions from Hugging Face at pinned commits and checks them by SHA-256 ([fetch_data.py](fetch_data.py)), checks out the bot's code at the pinned commit and installs its dependencies at the versions that built the published index ([requirements.txt](requirements.txt)). `run.sh` checks the scoring rules, indexes the documents (277 passages, a fraction of a cent of embeddings), asks the 70 questions three times and rewrites `results/openai/`. It takes about 20 minutes with `gpt-4o-mini` and `text-embedding-3-small`.

Options: `--runs 1` for a single run, `--only Q01,Q68` for a few questions (written to `results/openai-partial/`), `--reingest` to rebuild the index. A key can also go in an `.env` file in this folder.

OpenAI models do not give exactly the same output every time, even at temperature 0, so a rerun lands near the published numbers rather than on them; the reranker's top 4 changes between runs for some questions.

## Check the answers

```bash
bash run.sh --answers
```

`--answers` adds one step per question: the bot writes its answer from exactly the top 4 it just retrieved, with the conversation so far for follow-ups, as it does for a user. Each answer is then checked against the passages its `[n]` citations name, with no language model judging:

| Check | Questions |
| :--- | :--- |
| Answered (did not refuse) | with evidence |
| Cites a passage holding primary evidence, or all of it | with evidence |
| Has no citation, or cites a passage number that does not exist | with evidence |
| Declined | with no answer in the documents |

Each question gets a verdict: GROUNDED, UNGROUNDED, REFUSED (although the documents hold the answer), DECLINED or ANSWERED (although they do not). This measures grounding, not correctness: an answer can cite the right passage and still misread it, and the expected answers themselves are not published. It costs one more model call per question and run, and like any full run it rewrites `results/openai/` and the result section above.

## Use local models

```bash
ollama pull bge-m3 && ollama pull qwen3.5:9b
bash run.sh --local
```

`--local` switches the bot to [Ollama](https://ollama.com/) on `localhost:11434`: `bge-m3` embeddings and `qwen3.5:9b` for rewriting and reranking, the bot's own local defaults. The passages are cut the same way, so the same evidence is scored; the numbers are your own and go to `results/local/`. A GPU helps: every question sends 20 passages through the chat model for reranking. On a laptop CPU with the smaller `qwen3.5:4b`, indexing and three questions took about 22 minutes, so try `--runs 1 --only Q01,Q68` first. Other models: set `OLLAMA_EMBEDDING_MODEL` and `OLLAMA_CHAT_MODEL`.

## Limits, plainly

1. 70 questions, 64 with evidence. One question is 1.6 points: treat differences under about 5 points as noise.
2. The evidence was chosen by one team and reviewed once. Some choices are judgement calls, such as which manual a question about "my machine" refers to.
3. Strict scoring: when the top 4 holds a passage that says nearly the same as the primary one (two pages both stating the 7-day window), the question still fails. Real retrieval quality is somewhat better than the headline.
4. The published result is retrieval only. A question that passes can still get a wrong answer, and one that fails can still get a reasonable one. `--answers` checks whether answers cite their evidence, not whether they are right.
5. The published run uses OpenAI models, which change over time and are not fully repeatable.
6. The questions were written for these documents, and the result reflects this mix: many consumer-rights questions against mostly store-policy text.

## Files

| Path | What it is |
| :--- | :--- |
| `documents/` | `sources.json` (titles and links); the six PDFs are fetched from Hugging Face |
| `cases/questions.json` | The 70 questions with their primary and supporting evidence, fetched from Hugging Face |
| `pipeline/benchmark.py` | Indexes the documents and runs the questions through the bot's retrieval |
| `pipeline/score.py` | Exact scoring, with a self check; plain Python |
| `pipeline/report.py` | Writes the result section: the README for the OpenAI run, `report.md` for a local run |
| `results/openai/` | The published run: `index.json`, `runs.jsonl`, `config.json`, `summary.json`, `per_question.csv`, and `questions-with-chunks.xlsx` to read it question by question |
| `setup.sh`, `run.sh`, `AGENT_COMMIT.txt`, `requirements.txt` | Setup and run; the bot's code is pinned to the listed commit |
| `fetch_data.py`, `DATA.txt`, `DATASET_CARD.md` | The data files on [Hugging Face](https://huggingface.co/datasets/TalkingDB/ecommerce-rag), each with its SHA-256 and the dataset commit it comes from, and the dataset card |

Built by [TalkingDB](https://talkingdb.io/). Code under [AGPL-3.0](../LICENSE).
