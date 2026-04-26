from __future__ import annotations

import argparse
import base64
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

from harness_common import CENTRAL_ROOT, DEFAULT_HERMES_BIN, HERMES_HOME_WIN, OPENYGGDRASIL_ROOT


CENTRAL_POLICY = CENTRAL_ROOT / "policy" / "system-rule" / "HERMES_SUBAGENT_GOVERNANCE.md"
CENTRAL_SKILL = (
    CENTRAL_ROOT / "skills" / "software-development" / "subagent-governance" / "SKILL.md"
)
MAILBOX_SCHEMA = CENTRAL_ROOT / "projects" / "harness" / "mailbox.v1.schema.json"
GRAPHIFY_SEMANTIC = OPENYGGDRASIL_ROOT / "common" / "graphify" / "extract_graphify_semantic.py"
RUNTIME_SKILL = (
    HERMES_HOME_WIN / "skills" / "software-development" / "subagent-governance" / "SKILL.md"
)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    return sha256_text(path.read_text(encoding="utf-8"))


def ensure_runtime_skill(central_skill: Path, runtime_skill: Path) -> dict:
    runtime_skill.parent.mkdir(parents=True, exist_ok=True)

    central_text = central_skill.read_text(encoding="utf-8")
    central_hash = sha256_text(central_text)
    before_exists = runtime_skill.exists()
    before_hash = file_sha256(runtime_skill) if before_exists else None

    if not before_exists or before_hash != central_hash:
        runtime_skill.write_text(central_text, encoding="utf-8")

    after_hash = file_sha256(runtime_skill)
    return {
        "runtime_skill_path": str(runtime_skill),
        "before_exists": before_exists,
        "before_hash": before_hash,
        "after_hash": after_hash,
        "central_hash": central_hash,
        "synced": before_hash != central_hash,
    }


def build_probe_prompt() -> str:
    return (
        "Use the subagent-governance skill. "
        "Scenario: a completed background graph search produced a mailbox packet. "
        "No direct SOT write is needed. "
        "Return exactly six markdown bullets with these exact labels only: "
        "capability classification, selected role path, authority boundary, "
        "inference dependency, expected output schema, Hermes integration point."
    )


def run_hermes_probe(*, prompt: str, hermes_bin: str = DEFAULT_HERMES_BIN) -> dict:
    encoded = base64.b64encode(prompt.encode("utf-8")).decode("ascii")
    python_code = f"""
import base64, subprocess, sys
prompt = base64.b64decode('{encoded}').decode('utf-8')
cp = subprocess.run(
    ['{hermes_bin}','chat','-q',prompt,'-Q','--max-turns','1'],
    text=True,
    capture_output=True,
)
sys.stdout.write(cp.stdout)
sys.stderr.write(cp.stderr)
raise SystemExit(cp.returncode)
""".strip()

    completed = subprocess.run(
        ["wsl", "-d", "ubuntu-agent", "--", "python3", "-c", python_code],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    required_labels = [
        "capability classification",
        "selected role path",
        "authority boundary",
        "inference dependency",
        "expected output schema",
        "Hermes integration point",
    ]
    found = {label: (label.lower() in stdout.lower()) for label in required_labels}
    return {
        "returncode": completed.returncode,
        "required_labels": found,
        "all_labels_present": all(found.values()),
        "stdout_preview": stdout[:2000],
        "stderr_preview": stderr[:1000],
    }


def verify_policy_alignment(policy_path: Path) -> dict:
    text = policy_path.read_text(encoding="utf-8")
    required_phrases = {
        "capability_first_ingest": "`ingest`",
        "capability_first_query": "`query`",
        "capability_first_lint": "`lint`",
        "skills_are_access_surface": "skills are the access and policy surface",
        "hermes_remains_center": "Hermes remains the center",
        "mailbox_not_sot": "not a SOT",
    }
    return {
        "policy_path": str(policy_path),
        "checks": {name: (phrase in text) for name, phrase in required_phrases.items()},
    }


def verify_graphify_inference_dependency(graphify_path: Path) -> dict:
    text = graphify_path.read_text(encoding="utf-8")
    checks = {
        "uses_hermes_chat": (
            "'chat','-q'" in text
            or "'chat', '-q'" in text
            or '"chat","-q"' in text
            or '"chat", "-q"' in text
        ),
        "uses_runtime_hermes_bin": "DEFAULT_HERMES_BIN" in text,
        "semantic_extraction_function": "run_hermes_extract(" in text,
    }
    return {
        "graphify_semantic_path": str(graphify_path),
        "checks": checks,
    }


def verify_mailbox_schema(schema_path: Path) -> dict:
    payload = json.loads(schema_path.read_text(encoding="utf-8"))
    packet_enum = (
        payload.get("properties", {})
        .get("kind", {})
        .get("enum", [])
    )
    status_enum = (
        payload.get("properties", {})
        .get("status", {})
        .get("enum", [])
    )
    required_scope_keys = sorted(
        payload.get("$defs", {})
        .get("scope", {})
        .get("properties", {})
        .keys()
    )
    return {
        "schema_path": str(schema_path),
        "kind_enum": packet_enum,
        "status_enum": status_enum,
        "scope_keys": required_scope_keys,
        "has_packet_kind": "packet" in packet_enum,
        "has_command_kind": "command" in packet_enum,
        "has_scope": bool(required_scope_keys),
    }


def run_all() -> dict:
    if shutil.which("wsl") is None:
        raise RuntimeError("wsl command is not available")

    skill_sync = ensure_runtime_skill(CENTRAL_SKILL, RUNTIME_SKILL)
    hermes_probe = run_hermes_probe(prompt=build_probe_prompt())
    policy_alignment = verify_policy_alignment(CENTRAL_POLICY)
    graphify_dependency = verify_graphify_inference_dependency(GRAPHIFY_SEMANTIC)
    mailbox_schema = verify_mailbox_schema(MAILBOX_SCHEMA)

    overall_pass = (
        hermes_probe["returncode"] == 0
        and hermes_probe["all_labels_present"]
        and all(policy_alignment["checks"].values())
        and all(graphify_dependency["checks"].values())
        and mailbox_schema["has_packet_kind"]
        and mailbox_schema["has_command_kind"]
        and mailbox_schema["has_scope"]
    )

    return {
        "status": "ok" if overall_pass else "failed",
        "skill_sync": skill_sync,
        "hermes_probe": hermes_probe,
        "policy_alignment": policy_alignment,
        "graphify_dependency": graphify_dependency,
        "mailbox_schema": mailbox_schema,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify subagent governance POC wiring.")
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_all()
    text = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    sys.stdout.buffer.write(text.encode("utf-8", errors="replace"))
    sys.stdout.buffer.write(b"\n")
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

