"""Run every question in cases/questions.json through the e-commerce RAG pipeline and record what it retrieves.

Uses the pipeline's own code (ecommerce-rag-agent, pinned in AGENT_COMMIT.txt): the same
document loader, chunker, vector store, reranker and question rewriting as the app. Only
retrieval is measured; the answer step runs only to build the conversation for the
follow-up questions (Q26 to Q29).

  python pipeline/benchmark.py                   OpenAI models, 3 runs (needs OPENAI_API_KEY)
  python pipeline/benchmark.py --local           local models through Ollama
  python pipeline/benchmark.py --runs 1 --only Q01,Q68

Writes index.json (every chunk in the index), runs.jsonl (top 20, reranker scores and top 4
for every question and run) and config.json, then scores them with score.py into
summary.json and per_question.csv. A full run with the default settings writes
results/<openai|local>/; --answers adds "-answers" to the folder, and --only, a different
--runs or settings changed through the environment add "-partial", so they never replace it.
The files are written to a staging folder and moved into place only when the run finishes.
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
RUNS = 3
# Settings fields that say where the run reads and writes, not how the pipeline behaves. Every
# other field of the pipeline's Settings is recorded in config.json and checked for changes.
NOT_SETTING_FIELDS = {"docs_dir", "sources_file", "feedback_file", "interactions_file", "qdrant_url",
                      "qdrant_api_key", "qdrant_path", "ollama_base_url"}
# Environment variables that pick where the run reads and writes, the provider or the key,
# not how the pipeline behaves; setting them is not a custom setting.
NOT_SETTINGS = {"DOCS_DIR", "SOURCES_FILE", "QDRANT_PATH", "QDRANT_URL", "QDRANT_API_KEY", "INTERACTIONS_FILE",
                "FEEDBACK_FILE", "LLM_PROVIDER", "EMBEDDING_PROVIDER", "OPENAI_API_KEY", "OLLAMA_BASE_URL"}

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
    check_agent()
    sys.path.insert(0, str(AGENT))


def check_agent() -> str:
    """Stop unless the pipeline code is at the commit in AGENT_COMMIT.txt with no local edits,
    so a run never claims a commit whose code it did not run. Returns the commit."""
    import subprocess

    pinned = (HERE / "AGENT_COMMIT.txt").read_text().split()[1]
    git = lambda *a: subprocess.run(["git", "-C", str(AGENT), *a], capture_output=True, text=True)  # noqa: E731
    head = git("rev-parse", "HEAD")
    if head.returncode:
        sys.exit(f"{AGENT} is not a git checkout. Run: bash setup.sh")
    if head.stdout.strip() != pinned:
        sys.exit(f"The pipeline code is at {head.stdout.strip()[:12]}, but AGENT_COMMIT.txt pins {pinned[:12]}. "
                 "Run: bash setup.sh")
    # Untracked files count too (an added module could change what runs), apart from the
    # bytecode Python writes itself: the pipeline repo does not ignore __pycache__.
    status = git("status", "--porcelain", "--untracked-files=all").stdout.splitlines()
    edited = "\n".join(line for line in status
                       if not (line.startswith("?? ") and (line.endswith(".pyc") or "__pycache__/" in line)))
    if edited:
        rel = AGENT.relative_to(HERE).as_posix()
        sys.exit(f"The pipeline code at {pinned[:12]} has local edits or added files, so a run would not measure "
                 f"that commit:\n{edited}\nUndo edits with: git -C {rel} checkout -- .\n"
                 f"Remove added files (lines starting ??) with: git -C {rel} clean -f <file>")
    return pinned


def setting_names(settings) -> list:
    """Every field of the pipeline's Settings that changes how it behaves, in its own order, so a
    setting added to the pipeline later is recorded and checked without a change here."""
    import dataclasses

    return [f.name for f in dataclasses.fields(settings) if f.name not in NOT_SETTING_FIELDS]


def custom_settings(settings) -> dict:
    """The recorded settings that differ from the pipeline's defaults, because an environment
    variable or a .env file changed them. Defaults come from the pipeline's own code: its
    settings are rebuilt with every variable it reads (apart from NOT_SETTINGS) removed."""
    import re

    from app.config import Settings

    names = set(re.findall(r'"([A-Z][A-Z0-9_]+)"', (AGENT / "app" / "config.py").read_text(encoding="utf-8")))
    saved = {n: os.environ.pop(n) for n in names - NOT_SETTINGS if n in os.environ}
    try:
        defaults = Settings()
    finally:
        os.environ.update(saved)
    return {k: str(getattr(settings, k)) for k in setting_names(settings)
            if str(getattr(settings, k)) != str(getattr(defaults, k))}


def output_folder(args, custom: dict):
    """results/openai (or results/local) for a full run with the default settings; any other run
    gets its own folder, so it never replaces the full run. Returns the folder and the reasons."""
    name = "local" if args.local else "openai"
    reasons = []
    if args.answers:
        name += "-answers"
        reasons.append("--answers")
    partial = []
    if args.only:
        partial.append("--only")
    if args.runs != RUNS:
        partial.append(f"--runs {args.runs}")
    if custom:
        partial.append("custom settings: " + ", ".join(f"{k}={v}" for k, v in custom.items()))
    if partial:
        name += "-partial"
        reasons += partial
    return HERE / "results" / name, reasons


def ensure_index(settings, reingest: bool) -> None:
    """Build the index if it is empty, asked for, or built from other inputs or chunk settings."""
    import hashlib

    from app.loaders import SUPPORTED_EXTENSIONS
    from app.vectorstore import count_points

    # Fingerprint exactly what the loader reads: every file it ingests (same extension rule),
    # and sources.json, whose titles and links are stored in every chunk.
    docs = Path(settings.docs_dir)
    inputs = [p for p in sorted(docs.iterdir()) if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS]
    inputs.append(Path(settings.sources_file))
    stamp = json.dumps({
        "inputs": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None for p in inputs},
        **{k: str(getattr(settings, k)) for k in ("embedding_id", "chunking_strategy", "chunk_size", "chunk_overlap")},
    }, sort_keys=True)
    stamp_file = INDEX_DIR / f"{settings.collection}.json"
    folder = INDEX_DIR / "collection" / settings.collection
    # Decide from the files alone: opening the index here (count_points) would keep its SQLite
    # file open, and on Windows the folder could then not be deleted.
    if not reingest and folder.exists() and (not stamp_file.exists() or stamp_file.read_text(encoding="utf-8") != stamp):
        print("Documents or chunk settings changed since the index was built; rebuilding it.")
        reingest = True
    if reingest and folder.exists():
        # Delete the collection's files before any Qdrant client opens them. Qdrant's local
        # delete leaves its SQLite file open and ignores the error, so on Windows the old
        # points survive and a rebuild adds every chunk a second time.
        import shutil

        shutil.rmtree(folder)
    if reingest or count_points(settings) == 0:
        import ingest

        # Written back only after a complete build, so a build that stops halfway is never
        # taken for a finished index on the next run.
        stamp_file.unlink(missing_ok=True)
        print(f"Indexing the documents with {settings.embedding_id} ...")
        ingest.run(None)
    INDEX_DIR.mkdir(exist_ok=True)
    stamp_file.write_text(stamp, encoding="utf-8")


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
    ids = [c["chunk_id"] for c in chunks]
    if len(ids) != len(set(ids)):
        sys.exit(f"The index holds {len(ids)} points for {len(set(ids))} chunks: some chunks are indexed twice, "
                 "which would skew every result. Rebuild it: bash run.sh --reingest")
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


RERANK_ATTEMPTS = 3


class RerankFailed(Exception):
    """The LLM reranker fell back to vector order on every attempt."""


def is_fallback(reranker_name, ranked) -> bool:
    """True when the LLM reranker returned vector order: every rerank score equals the vector score."""
    return reranker_name == "llm" and bool(ranked) and all(
        abs(c.rerank_score - c.vector_score) < 1e-9 for c in ranked)


def positive_int(text):
    n = int(text)
    if n < 1:
        raise argparse.ArgumentTypeError(f"must be 1 or more, not {n}")
    return n


def select_cases(only, cases_all):
    """The scored questions, or the ones --only names. Stops on an id that does not exist or
    is not scored, rather than silently running fewer questions."""
    cases = [c for c in cases_all if not c.get("not_scored")]
    if not only:
        return cases
    wanted = list(dict.fromkeys(x.strip().upper() for x in only.split(",") if x.strip()))
    if not wanted:
        sys.exit("--only names no question ids, e.g. --only Q01,Q68")
    known = {c["id"]: c for c in cases_all}
    unknown = [w for w in wanted if w not in known]
    if unknown:
        sys.exit(f"Unknown question id(s) in --only: {', '.join(unknown)}. "
                 f"The ids are {cases_all[0]['id']} to {cases_all[-1]['id']}, as in cases/questions.json.")
    skipped = [w for w in wanted if known[w].get("not_scored")]
    if skipped:
        sys.exit("Not scored, so not run: " + "; ".join(f"{w} ({known[w]['not_scored']})" for w in skipped))
    return [c for c in cases if c["id"] in wanted]


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
        for _ in range(RERANK_ATTEMPTS):
            ranked = a.reranker.rerank(query, candidates) if candidates else []
            if not is_fallback(a.reranker.name, ranked):
                break
        else:
            raise RerankFailed(query)
        kept = [c for c in ranked if c.rerank_score >= s.min_rerank_score][: s.top_k]
        cid = lambda d: int(d.metadata["chunk_id"])  # noqa: E731
        return {
            "top_vector": [[cid(d), round(float(sc), 4)] for d, sc in hits],
            "candidates": [cid(d) for d, _ in candidates],
            "reranked": [[cid(c.document), round(c.rerank_score, 3)] for c in ranked],
            "kept": [cid(c.document) for c in kept],
            "rerank_fallback": False,
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
    p.add_argument("--runs", type=positive_int, default=RUNS, help=f"times each question is asked (default {RUNS})")
    p.add_argument("--only", default="", help="comma-separated question ids, for a quick check")
    p.add_argument("--reingest", action="store_true", help="rebuild the index even if it exists")
    p.add_argument("--answers", action="store_true",
                   help="also write the bot's answer from the same top 4 and score it (one more model call per question)")
    args = p.parse_args()
    # Check the questions before any setup, so a typo in --only costs nothing.
    if not score.CASES.exists():
        sys.exit(f"{score.CASES.relative_to(HERE).as_posix()} not found. Run: bash setup.sh")
    cases_all = json.loads(score.CASES.read_text(encoding="utf-8"))["questions"]
    cases = select_cases(args.only, cases_all)

    configure(args.local)
    import logging

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("pypdf").setLevel(logging.ERROR)  # font warnings while reading the PDFs; the text is unaffected
    from app.config import get_settings

    settings = get_settings()
    out, reasons = output_folder(args, custom_settings(settings))
    if reasons:
        print(f"Writing to results/{out.name}/ ({'; '.join(reasons)}), not over the full run.")
    # Everything is written to a staging folder and moved into place only when the run has
    # finished and been scored, so a run that stops (a failed check, an API error, Ctrl+C)
    # leaves the results already in the folder untouched.
    stage = out.with_name(out.name + ".tmp")
    if stage.exists():
        import shutil

        shutil.rmtree(stage)
    stage.mkdir(parents=True)

    ensure_index(settings, args.reingest)
    runner = Runner(settings)
    # Close the local index on any exit, including a stop below; left to interpreter shutdown,
    # Qdrant's own cleanup prints an ImportError traceback after the real message.
    import atexit

    atexit.register(runner.assistant.vectorstore.client.close)
    by_id = {c["id"]: c for c in cases_all}

    index = snapshot(runner.assistant.vectorstore, stage)
    check_evidence(cases, index)

    config = {k: str(getattr(settings, k)) for k in setting_names(settings)}
    config["agent_commit"] = check_agent()
    config["runs"] = args.runs
    config["answers"] = args.answers
    config["run_date"] = date.today().isoformat()
    (stage / "config.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    print("Config:", config)

    total = args.runs * len(cases)
    with open(stage / "runs.jsonl", "w", encoding="utf-8") as log:
        n = 0
        for run in range(1, args.runs + 1):
            for case in cases:
                n += 1
                query, asked, prior, history = runner.query_for(case, by_id)
                try:
                    found, kept = runner.retrieve(query)
                except RerankFailed:
                    sys.exit(f"The LLM reranker ({settings.rerank_model or settings.chat_model}) failed {RERANK_ATTEMPTS} "
                             f"times on {case['id']} (see the warning above) and fell back to vector order, so this run "
                             f"would not measure the reranker. Nothing was written to results/{out.name}/. "
                             "Check the model name, API key or Ollama, then run again.")
                rec = {"run": run, "id": case["id"], "query": query, "prior_turns": prior, **found}
                if args.answers:
                    rec.update(runner.answer(asked, kept, history))
                log.write(json.dumps(rec, ensure_ascii=False) + "\n")
                log.flush()
                print(f"run {run}/{args.runs}  {n:>3}/{total}  {case['id']}  top 4: {rec['kept']}", flush=True)

    runner.assistant.vectorstore.client.close()  # close the local index now, not during interpreter shutdown
    summary, rows = score.score_folder(stage)
    score.write(stage, summary, rows)

    # The run is complete: replace the files it produced, file by file, so anything else kept
    # in the folder (such as the spreadsheet in results/openai) stays.
    out.mkdir(parents=True, exist_ok=True)
    for f in stage.iterdir():
        os.replace(f, out / f.name)
    stage.rmdir()
    import report

    print("\n" + report.write_report(out))
    print(f"Report: {out / 'report.md'}\nResults: {out}")


if __name__ == "__main__":
    main()
