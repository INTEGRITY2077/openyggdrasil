from __future__ import annotations

import argparse
import hashlib
import json
import sys
from typing import List

from answer_assurance import assure_answer_payload, render_assurance_fallback
from answer_quality_eval import evaluate_answer_quality
from answer_edge_renderer import render_answer_payload
from mailbox_store import inbox_packets
from pathfinder import build_pathfinder_bundle
from packet_scoring import score_packet
from plugin_logger import record_plugin_event
from reactive_decision_log import render_decision_log_payload
from subagent_telemetry import record_subagent_event


def select_packets(
    *,
    profile: str,
    session_id: str | None,
    parent_question_id: str | None,
    query_text: str,
    top_k: int,
    mailbox_namespace: str | None = None,
) -> List[dict]:
    inbox_kwargs = {"profile": profile}
    if mailbox_namespace is not None:
        inbox_kwargs["namespace"] = mailbox_namespace
    packets = inbox_packets(session_id=session_id, **inbox_kwargs)
    if parent_question_id:
        packets.extend(
            inbox_packets(
                parent_question_id=parent_question_id,
                **inbox_kwargs,
            )
        )

    dedup = {}
    for packet in packets:
        packet_scope = packet.get("scope", {})
        if not packet_scope.get("session_id") and not packet.get("parent_question_id"):
            continue
        dedup[packet["message_id"]] = packet
    ranked = sorted(
        dedup.values(),
        key=lambda message: score_packet(message, query_text),
        reverse=True,
    )
    return ranked[:top_k]

def render_decision_log(*, packets: List[dict], query_text: str, locale: str | None = None) -> dict:
    return render_decision_log_payload(
        packets=packets,
        query_text=query_text,
        requested_locale=locale,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Simulate Hermes mailbox preflight consumption.")
    parser.add_argument("--profile", required=True)
    parser.add_argument("--session-id", default=None)
    parser.add_argument("--query", required=True)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--parent-question-id", default=None)
    parser.add_argument("--render-brief", action="store_true")
    parser.add_argument("--render-answer", action="store_true")
    parser.add_argument("--locale", default=None)
    parser.add_argument("--mailbox-namespace", default=None)
    return parser.parse_args()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args()
    packets = select_packets(
        profile=args.profile,
        session_id=args.session_id,
        parent_question_id=args.parent_question_id,
        query_text=args.query,
        top_k=args.top_k,
        mailbox_namespace=args.mailbox_namespace,
    )
    packet_scores = {
        packet["message_id"]: score_packet(packet, args.query)
        for packet in packets
    }
    record_plugin_event(
        event_type="preflight_selection_made",
        actor="hermes",
        parent_question_id=args.parent_question_id,
        profile=args.profile,
        session_id=args.session_id,
        query_text=args.query,
        artifacts={
            "packet_ids": [packet["message_id"] for packet in packets],
            "packet_types": [packet.get("message_type") for packet in packets],
            "mailbox_namespace": args.mailbox_namespace,
        },
        state={
            "selected_packet_count": len(packets),
            "top_k": args.top_k,
            "packet_scores": packet_scores,
        },
    )
    for packet in packets:
        packet_parent_question_id = packet.get("parent_question_id")
        effective_parent_question_id = args.parent_question_id or packet_parent_question_id
        record_subagent_event(
            trace_id=packet["message_id"],
            capability="query",
            role="hermes",
            actor="hermes",
            decider="hermes",
            action="preflight_packet_consumed",
            status="success",
            producer="hermes-preflight",
            parent_question_id=effective_parent_question_id,
            artifacts={"packet_id": packet["message_id"], "message_id": packet["message_id"]},
            scope={
                "profile": packet.get("scope", {}).get("profile"),
                "session_id": packet.get("scope", {}).get("session_id"),
                "vault_path": packet.get("scope", {}).get("vault_path"),
                "graph_path": packet.get("scope", {}).get("graph_path"),
                "source_paths": packet.get("payload", {}).get("source_paths", []),
            },
            inference={"mode": "deterministic"},
            details={
                "query": args.query,
                "packet_parent_question_id": packet_parent_question_id,
            },
        )
    pathfinder_bundle = None
    if args.render_brief or args.render_answer:
        pathfinder_bundle = build_pathfinder_bundle(query_text=args.query)
        record_plugin_event(
            event_type="pathfinder_bundle_built",
            actor="pathfinder",
            parent_question_id=args.parent_question_id,
            profile=args.profile,
            session_id=args.session_id,
            query_text=args.query,
            artifacts={
                "anchor_id": pathfinder_bundle.get("anchor_id"),
                "topic_id": pathfinder_bundle.get("topic_id"),
                "page_ids": pathfinder_bundle.get("page_ids", []),
                "mailbox_namespace": args.mailbox_namespace,
            },
            state={
                "anchor_type": pathfinder_bundle.get("anchor_type"),
                "episode_count": len(pathfinder_bundle.get("episode_ids", [])),
                "support_fact_count": len(pathfinder_bundle.get("support_facts", [])),
                "bundle_mode": pathfinder_bundle.get("bundle_mode"),
            },
        )
        report = render_decision_log(packets=packets, query_text=args.query, locale=args.locale)
        record_plugin_event(
            event_type="decision_log_rendered",
            actor="hermes",
            parent_question_id=args.parent_question_id,
            profile=args.profile,
            session_id=args.session_id,
            query_text=args.query,
            artifacts={
                "packet_ids": [packet["message_id"] for packet in packets],
                "packet_types": [packet.get("message_type") for packet in packets],
                "rendering_mode": report.get("rendering_mode"),
                "requested_locale": report.get("requested_locale"),
                "mailbox_namespace": args.mailbox_namespace,
            },
            state={
                "brief_line_count": len(report.get("brief_lines", [])),
                "selected_packet_count": len(packets),
                "graph_hint_count": sum(1 for packet in packets if packet.get("message_type") == "graph_hint"),
                "lint_alert_count": sum(1 for packet in packets if packet.get("message_type") == "lint_alert"),
                "fallback_order": report.get("state", {}).get("fallback", {}).get("order", []),
                "primary_action": report.get("state", {}).get("decision", {}).get("primary_action"),
            },
        )
        payload = {"report": report, "packets": packets, "pathfinder_bundle": pathfinder_bundle}
        if args.render_answer:
            initial_answer = render_answer_payload(packets=packets, query_text=args.query)
            record_plugin_event(
                event_type="answer_rendered",
                actor="hermes",
                parent_question_id=args.parent_question_id,
                profile=args.profile,
                session_id=args.session_id,
                query_text=args.query,
                artifacts={
                    "packet_ids": [packet["message_id"] for packet in packets],
                    "packet_types": [packet.get("message_type") for packet in packets],
                    "answer_hash": initial_answer.get("answer_hash"),
                    "rendering_mode": initial_answer.get("rendering_mode"),
                    "mailbox_namespace": args.mailbox_namespace,
                },
                state={
                    "answer_length": len(initial_answer.get("answer_text", "")),
                    "selected_packet_count": len(packets),
                    "graph_hint_count": sum(1 for packet in packets if packet.get("message_type") == "graph_hint"),
                    "lint_alert_count": sum(1 for packet in packets if packet.get("message_type") == "lint_alert"),
                    "stage": "initial",
                },
            )
            initial_answer_quality = evaluate_answer_quality(
                query_text=args.query,
                packets=packets,
                answer_payload=initial_answer,
                decision_report=report,
            )
            record_plugin_event(
                event_type="answer_quality_evaluated",
                actor="hermes",
                parent_question_id=args.parent_question_id,
                profile=args.profile,
                session_id=args.session_id,
                query_text=args.query,
                artifacts={
                    "packet_ids": [packet["message_id"] for packet in packets],
                    "packet_types": [packet.get("message_type") for packet in packets],
                    "answer_hash": initial_answer.get("answer_hash"),
                    "quality_grade": initial_answer_quality.get("quality_grade"),
                    "mailbox_namespace": args.mailbox_namespace,
                },
                state={
                    **initial_answer_quality,
                    "evaluation_stage": "initial",
                },
            )
            assurance = assure_answer_payload(
                query_text=args.query,
                packets=packets,
                answer_payload=initial_answer,
                quality_verdict=initial_answer_quality,
            )
            final_answer = assurance["answer"]
            final_answer_quality = (
                initial_answer_quality
                if not assurance.get("applied")
                else evaluate_answer_quality(
                    query_text=args.query,
                    packets=packets,
                    answer_payload=final_answer,
                    decision_report=report,
                )
            )
            if assurance.get("applied") and not final_answer_quality.get("quality_gate_passed"):
                fallback_text = render_assurance_fallback(
                    query_text=args.query,
                    packets=packets,
                    quality_verdict=final_answer_quality,
                )
                final_answer = {
                    "rendering_mode": "deterministic-assurance-fallback",
                    "answer_text": fallback_text,
                    "answer_hash": "sha256:" + hashlib.sha256(fallback_text.encode("utf-8")).hexdigest(),
                    "state": final_answer.get("state", {}),
                }
                assurance = {
                    "applied": True,
                    "assurance_mode": "deterministic-grounded-fallback-after-repair",
                    "reasons": list(assurance.get("reasons", [])) + ["final_quality_gate_failed"],
                    "answer": final_answer,
                }
                final_answer_quality = evaluate_answer_quality(
                    query_text=args.query,
                    packets=packets,
                    answer_payload=final_answer,
                    decision_report=report,
                )
            record_plugin_event(
                event_type="answer_assurance_applied",
                actor="hermes",
                parent_question_id=args.parent_question_id,
                profile=args.profile,
                session_id=args.session_id,
                query_text=args.query,
                artifacts={
                    "packet_ids": [packet["message_id"] for packet in packets],
                    "packet_types": [packet.get("message_type") for packet in packets],
                    "initial_answer_hash": initial_answer.get("answer_hash"),
                    "final_answer_hash": final_answer.get("answer_hash"),
                    "assurance_mode": assurance.get("assurance_mode"),
                    "mailbox_namespace": args.mailbox_namespace,
                },
                state={
                    "applied": bool(assurance.get("applied")),
                    "reasons": list(assurance.get("reasons", [])),
                    "initial_quality_grade": initial_answer_quality.get("quality_grade"),
                    "final_quality_grade": final_answer_quality.get("quality_grade"),
                    "final_quality_gate_passed": final_answer_quality.get("quality_gate_passed"),
                },
            )
            record_plugin_event(
                event_type="answer_quality_evaluated",
                actor="hermes",
                parent_question_id=args.parent_question_id,
                profile=args.profile,
                session_id=args.session_id,
                query_text=args.query,
                artifacts={
                    "packet_ids": [packet["message_id"] for packet in packets],
                    "packet_types": [packet.get("message_type") for packet in packets],
                    "answer_hash": final_answer.get("answer_hash"),
                    "quality_grade": final_answer_quality.get("quality_grade"),
                    "mailbox_namespace": args.mailbox_namespace,
                },
                state={
                    **final_answer_quality,
                    "evaluation_stage": "final",
                },
            )
            payload["initial_answer"] = initial_answer
            payload["answer"] = final_answer
            payload["initial_answer_quality"] = initial_answer_quality
            payload["answer_quality"] = final_answer_quality
            payload["answer_assurance"] = {
                "applied": bool(assurance.get("applied")),
                "assurance_mode": assurance.get("assurance_mode"),
                "reasons": list(assurance.get("reasons", [])),
            }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(packets, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
