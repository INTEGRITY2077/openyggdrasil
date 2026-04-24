from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

import jsonschema


OPENYGGDRASIL_ROOT = Path(__file__).resolve().parents[2]
MAILBOX_SCHEMA_PATH = (
    OPENYGGDRASIL_ROOT
    / "providers"
    / "hermes"
    / "projects"
    / "harness"
    / "mailbox.v1.schema.json"
)


@lru_cache(maxsize=1)
def load_schema() -> Dict[str, Any]:
    return json.loads(MAILBOX_SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_message(message: Dict[str, Any]) -> None:
    jsonschema.validate(instance=message, schema=load_schema())
