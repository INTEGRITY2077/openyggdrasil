from __future__ import annotations

from typing import Any, Dict, Iterable, List


def planned_observer_commands(*, profiles: Iterable[str], schedule_lint: bool) -> List[Dict[str, Any]]:
    plans: List[Dict[str, Any]] = []
    if schedule_lint:
        for profile in profiles:
            plans.append(
                {
                    "message_type": "execute_lint",
                    "profile": profile,
                    "session_id": None,
                }
            )
    return plans
