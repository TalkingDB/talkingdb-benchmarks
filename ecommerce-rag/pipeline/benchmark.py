"""Run the 70 questions through the e-commerce RAG pipeline and record what it retrieves.

Uses the pipeline's own code (ecommerce-rag-agent, pinned in AGENT_COMMIT.txt): the same
document loader, chunker, vector store, reranker and question rewriting as the app. Only
retrieval is measured; the answer step runs only to build the conversation for the
follow-up questions (Q26 to Q29).

  python pipeline/benchmark.py                   OpenAI models, 3 runs (needs OPENAI_API_KEY)
  python pipeline/benchmark.py --local           local models through Ollama
  python pipeline/benchmark.py --runs 1 --only Q01,Q68

Writes results/<openai|local>/: index.json (every chunk in the index), runs.jsonl (top 20,
reranker scores and top 4 for every question and run), config.json, then scores them with
score.py into summary.json and per_question.csv.
"""

import argparse
import json
import os
import sys
import uuid
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
AGENT = HERE / "agent-src" / "ecommerce-rag-agent"
INDEX_DIR = HERE / ".index"

sys.path.insert(0, str(HERE / "pipeline"))
import score  # noqa: E402


def configure(local: bool) -> None:
    """Point the pipeline at this folder's documents and index, before it reads settings."""
    os.environ.update({
        "DOCS_DIR": str(HERE / "documents"),
        "SOURCES_FILE": str(HERE / "documents" / "sources.json"),
        "QDRANT_PATH": str(INDEX_DIR),
        "INTERACTIONS_FILE": str(INDEX_DIR / "interactions.jsonl"),
        "FEEDBACK_FILE": str(INDEX_DIR / "feedback.jsonl"),
        "QDRANT_URL": "",  # empty, not unset, so a .env file cannot point the run at a server
    })
    provider = "ollama" if local else "openai"
    os.environ["LLM_PROVIDER"] = provider
    os.environ["EMBEDDING_PROVIDER"] = provider
    if not AGENT.exists():
        sys.exit(f"Pipeline code not found at {AGENT}. Run: bash setup.sh")
    sys.path.insert(0, str(AGENT))


def ensure_index(settings, reingest: bool) -> None:
    from app.vectorstore import count_points

    if reingest or count_points(settings) == 0:
        import ingest

        print(f"Indexing the documents with {settings.embedding_id} ...")
        ingest.run(None)


def snapshot(store, out: Path) -> dict:
    """Save every chunk in the index, so the run can be re-scored without the index."""
    points, offset = [], None
    while True:
        batch, offset = store.client.scroll(store.collection_name, limit=256, offset=offset, with_payload=True)
        points.extend(batch)
        if offset is None:
            break
    chunks = sorted(
        (
            {
                "chunk_id": p.payload["metadata"]["chunk_id"],
                "document": p.payload["metadata"]["source"],
                "page": p.payload["metadata"].get("page"),
                "text": p.payload["page_content"],
            }
            for p in points
        ),
        key=lambda c: c["chunk_id"],
    )
    (out / "index.json").write_text(json.dumps(chunks, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return {c["chunk_id"]: {"document": c["document"], "text": score.norm(c["text"])} for c in chunks}


def check_evidence(cases, index) -> None:
    """Every quote must exist somewhere in the index, or the run cannot be scored fairly."""
    missing = [
        (c["id"], ev["quote"])
        for c in cases for u in c["primary"] + c["supporting"] for ev in u["evidence"]
        if not any(ch["document"] == ev["document"] and score.norm(ev["quote"]) in ch["text"] for ch in index.values())
    ]
    if missing:
        for qid, quote in missing[:10]:
            print(f"  {qid}: not in index: {quote!r}")
        sys.exit(f"{len(missing)} evidence quotes are missing from the index; check the documents and chunker.")
    print(f"Index: {len(index)} chunks; all evidence quotes found.")


class Runner:
    def __init__(self, settings):
        from app.rag import build_assistant

        self.settings = settings
        self.assistant = build_assistant(settings)

    def query_for(self, case, by_id):
        """The search query for a question, the question as asked, and its conversation so far.
        Follow-ups are rewritten against their conversation, as the bot does."""
        turns = [t.strip() for t in case["question"].split(">>") if t.strip()]
        prior = []
        if case.get("after"):
            prior = [t.strip() for t in by_id[case["after"]]["question"].split(">>") if t.strip()]
        prior += turns[:-1]
        if not prior:
            return turns[-1], turns[-1], [], []
        session = f"bench-{uuid.uuid4()}"
        for turn in prior:
            self.assistant.ask(turn, session_id=session)
        history = self.assistant.memory.get(session)
        return self.assistant.condense(turns[-1], history), turns[-1], prior, history

    def retrieve(self, query):
        """The pipeline's retrieve(), keeping every stage instead of only the final passages.
        Returns the record and the final passages, for the answer step."""
        s, a = self.settings, self.assistant
        hits = a.vectorstore.similarity_search_with_score(query, k=max(s.fetch_k, s.top_k))
        candidates = [(d, sc) for d, sc in hits if sc >= s.min_relevance]
        ranked = a.reranker.rerank(query, candidates) if candidates else []
        kept = [c for c in ranked if c.rerank_score >= s.min_rerank_score][: s.top_k]
        cid = lambda d: int(d.metadata["chunk_id"])  # noqa: E731
        return {
            "top_vector": [[cid(d), round(float(sc), 4)] for d, sc in hits],
            "candidates": [cid(d) for d, _ in candidates],
            "reranked": [[cid(c.document), round(c.rerank_score, 3)] for c in ranked],
            "kept": [cid(c.document) for c in kept],
            "rerank_fallback": bool(ranked) and a.reranker.name == "llm"
            and all(abs(c.rerank_score - c.vector_score) < 1e-9 for c in ranked),
        }, kept

    def answer(self, question, kept, history):
        """The pipeline's answer step on exactly these passages, as ask() runs it.
        Returns the answer, whether it is the refusal, and the passages its [n] citations name."""
        import re

        from app.config import REFUSAL_MESSAGE
        from app.rag import _format_context, _is_refusal

        if not kept:
            return {"answer": REFUSAL_MESSAGE, "refused": True, "cited": [], "invalid_citations": []}
        text = self.assistant._answer_chain.invoke(
            {"context": _format_context(kept), "history": history, "question": question}
        ).strip()
        refused = _is_refusal(text)
        numbers = sorted({int(n) for n in re.findall(r"\[(\d+)\]", text)})
        return {
            "answer": REFUSAL_MESSAGE if refused else text,
            "refused": refused,
            "cited": [] if refused else [int(kept[n - 1].document.metadata["chunk_id"]) for n in numbers if 1 <= n <= len(kept)],
            "invalid_citations": [] if refused else [n for n in numbers if not 1 <= n <= len(kept)],
        }


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--local", action="store_true", help="use local models through Ollama instead of OpenAI")
    p.add_argument("--runs", type=int, default=3)
    p.add_argument("--only", default="", help="comma-separated question ids, for a quick check")
    p.add_argument("--reingest", action="store_true", help="rebuild the index even if it exists")
    p.add_argument("--answers", action="store_true",
                   help="also write the bot's answer from the same top 4 and score it (one more model call per question)")
    args = p.parse_args()

    configure(args.local)
    import logging

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("pypdf").setLevel(logging.ERROR)  # font warnings while reading the PDFs; the text is unaffected
    from app.config import get_settings

    settings = get_settings()
    out = HERE / "results" / ("local" if args.local else "openai")
    if args.only:
        out = out.with_name(out.name + "-partial")
    out.mkdir(parents=True, exist_ok=True)

    ensure_index(settings, args.reingest)
    runner = Runner(settings)
    cases_all = json.loads(score.CASES.read_text(encoding="utf-8"))["questions"]
    by_id = {c["id"]: c for c in cases_all}
    cases = [c for c in cases_all if not c.get("not_scored")]
    if args.only:
        wanted = {x.strip() for x in args.only.split(",")}
        cases = [c for c in cases if c["id"] in wanted]

    index = snapshot(runner.assistant.vectorstore, out)
    check_evidence(cases, index)

    config = {k: str(getattr(settings, k)) for k in (
        "llm_provider", "chat_model", "embedding_provider", "embedding_model", "reranker", "rerank_model",
        "fetch_k", "min_relevance", "top_k", "min_rerank_score", "temperature",
        "chunking_strategy", "chunk_size", "chunk_overlap")}
    config["agent_commit"] = (HERE / "AGENT_COMMIT.txt").read_text().split()[1]
    config["runs"] = args.runs
    config["answers"] = args.answers
    config["run_date"] = date.today().isoformat()
    (out / "config.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    print("Config:", config)

    total = args.runs * len(cases)
    with open(out / "runs.jsonl", "w", encoding="utf-8") as log:
        n = 0
        for run in range(1, args.runs + 1):
            for case in cases:
                n += 1
                query, asked, prior, history = runner.query_for(case, by_id)
                found, kept = runner.retrieve(query)
                rec = {"run": run, "id": case["id"], "query": query, "prior_turns": prior, **found}
                if args.answers:
                    rec.update(runner.answer(asked, kept, history))
                log.write(json.dumps(rec, ensure_ascii=False) + "\n")
                log.flush()
                print(f"run {run}/{args.runs}  {n:>3}/{total}  {case['id']}  top 4: {rec['kept']}", flush=True)

    runner.assistant.vectorstore.client.close()  # close the local index now, not during interpreter shutdown
    summary, rows = score.score_folder(out)
    score.write(out, summary, rows)
    print()
    score.show(summary)
    if not args.only:
        import report

        report.write_report(out)
    print(f"\nResults: {out}")


if __name__ == "__main__":
    main()
