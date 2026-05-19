from __future__ import annotations

from runtime.operator.consumer import (
    _memory_finder_judgment,
    _prepare_memory_finder_bundle,
)


def test_completed_support_without_safe_cursor_is_typed_unavailable() -> None:
    bundle = {
        "support_facts": [{"text": "plugin agents are a definition supply path"}],
        "source_paths": ["categories/software-development/claude-code/extension-placement/agents.md"],
    }

    prepared, status = _prepare_memory_finder_bundle(
        query_text="plugin agents versus subagent boundary",
        bundle=bundle,
        status="completed",
    )
    judgment = _memory_finder_judgment(
        query_text="plugin agents versus subagent boundary",
        bundle=prepared,
        status=status,
    )

    assert status == "typed_unavailable_unsafe_index_cursor"
    assert prepared["safe_index_cursor"]["status"] == "missing"
    assert prepared["safe_index_cursor"]["final_support_allowed"] is False
    assert prepared["support_bundle"]["safe_index_cursor"]["status"] == "missing"
    assert judgment["judgment"] == "typed_unavailable"
    assert judgment["observation"]["safe_index_cursor_status"] == "missing"
    assert judgment["observation"]["safe_index_cursor_allowed"] is False


def test_completed_support_with_inside_safe_cursor_can_close_as_support_bundle() -> None:
    bundle = {
        "support_facts": [{"text": "plugin agents are a definition supply path"}],
        "source_paths": ["categories/software-development/claude-code/extension-placement/agents.md"],
        "safe_index_cursor": {
            "schema_version": "safe_index_cursor_check.v1",
            "status": "inside",
            "final_support_allowed": True,
            "checked_paths": [
                "vault/categories/software-development/claude-code/extension-placement/agents.md"
            ],
            "rejected_paths": [],
        },
    }

    prepared, status = _prepare_memory_finder_bundle(
        query_text="plugin agents versus subagent boundary",
        bundle=bundle,
        status="completed",
    )
    judgment = _memory_finder_judgment(
        query_text="plugin agents versus subagent boundary",
        bundle=prepared,
        status=status,
    )

    assert status == "completed"
    assert judgment["judgment"] == "success"
    assert judgment["close_decision"] == "support_bundle"
    assert judgment["observation"]["safe_index_cursor_status"] == "inside"
    assert judgment["observation"]["safe_index_cursor_allowed"] is True

