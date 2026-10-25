"""Lightweight checks for the isolated adaptive benchmark harness."""
import unittest

from docs.competition.benchmark_learning_plan import build_graph, nearest_rank, run_benchmark


class AdaptiveBenchmarkTests(unittest.TestCase):
    def test_scenarios_are_deterministic_and_bounded(self):
        self.assertEqual(build_graph(9, "chain").model_dump_json(), build_graph(9, "chain").model_dump_json())
        self.assertEqual(len(build_graph(9, "chain").edges), 8)
        self.assertEqual(len(build_graph(9, "independent").edges), 0)
        with self.assertRaises(ValueError):
            build_graph(0, "chain")

    def test_nearest_rank_definition(self):
        self.assertEqual(nearest_rank([8, 2, 4, 6], .50), 4)
        self.assertEqual(nearest_rank([8, 2, 4, 6], .95), 8)

    def test_benchmark_runs_on_synthetic_data(self):
        result = run_benchmark(topics=5, scenario="chain", runs=2, warmups=0)
        self.assertIs(result["synthetic"], True)
        self.assertEqual(result["workload"]["runs"], 2)
        self.assertEqual(result["workload"]["edges"], 4)
        self.assertLessEqual(result["latency_ms"]["min"], result["latency_ms"]["max"])


if __name__ == "__main__":
    unittest.main()
