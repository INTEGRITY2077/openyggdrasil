from __future__ import annotations

from typing import Any

from runtime.common.portable_ref import validate_public_ref


def safe_portable_ref(value: Any, *, field_name: str) -> str:
    return validate_public_ref(value, field=field_name)
