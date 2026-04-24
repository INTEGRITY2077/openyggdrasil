from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from packet_factory import build_graph_hint_packet
from reactive_decision_log import render_decision_log_payload


HANGUL_RE = re.compile(r"[\u3131-\u318E\uAC00-\uD7A3]")
ARABIC_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]")
CYRILLIC_RE = re.compile(r"[\u0400-\u04FF]")
THAI_RE = re.compile(r"[\u0E00-\u0E7F]")


def sample_packets(language_tag: str) -> list[dict]:
    graph_packet = build_graph_hint_packet(
        profile="wiki",
        session_id=f"reactive-{language_tag}",
        topic="reverse push mailbox",
        source_paths=[r"%HERMES_ROOT%\vault\queries\observer-daemon-role.md"],
        facts=["graph fact"],
        human_summary="graph packet",
    )
    lint_packet = build_graph_hint_packet(
        profile="wiki",
        session_id=f"reactive-{language_tag}",
        topic="reverse push mailbox",
        source_paths=[r"%HERMES_ROOT%\vault\concepts\llm-wiki-pattern.md"],
        facts=["lint fact"],
        human_summary="lint packet",
    )
    lint_packet["message_type"] = "lint_alert"
    return [graph_packet, lint_packet]


def cases() -> dict[str, str]:
    return {
        "ko-KR": "이 메일박스 역푸시 흐름이 어떻게 동작하는지 설명해줘.",
        "en-US": "Explain how this mailbox reverse push flow works.",
        "ar-SA": "اشرح كيف تعمل آلية الدفع العكسي لصندوق البريد.",
        "ru-RU": "Объясни, как работает этот поток обратного push для mailbox.",
        "th-TH": "อธิบายว่ากลไก reverse push ของ mailbox นี้ทำงานอย่างไร",
        "id-ID": "Jelaskan bagaimana alur reverse push mailbox ini bekerja.",
        "hu-HU": "Magyarázd el, hogyan működik ez a mailbox reverse push folyamat.",
    }


def verify_language(locale_tag: str, lines: list[str]) -> dict[str, object]:
    joined = " ".join(lines)
    if locale_tag == "ko-KR":
        ok = bool(HANGUL_RE.search(joined))
        return {"ok": ok, "reason": "contains_hangul"}
    if locale_tag == "ar-SA":
        ok = bool(ARABIC_RE.search(joined))
        return {"ok": ok, "reason": "contains_arabic"}
    if locale_tag == "ru-RU":
        ok = bool(CYRILLIC_RE.search(joined))
        return {"ok": ok, "reason": "contains_cyrillic"}
    if locale_tag == "th-TH":
        ok = bool(THAI_RE.search(joined))
        return {"ok": ok, "reason": "contains_thai"}
    if locale_tag == "id-ID":
        ok = any(token in joined.lower() for token in ["anda", "bagaimana", "alur", "akan"])
        return {"ok": ok, "reason": "contains_indonesian_markers"}
    if locale_tag == "hu-HU":
        lowered = joined.lower()
        ok = any(token in lowered for token in ["hogyan", "először", "kérdeztél", "működ", "mukod"])
        return {"ok": ok, "reason": "contains_hungarian_markers"}
    if locale_tag == "en-US":
        ok = any(token in joined.lower() for token in ["you asked", "hermes will", "if that"])
        return {"ok": ok, "reason": "contains_english_markers"}
    return {"ok": False, "reason": "unknown_locale"}


def verify_schema_first(report: dict) -> dict[str, bool]:
    state = report["state"]
    return {
        "has_question_context": isinstance(state.get("question_context"), str),
        "has_received_signals": isinstance(state.get("received_signals"), dict),
        "has_decision": isinstance(state.get("decision"), dict),
        "has_fallback": isinstance(state.get("fallback"), dict),
        "has_grounding": isinstance(state.get("grounding"), dict),
        "question_context_is_string": isinstance(state.get("question_context"), str),
        "signals_have_counts": isinstance(state["received_signals"].get("graph_hints"), int)
        and isinstance(state["received_signals"].get("lint_alerts"), int),
        "decision_is_machine_typed": isinstance(state["decision"].get("primary_action"), str)
        and isinstance(state["decision"].get("cautions"), list),
        "fallback_is_machine_typed": isinstance(state["fallback"].get("order"), list),
        "brief_lines_count_is_four": isinstance(report.get("brief_lines"), list) and len(report["brief_lines"]) == 4,
        "rendering_is_hermes_reactive": report.get("rendering_mode") == "hermes-reactive",
    }


def run_case(locale_tag: str, query: str) -> dict:
    report = render_decision_log_payload(
        packets=sample_packets(locale_tag),
        query_text=query,
        requested_locale=None,
    )
    schema_checks = verify_schema_first(report)
    language_check = verify_language(locale_tag, report["brief_lines"])
    ok = all(schema_checks.values()) and bool(language_check["ok"])
    return {
        "status": "ok" if ok else "failed",
        "report": report,
        "schema_checks": schema_checks,
        "language_check": language_check,
    }


def run_all() -> dict[str, object]:
    results: dict[str, dict] = {}
    for locale_tag, query in cases().items():
        results[locale_tag] = run_case(locale_tag, query)

    overall_ok = all(result["status"] == "ok" for result in results.values())
    return {
        "status": "ok" if overall_ok else "failed",
        "cases": results,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Proof run for schema-first reactive decision-log rendering.")
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
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
