"""Eval suites in fake mode (CI gate), AUC, label export and offline re-scoring."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from careergraph.domain.models import ShortlistDecision
from careergraph.evals.report import export_labels, write_reports
from careergraph.evals.suites import SUITES, match_suite_from_labels, ranking_auc, run_suite
from tests.conftest import make_settings
from tests.helpers import demo_service


@pytest.mark.parametrize("suite", SUITES)
def test_fake_suites_pass_their_gates(tmp_path: Path, suite: str) -> None:
    r = run_suite(suite, make_settings(tmp_path), "fake")
    assert r.thresholds, "every suite must be gated in fake mode"
    assert r.passed, (r.metrics, r.thresholds)


def test_ranking_auc() -> None:
    assert ranking_auc([3, 4], [1, 2]) == 1.0
    assert ranking_auc([1], [1]) == 0.5
    assert ranking_auc([1], [2]) == 0.0


def test_reports_carry_the_fake_mode_disclaimer(tmp_path: Path) -> None:
    r = run_suite("injection", make_settings(tmp_path), "fake")
    js, md = write_reports([r], tmp_path / "evals")
    assert "NOT model quality" in md.read_text() and js.exists()


def test_export_labels_and_offline_rescore(tmp_path: Path) -> None:
    with demo_service(tmp_path) as svc:
        out = svc.start_run()
        items = out.payload["items"]  # type: ignore[index]
        svc.approve_shortlist(out.thread_id, [
            ShortlistDecision(job_id=items[0]["job_id"], decision="approve"),
            ShortlistDecision(job_id=items[-1]["job_id"], decision="reject"),
        ])  # fmt: skip
        target = tmp_path / "labels.yaml"
        assert export_labels(svc.repo, target) == 2
        data = yaml.safe_load(target.read_text())
        assert data[items[0]["job_id"]]["label"] == "approve"
        r = match_suite_from_labels(svc.cfg, svc.repo, target, svc.store)
        assert set(r.metrics) == {"precision_at_shortlist", "recall_at_shortlist", "ranking_auc"}
        assert r.metrics["ranking_auc"] == 1.0
