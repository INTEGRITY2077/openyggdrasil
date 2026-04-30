"""Read and validate .skill.md YAML frontmatter.

This module is the Plane B 'reader' — the code that consumes .skill.md
execution directives so the PTC engine can make effort-class routing
decisions.  It parses only the YAML frontmatter (between ``---`` fences)
and validates it against ``contracts/module_skill.v1.schema.json``.

Body markdown after the closing ``---`` is deliberately ignored.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

try:
    import jsonschema  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover – optional at import time
    jsonschema = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(
    r"\A\s*---\s*\n(.*?)\n---\s*\n",
    re.DOTALL,
)

_CONTRACTS_ROOT = Path(__file__).resolve().parents[2] / "contracts"
_SCHEMA_PATH = _CONTRACTS_ROOT / "module_skill.v1.schema.json"

EFFORT_ORDER: dict[str, int] = {"high": 3, "medium": 2, "low": 1}


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SkillMetadata:
    """Parsed and validated .skill.md frontmatter."""

    name: str
    description: str
    chain_position: str
    effort_class: str
    requires_reasoning: bool
    bundle_eligible: bool
    output_contract: str
    shared_context: tuple[str, ...] = ()
    success_condition: tuple[str, ...] = ()
    failure_mode: tuple[str, ...] = ()
    source_path: Path | None = None

    # -- convenience ----------------------------------------------------------

    @property
    def effort_rank(self) -> int:
        """Numeric effort rank for comparison (high=3, medium=2, low=1)."""
        return EFFORT_ORDER.get(self.effort_class, 0)

    @property
    def needs_lease(self) -> bool:
        """Whether this module requires a Reasoning Lease allocation."""
        return self.requires_reasoning or self.effort_class == "high"


# ---------------------------------------------------------------------------
# Schema loading
# ---------------------------------------------------------------------------

_CACHED_SCHEMA: dict[str, Any] | None = None


def _load_schema() -> dict[str, Any]:
    global _CACHED_SCHEMA
    if _CACHED_SCHEMA is not None:
        return _CACHED_SCHEMA
    if not _SCHEMA_PATH.exists():
        raise FileNotFoundError(
            f"module_skill.v1 schema not found at {_SCHEMA_PATH}"
        )
    _CACHED_SCHEMA = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    return _CACHED_SCHEMA


# ---------------------------------------------------------------------------
# Frontmatter extraction
# ---------------------------------------------------------------------------

def extract_frontmatter(text: str) -> dict[str, Any]:
    """Extract YAML frontmatter from a .skill.md file's text content.

    Raises ``ValueError`` if no valid frontmatter fence is found.
    """
    match = _FRONTMATTER_RE.match(text)
    if not match:
        raise ValueError("no YAML frontmatter fence (---) found")
    raw_yaml = match.group(1)
    parsed = yaml.safe_load(raw_yaml)
    if not isinstance(parsed, dict):
        raise ValueError(
            f"frontmatter must be a YAML mapping, got {type(parsed).__name__}"
        )
    return parsed


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_frontmatter(
    data: Mapping[str, Any],
    *,
    raise_on_error: bool = True,
) -> list[str]:
    """Validate parsed frontmatter against module_skill.v1.schema.json.

    Returns a list of validation error messages (empty if valid).
    When *raise_on_error* is ``True`` (default), raises ``ValueError``
    on the first error instead.
    """
    schema = _load_schema()
    errors: list[str] = []

    if jsonschema is not None:
        validator = jsonschema.Draft202012Validator(schema)
        for error in sorted(validator.iter_errors(data), key=lambda e: list(e.path)):
            errors.append(f"{'.'.join(str(p) for p in error.path) or '(root)'}: {error.message}")
    else:
        # Minimal fallback when jsonschema is not installed
        for req in schema.get("required", []):
            if req not in data:
                errors.append(f"(root): required field '{req}' missing")

    if raise_on_error and errors:
        raise ValueError(
            f"skill frontmatter validation failed:\n"
            + "\n".join(f"  - {e}" for e in errors)
        )
    return errors


# ---------------------------------------------------------------------------
# Parsing pipeline
# ---------------------------------------------------------------------------

def parse_skill_file(path: Path) -> SkillMetadata:
    """Read a .skill.md file and return validated ``SkillMetadata``.

    Raises ``FileNotFoundError`` if *path* does not exist.
    Raises ``ValueError`` if frontmatter is missing or invalid.
    """
    if not path.exists():
        raise FileNotFoundError(f"skill file not found: {path}")
    text = path.read_text(encoding="utf-8")
    data = extract_frontmatter(text)
    validate_frontmatter(data)
    return _build_metadata(data, source_path=path)


def parse_skill_text(text: str, *, source_path: Path | None = None) -> SkillMetadata:
    """Parse raw .skill.md text and return validated ``SkillMetadata``."""
    data = extract_frontmatter(text)
    validate_frontmatter(data)
    return _build_metadata(data, source_path=source_path)


def _build_metadata(
    data: Mapping[str, Any],
    *,
    source_path: Path | None = None,
) -> SkillMetadata:
    return SkillMetadata(
        name=str(data["name"]),
        description=str(data["description"]),
        chain_position=str(data["chain_position"]),
        effort_class=str(data["effort_class"]),
        requires_reasoning=bool(data["requires_reasoning"]),
        bundle_eligible=bool(data["bundle_eligible"]),
        output_contract=str(data["output_contract"]),
        shared_context=tuple(str(s) for s in data.get("shared_context") or []),
        success_condition=tuple(str(s) for s in data.get("success_condition") or []),
        failure_mode=tuple(str(s) for s in data.get("failure_mode") or []),
        source_path=path_obj if (path_obj := source_path) else None,
    )


# ---------------------------------------------------------------------------
# Skill directory scanner (cache)
# ---------------------------------------------------------------------------

@dataclass
class SkillMetadataCache:
    """Scans a directory tree for .skill.md files and caches their metadata.

    Usage::

        cache = SkillMetadataCache.from_directory(runtime_root)
        high_effort = cache.by_effort("high")
        amundsen = cache.get("amundsen")
    """

    entries: dict[str, SkillMetadata] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)

    # -- construction ---------------------------------------------------------

    @classmethod
    def from_directory(cls, root: Path) -> SkillMetadataCache:
        """Recursively scan *root* for ``*.skill.md`` files."""
        cache = cls()
        if not root.is_dir():
            return cache
        for skill_path in sorted(root.rglob("*.skill.md")):
            try:
                meta = parse_skill_file(skill_path)
                cache.entries[meta.name] = meta
            except (ValueError, FileNotFoundError) as exc:
                cache.errors[str(skill_path)] = str(exc)
        return cache

    # -- query ----------------------------------------------------------------

    def get(self, name: str) -> SkillMetadata | None:
        """Look up a skill by module name."""
        return self.entries.get(name)

    def by_effort(self, effort_class: str) -> list[SkillMetadata]:
        """Return all skills matching the given effort_class."""
        return [m for m in self.entries.values() if m.effort_class == effort_class]

    def by_chain(self, chain_position: str) -> list[SkillMetadata]:
        """Return all skills at the given chain_position."""
        return [m for m in self.entries.values() if m.chain_position == chain_position]

    def requiring_lease(self) -> list[SkillMetadata]:
        """Return all skills that need a Reasoning Lease."""
        return [m for m in self.entries.values() if m.needs_lease]

    def bundleable(self) -> list[SkillMetadata]:
        """Return all skills eligible for same-session bundling."""
        return [m for m in self.entries.values() if m.bundle_eligible]

    @property
    def names(self) -> list[str]:
        """Sorted list of all cached module names."""
        return sorted(self.entries)
