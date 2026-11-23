"""Regression tests for what keeps a run from replacing the published results.

Run from ecommerce-rag/ after setup: .venv-rag/bin/python -m unittest discover -s pipeline -v
(on Windows: .venv-rag/Scripts/python.exe). No API key or network needed.
"""

import os
import subprocess
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import benchmark  # noqa: E402

FULL_RUN = Namespace(local=False, answers=False, only=None, runs=benchmark.RUNS)


class OutputFolder(unittest.TestCase):
    """A changed pipeline setting sends the run to a -partial folder, never results/openai/."""

    @classmethod
    def setUpClass(cls):
        cls.env = dict(os.environ)
        benchmark.configure(local=False)
        from app.config import Settings
        cls.Settings = Settings

    @classmethod
    def tearDownClass(cls):
        os.environ.clear()
        os.environ.update(cls.env)

    def folder(self, **env):
        with mock.patch.dict(os.environ, env):
            settings = self.Settings()
            return benchmark.output_folder(FULL_RUN, benchmark.custom_settings(settings))[0].name

    def test_default_settings_publish(self):
        self.assertEqual(self.folder(), "openai")

    def test_history_turns_is_partial(self):
        self.assertEqual(self.folder(HISTORY_TURNS="8"), "openai-partial")

    def test_every_behaviour_setting_is_partial(self):
        for name, value in {"TOP_K": "6", "CHUNK_SIZE": "800", "QDRANT_COLLECTION": "other",
                            "CROSS_ENCODER_MODEL": "other", "OLLAMA_NUM_CTX": "4096",
                            "OLLAMA_REASONING": "true"}.items():
            with self.subTest(name):
                self.assertEqual(self.folder(**{name: value}), "openai-partial")

    def test_config_records_every_behaviour_setting(self):
        names = benchmark.setting_names(self.Settings())
        for name in ("history_turns", "cross_encoder_model", "ollama_num_ctx", "ollama_reasoning",
                     "collection_name", "top_k", "chunk_size"):
            self.assertIn(name, names)
        for name in benchmark.NOT_SETTING_FIELDS:
            self.assertNotIn(name, names)


class PinnedAgent(unittest.TestCase):
    """The run stops when the pipeline code has edits or added files, not for bytecode."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        here = Path(self.tmp.name)
        agent = here / "agent-src" / "agent"
        agent.mkdir(parents=True)
        git = lambda *a: subprocess.run(["git", "-C", str(agent), *a], check=True, capture_output=True)  # noqa: E731
        git("init", "-q")
        (agent / "rag.py").write_text("x = 1\n")
        git("add", ".")
        git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "pin")
        sha = subprocess.run(["git", "-C", str(agent), "rev-parse", "HEAD"], capture_output=True, text=True).stdout
        (here / "AGENT_COMMIT.txt").write_text(f"agent {sha.strip()}\n")
        self.agent = agent
        self.patches = [mock.patch.object(benchmark, "HERE", here), mock.patch.object(benchmark, "AGENT", agent)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_clean_checkout_passes(self):
        benchmark.check_agent()

    def test_bytecode_is_ignored(self):
        (self.agent / "__pycache__").mkdir()
        (self.agent / "__pycache__" / "rag.cpython-313.pyc").write_bytes(b"")
        benchmark.check_agent()

    def test_added_module_stops_the_run(self):
        (self.agent / "extra.py").write_text("x = 2\n")
        with self.assertRaises(SystemExit) as stop:
            benchmark.check_agent()
        self.assertIn("extra.py", str(stop.exception.code))

    def test_edited_file_stops_the_run(self):
        (self.agent / "rag.py").write_text("x = 3\n")
        with self.assertRaises(SystemExit):
            benchmark.check_agent()


QUESTIONS = [
    {"id": "Q01", "primary": [1]}, {"id": "Q02", "primary": []},
    {"id": "Q03", "primary": [1], "not_scored": "needs a live order"},
]


class Arguments(unittest.TestCase):
    """Bad --only and --runs values stop the run with a message, before any setup."""

    def ids(self, only):
        return [c["id"] for c in benchmark.select_cases(only, QUESTIONS)]

    def test_no_only_runs_every_scored_question(self):
        self.assertEqual(self.ids(""), ["Q01", "Q02"])

    def test_only_is_case_and_space_insensitive(self):
        self.assertEqual(self.ids(" q02 , Q01,q01"), ["Q01", "Q02"])

    def test_unknown_id_stops(self):
        for only in ("Q99", "Q01,Q99", ",", "Q1"):
            with self.subTest(only), self.assertRaises(SystemExit) as stop:
                self.ids(only)
            self.assertIsInstance(stop.exception.code, str)

    def test_not_scored_id_stops(self):
        with self.assertRaises(SystemExit) as stop:
            self.ids("Q03")
        self.assertIn("needs a live order", stop.exception.code)

    def test_runs_must_be_positive(self):
        self.assertEqual(benchmark.positive_int("2"), 2)
        for bad in ("0", "-1"):
            with self.subTest(bad), self.assertRaises(Exception):
                benchmark.positive_int(bad)


class Reranker(unittest.TestCase):
    """A reranker that falls back to vector order is retried, then stops the run."""

    class Chunk:
        def __init__(self, vector, rerank):
            self.vector_score, self.rerank_score = vector, rerank
            self.document = mock.Mock(metadata={"chunk_id": 1})

    def runner(self, results):
        r = benchmark.Runner.__new__(benchmark.Runner)
        r.settings = Namespace(fetch_k=20, top_k=4, min_relevance=0.2, min_rerank_score=0.4)
        doc = mock.Mock(metadata={"chunk_id": 1})
        r.assistant = mock.Mock()
        r.assistant.vectorstore.similarity_search_with_score.return_value = [(doc, 0.7)]
        r.assistant.reranker.name = "llm"
        r.assistant.reranker.rerank.side_effect = results
        return r

    def test_fallback_detection(self):
        self.assertTrue(benchmark.is_fallback("llm", [self.Chunk(0.7, 0.7)]))
        self.assertFalse(benchmark.is_fallback("llm", [self.Chunk(0.7, 0.9)]))
        self.assertFalse(benchmark.is_fallback("llm", []))
        self.assertFalse(benchmark.is_fallback("none", [self.Chunk(0.7, 0.7)]))

    def test_retry_recovers(self):
        r = self.runner([[self.Chunk(0.7, 0.7)], [self.Chunk(0.7, 0.9)]])
        found, kept = r.retrieve("q")
        self.assertEqual(found["reranked"], [[1, 0.9]])
        self.assertEqual(r.assistant.reranker.rerank.call_count, 2)

    def test_repeated_fallback_stops(self):
        r = self.runner([[self.Chunk(0.7, 0.7)]] * benchmark.RERANK_ATTEMPTS)
        with self.assertRaises(benchmark.RerankFailed):
            r.retrieve("q")


class Report(unittest.TestCase):
    """A partial run shows only the rows for the kinds of question it holds."""

    def render(self, ids):
        import score, report  # noqa: E401
        src = Path(__file__).resolve().parent.parent / "results" / "openai"
        if not (src / "runs.jsonl").exists() or not score.CASES.exists():
            self.skipTest("needs the published run and cases/questions.json (bash setup.sh)")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "index.json").write_bytes((src / "index.json").read_bytes())
            (out / "config.json").write_bytes((src / "config.json").read_bytes())
            lines = [line for line in (src / "runs.jsonl").read_text(encoding="utf-8").splitlines()
                     if any(f'"id": "{i}"' in line for i in ids)]
            (out / "runs.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
            score.write(out, *score.score_folder(out))
            return report.full_report(out)

    def test_only_questions_with_evidence(self):
        text = self.render(["Q01"])
        self.assertIn("Top 20, after vector search", text)
        self.assertNotIn("No answer in the documents", text)
        self.assertNotIn("0 of 0", text)

    def test_only_no_answer_questions(self):
        text = self.render(["Q15"])
        self.assertIn("No answer in the documents | 1 |", text)
        self.assertNotIn("Top 20, after vector search", text)
        self.assertNotIn("headline", text)
        self.assertNotIn("## All metrics", text)


if __name__ == "__main__":
    unittest.main()
