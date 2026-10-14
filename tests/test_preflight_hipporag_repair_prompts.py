import unittest
import json
import os
import subprocess
import sys
from types import ModuleType, SimpleNamespace

import pytest

from scripts.preflight_hipporag_repair_prompts import (
    UPSTREAM_COMMIT,
    summarize_prompts,
    validate_upstream_pin,
)


@pytest.fixture
def pinned_sdk_tree(tmp_path, monkeypatch):
    from scripts import preflight_hipporag_repair_prompts as preflight

    source = tmp_path / "source"
    package = source / "src/hipporag"
    installed = tmp_path / "installed/hipporag"
    package.mkdir(parents=True)
    installed.mkdir(parents=True)
    content = b"PINNED_VALUE = 1\n"
    for root in (package, installed):
        (root / "__init__.py").write_bytes(content)

    def git(*args):
        # Hooks export GIT_DIR/GIT_INDEX_FILE for the parent checkout. Never let
        # fixture init/add/commit operate on that repository.
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("GIT_")
        }
        return subprocess.check_output(["git", "-C", str(source), *args], env=env)

    git("init", "--quiet")
    git("add", "src/hipporag/__init__.py")
    git(
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "--quiet",
        "-m",
        "Pinned SDK fixture",
    )
    pin = git("rev-parse", "HEAD").decode().strip()
    monkeypatch.setattr(preflight, "UPSTREAM_COMMIT", pin)
    monkeypatch.setattr(
        preflight.importlib_metadata,
        "distribution",
        lambda name: SimpleNamespace(locate_file=lambda relative: installed),
    )
    # No SDK required in the general offline environment. Real Git blobs remain
    # the baseline; fake imports merely stand in for the already verified class.
    module, prompts = ModuleType("hipporag"), ModuleType("hipporag.prompts")
    module.__file__ = str(installed / "__init__.py")
    prompts.PromptTemplateManager = object()
    monkeypatch.setitem(sys.modules, "hipporag", module)
    monkeypatch.setitem(sys.modules, "hipporag.prompts", prompts)
    return preflight, source, package, installed, git, prompts.PromptTemplateManager


def test_sdk_is_verified_against_committed_blobs_with_crlf_checkout(pinned_sdk_tree):
    preflight, source, package, installed, _, manager = pinned_sdk_tree
    (package / "__init__.py").write_bytes(b"PINNED_VALUE = 1\r\n")
    (installed / "__init__.py").write_bytes(b"PINNED_VALUE = 1\r\n")
    assert preflight.verify_target_prompt_installation(source) == (manager, 1)


def test_sdk_git_verification_ignores_parent_hook_repository(
    pinned_sdk_tree, monkeypatch
):
    preflight, source, _, _, _, manager = pinned_sdk_tree
    monkeypatch.setenv("GIT_DIR", str(source / "nonexistent-parent.git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(source / "other-worktree"))
    monkeypatch.setenv("GIT_INDEX_FILE", str(source / "unrelated-index"))
    assert preflight.verify_target_prompt_installation(source) == (manager, 1)


def test_identical_uncommitted_source_and_install_changes_fail_before_http(
    pinned_sdk_tree, monkeypatch
):
    preflight, source, package, installed, git, _ = pinned_sdk_tree
    for root in (package, installed):
        (root / "__init__.py").write_bytes(b"PINNED_VALUE = 999\n")
    assert git("rev-parse", "HEAD").decode().strip() == preflight.UPSTREAM_COMMIT
    assert git("status", "--porcelain").strip()
    assert (package / "__init__.py").read_bytes() == (
        installed / "__init__.py"
    ).read_bytes()
    monkeypatch.setattr(
        preflight,
        "load_source_inputs",
        lambda *args, **kwargs: ({}, [], [], "manifest-sha", "corpus-sha"),
    )
    import requests

    calls = []

    def forbidden(*args, **kwargs):
        calls.append(True)
        raise AssertionError("HTTP must not be reached")

    monkeypatch.setattr(requests.sessions.Session, "request", forbidden)
    with pytest.raises(
        ValueError, match="Source SDK file differs from pinned Git blob"
    ):
        preflight.run_target_preflight(
            SimpleNamespace(
                manifest=source / "unused.json", data_root=source, sdk_source=source
            )
        )
    assert calls == []


def test_changed_installed_file_is_rejected_even_with_clean_source(pinned_sdk_tree):
    preflight, source, _, installed, _, _ = pinned_sdk_tree
    (installed / "__init__.py").write_bytes(b"PINNED_VALUE = 999\n")
    with pytest.raises(
        ValueError, match="Installed SDK file differs from pinned Git blob"
    ):
        preflight.verify_target_prompt_installation(source)


@pytest.mark.parametrize("tree", ["source", "installed"])
def test_untracked_python_files_are_rejected(pinned_sdk_tree, tree):
    preflight, source, package, installed, _, _ = pinned_sdk_tree
    root = package if tree == "source" else installed
    (root / "untracked.py").write_text("EXTRA = True\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Python file set differs from pinned commit"):
        preflight.verify_target_prompt_installation(source)


class HippoRAGRepairPromptPreflightTests(unittest.TestCase):
    def test_prompt_summary_separates_utf8_bytes_from_tokens(self):
        rows = [
            {
                "order": 0,
                "stage": "openie_ner",
                "utf8_bytes": 12,
                "prompt_sha256": "a" * 64,
                "raw_prompt": "private text",
            },
            {
                "order": 1,
                "stage": "openie_ner",
                "utf8_bytes": 20,
                "prompt_sha256": "b" * 64,
            },
            {
                "order": 2,
                "stage": "openie_triples",
                "utf8_bytes": 40,
                "prompt_sha256": "c" * 64,
            },
        ]

        result = summarize_prompts(
            rows,
            model_digest="model-digest",
            num_ctx=4096,
            output_caps={"openie_ner": 1024, "openie_triples": 3072},
        )

        self.assertEqual(result["exact_prompt_token_counts"], None)
        self.assertEqual(
            result["by_stage"]["openie_ner"]["max_rendered_prompt_utf8_bytes"], 20
        )
        self.assertEqual(
            result["by_stage"]["openie_triples"]["max_rendered_prompt_utf8_bytes"], 40
        )
        self.assertNotIn("private text", str(result))
        self.assertEqual(result["model_requests_made"], 0)

    def test_prompt_summary_requires_caps_for_both_stages(self):
        with self.assertRaisesRegex(ValueError, "Both frozen stage output caps"):
            summarize_prompts(
                [], model_digest="m", num_ctx=4096, output_caps={"openie_ner": 1024}
            )

    def test_prompt_renderer_requires_exact_installed_upstream_commit(self):
        direct_url = json.dumps({"vcs_info": {"commit_id": UPSTREAM_COMMIT}})
        self.assertEqual(validate_upstream_pin("2.0.0a5", direct_url), UPSTREAM_COMMIT)
        with self.assertRaisesRegex(ValueError, "version"):
            validate_upstream_pin("2.0.0", direct_url)
        with self.assertRaisesRegex(ValueError, "commit"):
            validate_upstream_pin(
                "2.0.0a5", json.dumps({"vcs_info": {"commit_id": "0" * 40}})
            )


if __name__ == "__main__":
    unittest.main()


def test_target_selection_covers_real_failure_categories_deterministically():
    from scripts.preflight_hipporag_repair_prompts import select_target_failure_cases

    rows = [
        {
            "passage_id": f"{stage}-{i}",
            "stage": stage,
            "attempt": 1,
            "status": "truncated",
            "response_bytes": i * 10,
        }
        for stage in ("openie_ner", "openie_triples")
        for i in range(1, 4)
    ]
    rows += [
        {
            "passage_id": "missing",
            "stage": "openie_ner",
            "attempt": 1,
            "status": "request_error",
            "response_bytes": 0,
        }
    ]
    selected, failed = select_target_failure_cases(rows)
    assert len(selected) == 5 and len(failed) == 7
    assert [r["passage_id"] for r in selected] == [
        "openie_ner-1",
        "openie_ner-3",
        "openie_triples-1",
        "openie_triples-3",
        "missing",
    ]
    assert select_target_failure_cases(list(reversed(rows)))[0] == selected
    rows += [dict(rows[0], attempt=2, status="valid_nonempty")]
    assert "openie_ner-1" not in {
        r["passage_id"] for r in select_target_failure_cases(rows)[0]
    }


def test_target_selection_does_not_invent_missing_categories():
    from scripts.preflight_hipporag_repair_prompts import select_target_failure_cases

    assert select_target_failure_cases([]) == ([], [])
    rows = [
        {
            "passage_id": "p",
            "stage": "openie_ner",
            "attempt": 1,
            "status": "truncated",
            "response_bytes": 1,
        }
    ]
    assert len(select_target_failure_cases(rows)[0]) == 1


def test_target_metadata_never_generates_or_serializes_credentials():
    import json
    from types import SimpleNamespace
    from scripts.preflight_hipporag_repair_prompts import target_capabilities

    calls = []

    class MetadataOnly:
        def get_adapter(self, _):
            return SimpleNamespace(max_retries=SimpleNamespace(total=0))

        def get(self, url, **kwargs):
            calls.append(url)
            assert kwargs["allow_redirects"] is False
            return SimpleNamespace(
                status_code=200,
                json=lambda: {
                    "data": [
                        {
                            "id": "test",
                            "model_name": "test",
                            "api_key": "private",
                            "model_info": {
                                "tokenizer": {"api_key": "private"},
                                "revision": "private",
                            },
                        }
                    ]
                },
            )

        def post(self, *args, **kwargs):
            raise AssertionError("Generation is forbidden")

    result = target_capabilities(
        MetadataOnly(),
        {"base_url": "https://example.test/v1", "model": "test", "key": "private"},
    )
    assert len(calls) == 3
    assert "private" not in json.dumps(result)
    assert all(all(v is None for v in r["limits"].values()) for r in result)


def test_metadata_timeout_is_recorded_without_secret_or_exception_text():
    from types import SimpleNamespace
    import requests
    from scripts.preflight_hipporag_repair_prompts import target_capabilities

    class Failed:
        def get_adapter(self, _):
            return SimpleNamespace(max_retries=SimpleNamespace(total=0))

        def get(self, *_args, **_kwargs):
            raise requests.Timeout("secret-key in upstream failure")

    result = target_capabilities(
        Failed(),
        {"base_url": "https://example.test/v1", "model": "test", "key": "secret-key"},
    )
    assert all(r["error_type"] == "Timeout" for r in result)
    assert "secret-key" not in str(result)


def test_data_root_resolves_historical_relative_corpus(tmp_path):
    import hashlib
    from scripts.plan_hipporag_repair import SOURCE_RUN_ID, load_source_inputs

    corpus = tmp_path / "data" / "corpus.json"
    corpus.parent.mkdir()
    corpus.write_text(
        json.dumps([{"id": "p", "title": "T", "text": "text"}]), encoding="utf-8"
    )
    manifest = tmp_path / f"hipporag2-musique-{SOURCE_RUN_ID}.manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "run_id": SOURCE_RUN_ID,
                "inputs": {
                    "corpus_path": "data/corpus.json",
                    "corpus_sha256": hashlib.sha256(corpus.read_bytes()).hexdigest(),
                },
                "index": {
                    "openie_acceptance_gate": {"expected_passages": 1},
                    "openie_attempts": [],
                },
            }
        ),
        encoding="utf-8",
    )
    result = load_source_inputs(manifest, data_root=tmp_path)
    assert result[1] == ["p"]
    corpus.write_text("changed", encoding="utf-8")
    import pytest

    with pytest.raises(ValueError, match="differs"):
        load_source_inputs(manifest, data_root=tmp_path)


def test_target_check_does_not_accept_valid_json_when_finish_is_length():
    from scripts.openie_protocol import classify_openie_attempt

    assert (
        classify_openie_attempt('{"named_entities": ["Alpha"]}', "length", ["Alpha"])
        == "truncated"
    )
    assert (
        classify_openie_attempt(None, None, None, request_error=True) == "request_error"
    )
    assert (
        classify_openie_attempt("invalid JSON", "stop", None, parse_error=True)
        == "parse_error"
    )
