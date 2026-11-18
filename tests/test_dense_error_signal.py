"""Inference-only feature, frozen decision, no leakage and paired offline CLI."""

import hashlib
import json
from pathlib import Path, PurePosixPath
import socket

import pytest

from scripts import dense_error_signal as signal


def test_direction_and_gold_not_accepted():
    assert signal.error_signal((0.9, 0.8, 0.7, 0.6, 0.5)) == -0.9
    assert signal.error_signal((0.1, 0, -0.1, -0.2, -0.3)) > -0.9
    with pytest.raises(ValueError):
        signal.error_signal({"scores": [0.9] * 5, "gold": "x", "em": 1})


@pytest.mark.parametrize(
    "scores",
    [
        (),
        (0.5,),
        (True,) * 5,
        (float("nan"),) * 5,
        (float("inf"),) * 5,
        (1.1,) * 5,
        (0, 1, 0, 0, 0),
        (None,) * 5,
    ],
)
def test_bad_features_stop(scores):
    with pytest.raises(ValueError):
        signal.error_signal(scores)


@pytest.mark.parametrize(
    "scores,targets,expected",
    [
        ([0, 1], [0, 1], 1),
        ([0, 1], [1, 0], 0),
        ([1, 1], [0, 1], 0.5),
        ([0, 2, 1, 1], [0, 1, 0, 1], 0.875),
        ([1, 2], [0, 0], None),
        ([1, 2], [1, 1], None),
    ],
)
def test_auroc_ties_direction_single_class(scores, targets, expected):
    assert signal.auroc(scores, targets) == expected
    assert signal.auroc(list(reversed(scores)), list(reversed(targets))) == expected


@pytest.mark.parametrize(
    "scores,targets",
    [
        ([], []),
        ([1], []),
        ([float("nan")], [0]),
        ([1], [None]),
        ([1], [True]),
        ([1], [2]),
    ],
)
def test_bad_scores_targets(scores, targets):
    with pytest.raises(ValueError):
        signal.auroc(scores, targets)


@pytest.mark.parametrize(
    "alias", ["identical", "parent_traversal", "relative", "json_temporary"]
)
def test_cli_rejects_output_alias_before_calculation_or_writes(
    tmp_path, monkeypatch, capsys, alias
):
    artifacts = tmp_path / "artifacts"
    cache = artifacts / ".cache"
    cache.mkdir(parents=True)
    private = cache / "shared.csv"
    public = private
    if alias == "parent_traversal":
        (cache / "nested").mkdir()
        public = cache / "nested" / ".." / "shared.csv"
    elif alias == "relative":
        monkeypatch.chdir(tmp_path)
        public = Path("artifacts/.cache/shared.csv")
    elif alias == "json_temporary":
        public = cache / "result.json"
        private = cache / "result.json.part"

    def forbidden(*args, **kwargs):
        raise AssertionError("Output collision must fail before computation or writing")

    monkeypatch.setattr(signal, "verify_freeze", forbidden)
    monkeypatch.setattr(signal, "evaluate", forbidden)
    monkeypatch.setattr(signal.dense, "write_json_atomic", forbidden)
    with pytest.raises(ValueError, match="public_private_output_collision"):
        signal.main(
            [
                "evaluate",
                "--artifact-root",
                str(artifacts),
                "--decision",
                str(tmp_path / "decision.json"),
                "--freeze-commit",
                "a" * 40,
                "--data-root",
                str(tmp_path / "data"),
                "--private-output",
                str(private),
                "--output",
                str(public),
            ]
        )
    assert not private.exists() and not public.exists()
    assert not list(cache.rglob("*.part"))
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("destination", ["json", "part"])
@pytest.mark.parametrize("alias", ["case", "hardlink"])
def test_cli_preserves_csv_when_file_identity_collides(
    tmp_path, monkeypatch, capsys, destination, alias
):
    artifacts = tmp_path / "artifacts"
    cache = artifacts / ".cache"
    cache.mkdir(parents=True)
    public = cache / "result.json"
    candidate = public if destination == "json" else public.with_suffix(".json.part")
    private = cache / "private.csv"
    if alias == "case":
        probe = cache / "CaseProbe"
        probe.touch()
        if not probe.with_name("caseprobe").exists():
            pytest.skip("Requires a case-insensitive filesystem")
        private = candidate.with_name(candidate.name.upper())
        if private.resolve() == candidate.resolve():
            # Windows Path equality may catch this early. Emulate macOS's
            # lexical comparison while retaining the real volume for samefile.
            resolve = type(candidate).resolve

            def lexical_resolve(path, *args, **kwargs):
                resolved = resolve(path, *args, **kwargs)
                if str(path) == str(candidate):
                    return PurePosixPath(resolved.as_posix())
                return resolved

            monkeypatch.setattr(type(candidate), "resolve", lexical_resolve)

    csv_bytes = b"question_id,signal,error\nsynthetic,0.1,1\n"

    if alias == "hardlink":
        open_path = type(private).open

        def link_after_creation(path, *args, **kwargs):
            stream = open_path(path, *args, **kwargs)
            if path == private and args == ("xb",):
                candidate.hardlink_to(private)
            return stream

        monkeypatch.setattr(type(private), "open", link_after_creation)

    monkeypatch.setattr(signal, "verify_freeze", lambda *args: {})
    monkeypatch.setattr(signal, "evaluate", lambda *args: ({"public": True}, csv_bytes))
    with pytest.raises(ValueError, match="public_private_output_collision"):
        signal.main(
            [
                "evaluate",
                "--artifact-root",
                str(artifacts),
                "--decision",
                str(tmp_path / "decision.json"),
                "--freeze-commit",
                "a" * 40,
                "--data-root",
                str(tmp_path / "data"),
                "--private-output",
                str(private),
                "--output",
                str(public),
            ]
        )
    assert private.samefile(candidate)
    assert private.read_bytes() == csv_bytes
    if destination == "part":
        assert not public.exists()
    assert capsys.readouterr().out == ""


def test_saved_feature_projection_does_not_access_answer_or_metrics(
    tmp_path, monkeypatch
):
    class Guard(dict):
        def __getitem__(self, key):
            assert key not in ("answer", "gold", "metrics", "em", "f1")
            return super().__getitem__(key)

    saved = Guard(
        dataset="musique",
        method="dense",
        question_id="synthetic",
        retrieval={"kind": "passages", "scores": [0.5] * 5},
    )
    monkeypatch.setattr(signal.dense, "sha256_file", lambda p: "sha")
    monkeypatch.setattr(signal.dense, "read_json", lambda p: saved)
    scores, _ = signal.saved_features(
        {
            signal.e2.case_key("musique", "dense", "synthetic"): (
                tmp_path / "case.json",
                "sha",
            )
        },
        "musique",
        "synthetic",
    )
    assert signal.error_signal(scores) == -0.5


def test_run_dense_drift_rejected_before_its_json_reader(tmp_path, monkeypatch):
    (tmp_path / "scripts").mkdir()
    dependency = tmp_path / "scripts/run_dense.py"
    dependency.write_bytes(b"changed dependency")
    decision = tmp_path / "freeze.json"
    decision.write_bytes(b"{}")
    monkeypatch.setattr(signal, "ROOT", tmp_path)
    monkeypatch.setattr(
        signal.subprocess,
        "check_output",
        lambda args, **kw: b"{}"
        if args[2].endswith(":freeze.json")
        else b"original dependency",
    )
    monkeypatch.setattr(signal.subprocess, "run", lambda *args, **kw: None)

    def forbidden_reader(*args):
        raise AssertionError("Changed IO dependency must not read the freeze")

    monkeypatch.setattr(signal.dense, "read_json", forbidden_reader)
    with pytest.raises(ValueError, match="run_dense.py"):
        signal.verify_freeze(decision, "a" * 40)


def test_imported_run_dense_must_match_freeze_too(tmp_path, monkeypatch):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts/run_dense.py").write_bytes(b"original dependency")
    imported = tmp_path / "other_run_dense.py"
    imported.write_bytes(b"different imported dependency")
    decision = tmp_path / "freeze.json"
    decision.write_bytes(b"{}")
    monkeypatch.setattr(signal, "ROOT", tmp_path)
    monkeypatch.setattr(signal.dense, "__file__", str(imported))
    monkeypatch.setattr(
        signal.subprocess,
        "check_output",
        lambda args, **kw: b"{}"
        if args[2].endswith(":freeze.json")
        else b"original dependency",
    )
    monkeypatch.setattr(signal.subprocess, "run", lambda *args, **kw: None)
    with pytest.raises(ValueError, match="run_dense.py"):
        signal.verify_freeze(decision, "a" * 40)


def test_real_cli_freeze_before_labels_private_output_and_reproducibility(
    tmp_path, monkeypatch
):
    repo, artifacts, data = (tmp_path / n for n in ("repo", "artifacts", "data"))
    (repo / "scripts").mkdir(parents=True)
    original_root = signal.ROOT
    for name in signal.CODE_FILES:
        (repo / "scripts" / name).write_bytes(
            (original_root / "scripts" / name).read_bytes()
        )
    monkeypatch.setattr(signal, "ROOT", repo)
    ids = [f"private-{i:03}" for i in range(500)]
    metadata = {}
    for dataset in signal.DATASETS:
        labels = data / f"data/processed/{dataset}/labels.json"
        labels.parent.mkdir(parents=True)
        labels.write_text(
            json.dumps(
                [{"id": q, "answer": "yes", "supporting_ids": ["p"]} for q in ids]
            )
        )
        metadata[dataset] = {
            "labels_sha256_evaluation_only": signal.dense.sha256_file(labels)
        }
    accesses, label_reads = [], []

    def inputs(*args):
        with pytest.raises(AssertionError, match="signal_network_forbidden"):
            socket.socket().connect(("localhost", 9))
        return ids, {}, metadata[args[-1]]

    def features(refs, dataset, qid):
        i = ids.index(qid)
        assert i < 400  # Reserved labels/features are never evaluated.
        accesses.append(i)
        return (0.5 if i % 2 else 0.2,) * 5, {
            "question_id": qid,
            "method": "dense",
            "status": "completed",
            "answer": "yes" if i % 2 else "wrong",
            "retrieval": {"source_ids": ["p"]},
            "run_id": "synthetic",
        }

    monkeypatch.setattr(signal, "inputs", inputs)
    monkeypatch.setattr(signal, "saved_features", features)
    read_json = signal.dense.read_json
    committed = {}

    def guarded_read(path):
        if Path(path).name == "labels.json":
            assert committed, "labels read before commit"
            label_reads.append(path)
        return read_json(path)

    monkeypatch.setattr(signal.dense, "read_json", guarded_read)
    decision = repo / "results/summary/signal-freeze.json"
    signal.main(
        ["freeze", "--artifact-root", str(artifacts), "--decision", str(decision)]
    )
    assert set(accesses) == set(range(300)) and not label_reads
    committed.update(
        {
            p.relative_to(repo).as_posix(): p.read_bytes()
            for p in repo.rglob("*")
            if p.is_file()
        }
    )
    monkeypatch.setattr(
        signal.subprocess,
        "check_output",
        lambda args, **kw: committed[args[2].split(":", 1)[1]],
    )
    monkeypatch.setattr(signal.subprocess, "run", lambda *a, **kw: None)
    with pytest.raises(ValueError, match="freeze_overwrite"):
        signal.main(
            ["freeze", "--artifact-root", str(artifacts), "--decision", str(decision)]
        )
    original = decision.read_bytes()
    decision.write_text("{}")
    with pytest.raises(ValueError, match="freeze_not_committed"):
        signal.verify_freeze(decision, "a" * 40)
    decision.write_bytes(original)
    # Existing historical freezes must be supplemented from their Git blob,
    # never by rewriting them or trusting the current run_dense.py hash.
    legacy = json.loads(original)
    del legacy["code_sha256_lf"]["run_dense.py"]
    legacy_bytes = json.dumps(legacy).encode("utf-8")
    for payload in (original, legacy_bytes):
        decision.write_bytes(payload)
        committed[decision.relative_to(repo).as_posix()] = payload
        assert signal.verify_freeze(decision, "a" * 40)["version"] == signal.VERSION
        dependency = repo / "scripts/run_dense.py"
        baseline = dependency.read_bytes()
        dependency.write_bytes(baseline + b"\n# changed after freeze\n")
        with pytest.raises(ValueError, match="run_dense.py"):
            signal.verify_freeze(decision, "a" * 40)
        dependency.write_bytes(baseline)
    decision.write_bytes(original)
    committed[decision.relative_to(repo).as_posix()] = original
    with pytest.raises(ValueError, match="full_freeze_commit"):
        signal.verify_freeze(decision, "short")
    args = [
        "evaluate",
        "--artifact-root",
        str(artifacts),
        "--decision",
        str(decision),
        "--freeze-commit",
        "a" * 40,
        "--data-root",
        str(data),
    ]
    with pytest.raises(ValueError, match="private_output"):
        signal.main(
            args
            + [
                "--private-output",
                str(repo / "results/summary/leak.csv"),
                "--output",
                str(repo / "bad.json"),
            ]
        )
    accesses.clear()
    reports = []
    for i in range(2):
        output = repo / f"report-{i}.json"
        private = artifacts / f".cache/private-{i}.csv"
        signal.main(args + ["--private-output", str(private), "--output", str(output)])
        reports.append(read_json(output))
        assert (
            reports[-1]["private_csv_sha256"]
            == hashlib.sha256(private.read_bytes()).hexdigest()
        )
        assert (
            "private-300" not in output.read_text()
            and "question_id" not in output.read_text()
        )
        assert len(private.read_text().splitlines()) == 201
    assert set(accesses) == set(range(300, 400))
    assert reports[0]["analytical_digest"] == reports[1]["analytical_digest"]
    assert reports[0]["private_csv_sha256"] == reports[1]["private_csv_sha256"]
    assert all(r["auroc"] == 1 and r["errors"] == 50 for r in reports[0]["datasets"])
    changed = repo / "scripts/dense_error_signal.py"
    changed.write_text("changed")
    with pytest.raises(ValueError, match="signal_code_changed"):
        signal.verify_freeze(decision, "a" * 40)
