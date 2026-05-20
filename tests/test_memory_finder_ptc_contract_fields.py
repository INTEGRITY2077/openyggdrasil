from __future__ import annotations

from runtime.operator.consumer import _promote_ptc_contract_fields


def test_promote_ptc_contract_fields_exposes_selected_capability_class_from_role_mode() -> None:
    bundle = {
        "tst_capability_supervisor": {
            "schema_version": "openyggdrasil_tst_supervisor_result.v1",
            "role": "memory_finder",
            "mode": "read_only_retrieval",
            "worker_authored_ptc_program": {
                "worker_authored_ptc_program_ref": "ptc-program-ref://memory_finder/example",
                "code_hash": "sha256:" + "a" * 64,
            },
            "tst_capability_allowlist": {
                "schema_version": "tst_capability_allowlist.v1",
                "selected_capabilities": ["locate_region"],
            },
            "ptc_program_observation": {
                "schema_version": "ptc_program_observation.v1",
                "executed_steps": ["locate_region"],
            },
        }
    }

    promoted = _promote_ptc_contract_fields(bundle)

    assert promoted["selected_capability_class"] == "memory_finder/read_only_retrieval"
    assert promoted["worker_authored_ptc_program_ref"] == "ptc-program-ref://memory_finder/example"
    assert promoted["code_hash"] == "sha256:" + "a" * 64
    assert promoted["capability_allowlist"]["selected_capabilities"] == ["locate_region"]
    assert promoted["execution_trace"]["executed_steps"] == ["locate_region"]
