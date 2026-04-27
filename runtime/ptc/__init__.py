"""PTC execution substrate package.

This package starts as a no-behavior-change skeleton. Existing Pathfinder and
programmatic tool runtime entry points stay on their current import paths until
an extraction slice is covered by compatibility tests.
"""

from __future__ import annotations

from .compat import (
    CLAIM_SCOPE,
    EXTRACTED_SURFACES,
    LEGACY_IMPORT_SURFACES,
    PACKAGE_STATUS,
    compatibility_policy,
)
from .engine import render_default_pathfinder_program

__all__ = [
    "CLAIM_SCOPE",
    "EXTRACTED_SURFACES",
    "LEGACY_IMPORT_SURFACES",
    "PACKAGE_STATUS",
    "compatibility_policy",
    "render_default_pathfinder_program",
]
