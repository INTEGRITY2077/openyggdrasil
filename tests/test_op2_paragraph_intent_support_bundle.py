import operator  # noqa: F401 - stdlib pre-import prevents runtime/operator shadowing in this repo layout.
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))

from runtime.retrieval.pathfinder_tools import build_ring_support_bundle


VAULT = Path(__file__).resolve().parent / "fixtures" / "op2_support_bundle_vault"
SCHEMA = Path(__file__).resolve().parents[1] / "contracts" / "typed_unavailable.v1.schema.json"


def test_prn_support_bundle_exposes_paragraph_intent_source_community_and_currentness():
    bundle = build_ring_support_bundle(
        query_text="PRN-e9e232e3e9e65c05 Provider autonomous salience trigger paragraph intent safety belt source lineage",
        vault_root=VAULT,
    )

    assert bundle["schema_version"] == "ring_support_bundle.v1"
    assert bundle["topic_id"] == "PRN-e9e232e3e9e65c05"
    assert bundle["ring_id"] == "ring-99453dc626bb5045"
    assert bundle["community_id"] == "community:openyggdrasil-provider-behavior-contract-memory-authoring-bridge"
    assert bundle["source_ref"] == "hermes-session-json://oy-live-hook-proof-1778026500"
    assert bundle["origin_locator"] == "hermes-session-json://oy-live-hook-proof-1778026500#message_index=0..1"
    assert bundle["provider_session_id"] == "oy-live-hook-proof-1778026500"
    assert bundle["message_index_range"] == {"start": 0, "end": 1}
    assert bundle["anchor_hash"] == "27fbbb875f07345c48df8bba87ca3354a305dcc8d49fc287cb29567f8944d5f4"
    assert bundle["commit_watermark"] == "session:oy-live-hook-proof-1778026500:message_index:1"
    assert bundle["lifecycle_state"] == "ACTIVE"
    assert bundle["current_authority"] == "active"

    safety_belt = bundle["paragraph_intent_safety_belt"]
    assert safety_belt["intent_field"].startswith("Provider 기억 보존은 사용자 explicit 명령")
    assert safety_belt["decomposition_guard"] == "preserve_paragraph_intent_before_decision_atoms"
    assert safety_belt["min_split_unit"] == "paragraph_intent"
    assert safety_belt["category_community_hint"] == "OpenYggdrasil provider behavior contract / memory authoring bridge"
    assert bundle.get("typed_unavailable") is None

    source_paths = "\n".join(bundle["source_paths"])
    assert "vault/queries/provider는-사용자-저장-명령" in source_paths
    assert "vault/_meta/provenance/provider는-사용자-저장-명령" in source_paths
    assert "vault/concepts/PRN-e9e232e3e9e65c05.md" in source_paths
    assert "vault/communities/openyggdrasil-provider-behavior-contract-memory-authoring-bridge.md" in source_paths


def test_ring_support_bundle_fails_closed_with_typed_unavailable_shape():
    bundle = build_ring_support_bundle(
        query_text="zzzz_unresolved_anchor_20260506_no_shared_tokens",
        vault_root=VAULT,
    )

    unavailable = bundle["typed_unavailable"]
    schema = Draft202012Validator.META_SCHEMA  # force import-time availability check
    assert schema
    contract = __import__("json").loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator(contract).validate(unavailable)
    assert unavailable["reason_code"] == "unresolved_evidence_ref"
    assert unavailable["blocked_stage"] == "recall_support_bundle"
    assert unavailable["fabricated_answer"] is False
    assert unavailable["raw_provider_material_included"] is False
