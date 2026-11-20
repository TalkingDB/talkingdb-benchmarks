---
pretty_name: "E-commerce RAG: retrieval benchmark on Indian consumer law and store policies"
language:
  - en
size_categories:
  - n<1K
task_categories:
  - question-answering
  - text-retrieval
---

# E-commerce RAG: retrieval benchmark

The data for the TalkingDB e-commerce RAG benchmark: six documents a customer support bot answers from (Indian consumer law, Meesho store policies and a Havells product manual), and the saved outputs of the published run. The questions, evidence, code and results are on GitHub: [talkingdb-benchmarks/ecommerce-rag](https://github.com/TalkingDB/talkingdb-benchmarks/tree/main/ecommerce-rag).

| File | What it is | Source | SHA-256 |
| :--- | :--- | :--- | :--- |
| `documents/CP Act 2019_1732700731.pdf` | Consumer Protection Act, 2019 (India) | [Govt. of India (official text; also on India Code)](https://www.indiacode.nic.in/bitstream/123456789/18964/1/cpa.pdf) | `0ae7f82ab5b77d50087cd4cd2dd2dbc12755c0bdb31371fdefd042b020d50756` |
| `documents/india_consumer_protection_ecommerce_rules_2020.pdf` | Consumer Protection (E-Commerce) Rules, 2020 (India) | [Ministry of Consumer Affairs, Govt. of India - G.S.R. 462(E)](https://taxguru.in/wp-content/uploads/2020/07/Consumer-Protection-E-Commerce-Rules-2020.pdf) | `e3c4bf5cb1a7189563e7aebea9f16e5e83ce14cdf7b2d45eda5d238cc53c0a41` |
| `documents/Learn More About Shipping & Delivery Charges for Meesho Supplier.pdf` | Meesho Shipping, Delivery & Returns Policy (sellers) | [Meesho (supplier website, saved as PDF)](https://supplier.meesho.com/shipping) | `a67801f5e03dda4bfb37396f91ebe0146e191fbe8d484cae5faadbbe8409dd84` |
| `documents/meesho.com_legal_returns, refunds and replacement_embed=true.pdf` | Meesho Returns, Exchange and Refunds Policy | [Meesho (official legal page, saved as PDF)](https://www.meesho.com/legal/returns,%20refunds%20and%20replacement?embed=true) | `3e31040490ade605610b09a47fa06c49e1b690989b51d416f33552fbbc54c2b4` |
| `documents/Penalty Structure and Handling Incorrect Penalties _ Meesho.pdf` | Meesho Supplier Learning Hub: Penalty Structure | [Meesho (supplier learning hub, saved as PDF)](https://supplier.meesho.com/learning-hub/lessons/how-to-handle-incorrect-penalties) | `b0d8be4a98b53d438b747de1c12857acf034c0696e5d52516de4600dcb268d32` |
| `documents/Siphon_WP_Manual_1.pdf` | Havells Siphon Water Purifier User Manual | [Havells India Ltd. (official product manual)](https://havells.com/media/wysiwyg/Siphon_WP_Manual_1.pdf) | `43421721c336b9bfcacb045960599b9e10d74d47213c9acaa626684fd92a2a8d` |
| `results/openai/index.json` | Every chunk in the published index (277), with its document, page and text, so the run can be re-scored without rebuilding the index | Published OpenAI run | `51dbf3518019c592b5dda203f2b9ee5e0879c202c24a9def47c73d625a4c831f` |
| `results/openai/runs.jsonl` | For each question and run: the search query, the top 20 with vector scores, the reranker scores and the final top 4 | Published OpenAI run | `92eba996d5b432bf872ca44bc9162b249372c0cbd13913404c238c8e83ecf0c8` |
| `results/openai/questions-with-chunks.xlsx` | The same run for reading by eye. Tab "with Chunks": each question with its primary and supporting chunks, the top 20 and final top 4 with their text, and both verdicts. Tab "Chunks": all chunks with their text | Published OpenAI run | `bbf368e0f5e1969e2365fa9af366e949bd55e5fa0afffcf5add9b6ad649da1e4` |

The documents are as provided by the client for this support bot; titles and original links are in `documents/sources.json`. Each remains under the terms of its publisher. The run outputs are derived from them.

To get the files with their hashes checked, run `python3 fetch_data.py` from the GitHub folder.
