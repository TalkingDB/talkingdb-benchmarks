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


if __name__ == "__main__":
    unittest.main()
