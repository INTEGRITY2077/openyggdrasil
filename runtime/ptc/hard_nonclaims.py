from __future__ import annotations

from collections.abc import Sequence


HARD_NONCLAIM_WEAKENING_TOKENS = (
    "override global",
    "weaken global",
    "remove global",
    "ignore global",
    "relax global",
    "waive global",
    "claim reasoning lease solved",
    "claim live readiness",
    "claim production readiness",
    "claim production ptc implemented",
    "claim full product readiness",
)


def assert_additive_only_hard_nonclaims(hard_nonclaims: Sequence[str]) -> None:
    normalized = "\n".join(str(value) for value in hard_nonclaims).lower()
    for token in HARD_NONCLAIM_WEAKENING_TOKENS:
        if token in normalized:
            raise ValueError("hard_nonclaims must not weaken global hard nonclaims")
