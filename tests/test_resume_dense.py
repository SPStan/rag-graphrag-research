import unittest

from scripts.resume_dense import validate_resume_prefix


class DenseResumeTests(unittest.TestCase):
    def _row(self, qid, run_id="run", expected=None, done=True):
        return {"question_id": qid, "run_id": run_id,
                "planned_question_ids": expected or ["q1", "q2", "q3"],
                "done": done, "done_reason": "stop" if done else None}

    def test_accepts_only_complete_ordered_prefix_for_same_run(self):
        expected = ["q1", "q2", "q3"]
        rows = [self._row("q1", expected=expected), self._row("q2", expected=expected)]
        self.assertEqual(validate_resume_prefix(rows, expected, "run"), 2)

    def test_rejects_reordered_or_duplicate_prefix(self):
        expected = ["q1", "q2", "q3"]
        with self.assertRaisesRegex(ValueError, "ordered prefix"):
            validate_resume_prefix([self._row("q2", expected=expected)], expected, "run")
        with self.assertRaisesRegex(ValueError, "ordered prefix"):
            validate_resume_prefix([self._row("q1", expected=expected),
                                    self._row("q1", expected=expected)], expected, "run")

    def test_rejects_rows_from_another_run_or_incomplete_generation(self):
        expected = ["q1", "q2"]
        with self.assertRaisesRegex(ValueError, "does not match"):
            validate_resume_prefix([self._row("q1", run_id="other", expected=expected)],
                                   expected, "run")
        with self.assertRaisesRegex(ValueError, "does not match"):
            validate_resume_prefix([self._row("q1", expected=expected, done=False)],
                                   expected, "run")


if __name__ == "__main__":
    unittest.main()
