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

The data for the TalkingDB e-commerce RAG benchmark: six documents a customer support bot answers from (Indian consumer law, Meesho store policies and a Havells product manual), and the support questions with the evidence each answer needs. The code and results are on GitHub: [talkingdb-benchmarks/ecommerce-rag](https://github.com/TalkingDB/talkingdb-benchmarks/tree/main/ecommerce-rag).

| File | What it is | Source | SHA-256 |
| :--- | :--- | :--- | :--- |
| `CP Act 2019_1732700731.pdf` | Consumer Protection Act, 2019 (India) | [Govt. of India (official text; also on India Code)](https://www.indiacode.nic.in/bitstream/123456789/18964/1/cpa.pdf) | `0ae7f82ab5b77d50087cd4cd2dd2dbc12755c0bdb31371fdefd042b020d50756` |
| `india_consumer_protection_ecommerce_rules_2020.pdf` | Consumer Protection (E-Commerce) Rules, 2020 (India) | [Ministry of Consumer Affairs, Govt. of India - G.S.R. 462(E)](https://taxguru.in/wp-content/uploads/2020/07/Consumer-Protection-E-Commerce-Rules-2020.pdf) | `e3c4bf5cb1a7189563e7aebea9f16e5e83ce14cdf7b2d45eda5d238cc53c0a41` |
| `Learn More About Shipping & Delivery Charges for Meesho Supplier.pdf` | Meesho Shipping, Delivery & Returns Policy (sellers) | [Meesho (supplier website, saved as PDF)](https://supplier.meesho.com/shipping) | `a67801f5e03dda4bfb37396f91ebe0146e191fbe8d484cae5faadbbe8409dd84` |
| `meesho.com_legal_returns, refunds and replacement_embed=true.pdf` | Meesho Returns, Exchange and Refunds Policy | [Meesho (official legal page, saved as PDF)](https://www.meesho.com/legal/returns,%20refunds%20and%20replacement?embed=true) | `3e31040490ade605610b09a47fa06c49e1b690989b51d416f33552fbbc54c2b4` |
| `Penalty Structure and Handling Incorrect Penalties _ Meesho.pdf` | Meesho Supplier Learning Hub: Penalty Structure | [Meesho (supplier learning hub, saved as PDF)](https://supplier.meesho.com/learning-hub/lessons/how-to-handle-incorrect-penalties) | `b0d8be4a98b53d438b747de1c12857acf034c0696e5d52516de4600dcb268d32` |
| `Siphon_WP_Manual_1.pdf` | Havells Siphon Water Purifier User Manual | [Havells India Ltd. (official product manual)](https://havells.com/media/wysiwyg/Siphon_WP_Manual_1.pdf) | `43421721c336b9bfcacb045960599b9e10d74d47213c9acaa626684fd92a2a8d` |
| `questions.json` | The support questions, each with its primary and supporting evidence as document, page and exact quote | Written by Smarter.codes | `0660eb4db1fefb24d26ba674992758fae34fd98f32f311b885601736392b9e05` |

The documents are as provided by the client for this support bot; titles and original links are in `documents/sources.json` on GitHub. Each remains under the terms of its publisher.

The benchmark fetches the documents from commit `322248c5359b26d99d185e91f34304ca4e347734` and the questions from commit `92092b46c725d24d048b9a4ed62861d1c05761f5`, so later uploads here never change it. To get the files with their hashes checked, run `python3 fetch_data.py` from the GitHub folder.

This dataset is private: the store policies and the manual belong to their publishers and are not redistributed. Access is for TalkingDB members; `fetch_data.py` uses your Hugging Face token (`hf auth login`, or `HF_TOKEN`).
