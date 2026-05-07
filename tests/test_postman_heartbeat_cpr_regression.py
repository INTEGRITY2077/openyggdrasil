from __future__ import annotations

import operator  # noqa: F401 - stdlib pre-import prevents runtime/operator shadowing in this repo layout.
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))

from delivery.postman_heartbeat_cpr_regression import run_postman_heartbeat_cpr_regression


def test_postman_heartbeat_cpr_regression_harness_passes_in_isolated_workspace() -> None:
    summary = run_postman_heartbeat_cpr_regression()

    assert summary["schema_version"] == "postman_heartbeat_cpr_regression.v1"
    assert summary["status"] == "pass"
    assert all(summary["checks"].values())
    assert summary["checks"]["delivery_created"] is True
    assert summary["checks"]["readback_message_id_matches"] is True
    assert summary["checks"]["korean_expansion_preserved"] is True
    assert summary["checks"]["korean_nonclaims_preserved"] is True
    assert summary["checks"]["payload_has_no_local_paths"] is True
    assert summary["cleanup"]["workspace_exists_after_run"] is False
    assert summary["observed"]["korean_expansion_tokens"] == ["ko_cho:ㅎㄱ", "ko_qwerty:gksrmf"]
    assert summary["hard_nonclaims"]["full_ux_passed"] is False
    assert summary["hard_nonclaims"]["postman_semantic_quality_owner"] is False


def test_postman_heartbeat_cpr_regression_harness_can_use_caller_workspace(tmp_path: Path) -> None:
    summary = run_postman_heartbeat_cpr_regression(workspace_root=tmp_path)

    assert summary["status"] == "pass"
    assert summary["cleanup"]["mode"] == "caller_owned_workspace"
    assert summary["cleanup"]["workspace_exists_after_run"] is True
    assert (tmp_path / ".yggdrasil").exists()
