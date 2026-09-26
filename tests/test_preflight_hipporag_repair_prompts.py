import unittest
import json

from scripts.preflight_hipporag_repair_prompts import (
    UPSTREAM_COMMIT, summarize_prompts, validate_upstream_pin,
)


class HippoRAGRepairPromptPreflightTests(unittest.TestCase):
    def test_prompt_summary_separates_utf8_bytes_from_tokens(self):
        rows = [
            {"order": 0, "stage": "openie_ner", "utf8_bytes": 12,
             "prompt_sha256": "a" * 64, "raw_prompt": "private text"},
            {"order": 1, "stage": "openie_ner", "utf8_bytes": 20,
             "prompt_sha256": "b" * 64},
            {"order": 2, "stage": "openie_triples", "utf8_bytes": 40,
             "prompt_sha256": "c" * 64},
        ]

        result = summarize_prompts(
            rows, model_digest="model-digest", num_ctx=4096,
            output_caps={"openie_ner": 1024, "openie_triples": 3072})

        self.assertEqual(result["exact_prompt_token_counts"], None)
        self.assertEqual(result["by_stage"]["openie_ner"][
            "max_rendered_prompt_utf8_bytes"], 20)
        self.assertEqual(result["by_stage"]["openie_triples"][
            "max_rendered_prompt_utf8_bytes"], 40)
        self.assertNotIn("private text", str(result))
        self.assertEqual(result["model_requests_made"], 0)

    def test_prompt_summary_requires_caps_for_both_stages(self):
        with self.assertRaisesRegex(ValueError, "Both frozen stage output caps"):
            summarize_prompts([], model_digest="m", num_ctx=4096,
                              output_caps={"openie_ner": 1024})

    def test_prompt_renderer_requires_exact_installed_upstream_commit(self):
        direct_url = json.dumps({"vcs_info": {"commit_id": UPSTREAM_COMMIT}})
        self.assertEqual(validate_upstream_pin("2.0.0a5", direct_url), UPSTREAM_COMMIT)
        with self.assertRaisesRegex(ValueError, "version"):
            validate_upstream_pin("2.0.0", direct_url)
        with self.assertRaisesRegex(ValueError, "commit"):
            validate_upstream_pin("2.0.0a5", json.dumps(
                {"vcs_info": {"commit_id": "0" * 40}}))


if __name__ == "__main__":
    unittest.main()
