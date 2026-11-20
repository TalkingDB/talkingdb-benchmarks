import unittest

from benchmark import (
    BM25,
    answer_options,
    evidence_for,
    named_specs,
    paired,
    score_answer,
)
from sources import read_json
from ttt_evaluate import checked_order
from ttt_rank import INPUTS, runtime_pins


class BenchmarkTests(unittest.TestCase):
    def setUp(self):
        self.specs = read_json("sources.json")
        self.entries = read_json("definitions.json")
        self.rows = {entry["id"]: entry for entry in self.entries}
        self.development = read_json("cases/development.json")
        self.evaluation = read_json("cases/evaluation.json")

    def test_family_split_and_gold_sources(self):
        self.assertTrue({c["acronym"] for c in self.development}.isdisjoint(c["acronym"] for c in self.evaluation))
        cases = self.development + self.evaluation
        self.assertEqual(len(cases), len({c["id"] for c in cases}))
        self.assertEqual(sum("citations" in c["expected"] for c in cases), 60)
        for case in cases:
            with self.subTest(case=case["id"]):
                scope = named_specs(case["question"])
                for citation in case["expected"].get("citations", []):
                    row = self.rows[citation]
                    self.assertEqual(row["acronym"], case["acronym"])
                    self.assertIn(row["expansion"].casefold(), {e.casefold() for e in case["expected"]["expansions"]})
                    if scope:
                        self.assertIn(row["spec"], scope)

    def test_wrong_scope_and_missing_visible_evidence_fail(self):
        case = next(c for c in self.evaluation if c["id"] == "CA-01")
        expected = case["expected"]
        correct = self.rows[expected["citations"][0]]
        self.assertEqual(score_answer(expected, correct, [correct["id"]]), "grounded_answer")
        self.assertEqual(score_answer(expected, correct, []), "wrong_or_missing_citation")
        same_expansion = next(r for r in self.entries if r["expansion"] == correct["expansion"] and r["id"] != correct["id"])
        self.assertEqual(score_answer(expected, same_expansion, [same_expansion["id"]]), "wrong_or_missing_citation")
        wrong = next(r for r in self.entries if r["acronym"] == "CA" and r["spec"] == "33.310")
        self.assertEqual(score_answer(expected, wrong, [wrong["id"]]), "wrong_expansion")

    def test_abstention_and_visible_competition(self):
        cases = [next(c for c in self.evaluation if c["kind"] == kind) for kind in ("ambiguous", "unsupported")]
        bm25 = BM25(self.entries, self.specs)
        for case in cases:
            with self.subTest(case=case["id"]):
                self.assertEqual(score_answer(case["expected"], None, []), "correct_abstention")
                ranking = evidence_for("scoped_prototype", case["question"], case["acronym"], self.entries, bm25)
                if case["kind"] == "ambiguous":
                    self.assertGreater(len({e["expansion"] for e in ranking}), 1)
                else:
                    self.assertEqual(ranking, [])
                guess = next(e for e in self.entries if e["acronym"] == case["acronym"])
                self.assertEqual(score_answer(case["expected"], guess, [guess["id"]]), "guessed_on_control")

    def test_option_order_does_not_depend_on_gold(self):
        case = self.development[0]
        self.assertEqual(answer_options(case, self.entries), answer_options({**case, "expected": {}}, self.entries))

    def test_paired_statistics(self):
        rows = [
            {"id": "a", "family": "A", "verdict": "grounded_answer", "recall_at_3": True},
            {"id": "b", "family": "B", "verdict": "missed_answer", "recall_at_3": False},
        ]
        other = [{**rows[0], "verdict": "missed_answer"}, {**rows[1], "verdict": "grounded_answer"}]
        comparison = paired(rows, other)
        self.assertEqual((comparison["wins"], comparison["losses"], comparison["ties"]), (1, 1, 0))
        self.assertEqual(comparison["family_mean_delta"], 0)

    def test_ttt_ranking_is_rejected_for_wrong_specification(self):
        from benchmark import dataset_hash
        from sources import ROOT

        case = next(c for c in self.evaluation if c["id"] == "CA-01")
        valid_id = case["expected"]["citations"][0]
        wrong_id = next(row["id"] for row in self.entries if row["acronym"] == "CA" and row["spec"] == "33.310")
        item = {"evidence_ids": [valid_id], "elements": [{"evidence_ids": [valid_id]}], "retrieval_seconds": 0.1}
        report = {"dataset_hashes": {path: dataset_hash(ROOT / path) for path in INPUTS},
                  "commits": runtime_pins(), "k": 3, "rankings": {case["id"]: item}}
        self.assertEqual(checked_order(report, [case], self.rows), report["dataset_hashes"])
        item["evidence_ids"] = [wrong_id]
        item["elements"] = [{"evidence_ids": [wrong_id]}]
        with self.assertRaisesRegex(ValueError, "document scope"):
            checked_order(report, [case], self.rows)


if __name__ == "__main__":
    unittest.main()
