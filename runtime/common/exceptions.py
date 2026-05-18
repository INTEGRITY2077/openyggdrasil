"""Shared runtime exception contracts.

Use these contracts only for degraded-path guards where the runtime should
return typed unavailable, skip an optional capability, or record a diagnostic
instead of crashing. They intentionally exclude programmer-error families such
as ``TypeError``, ``KeyError``, and ``RuntimeError``.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess


_OPTIONAL_VALIDATION_ERRORS: list[type[BaseException]] = []
_OPTIONAL_PARSE_ERRORS: list[type[BaseException]] = []

try:
    import jsonschema
except ImportError:
    jsonschema = None

if jsonschema is not None:
    _OPTIONAL_VALIDATION_ERRORS.extend(
        [
            jsonschema.ValidationError,
            jsonschema.SchemaError,
        ]
    )

try:
    import yaml
except ImportError:
    yaml = None

if yaml is not None:
    _OPTIONAL_PARSE_ERRORS.append(yaml.YAMLError)


OPTIONAL_IMPORT_ERRORS = (ImportError,)

IO_RUNTIME_ERRORS = (
    OSError,
    TimeoutError,
    UnicodeError,
    json.JSONDecodeError,
    sqlite3.Error,
    subprocess.SubprocessError,
    *_OPTIONAL_PARSE_ERRORS,
)

VALIDATION_RUNTIME_ERRORS = (
    ValueError,
    *_OPTIONAL_VALIDATION_ERRORS,
)

RECOVERABLE_RUNTIME_ERRORS = (
    *OPTIONAL_IMPORT_ERRORS,
    *IO_RUNTIME_ERRORS,
    *VALIDATION_RUNTIME_ERRORS,
)
