"""No-request checks for the bounded context pilot."""

import unittest

from scripts.measure_hipporag_repair_context import select_pilot_prompts


class ContextPilotTests(unittest.TestCase):
    def test_selects_one_longest_known_prompt_per_stage(self):
        rows = [
            {"order": 0, "stage": "openie_ner", "utf8_bytes": 12},
            {"order": 1, "stage": "openie_ner", "utf8_bytes": 20},
            {"order": 2, "stage": "openie_triples", "utf8_bytes": 40},
        ]
        self.assertEqual([row["order"] for row in select_pilot_prompts(rows)], [1, 2])
        with self.assertRaisesRegex(ValueError, "openie_triples"):
            select_pilot_prompts(rows[:2])


if __name__ == "__main__":
    unittest.main()
