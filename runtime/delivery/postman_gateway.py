from __future__ import annotations

from typing import Any, Dict

from delivery.mailbox_contamination_guard import ensure_mailbox_message_accepted
from delivery.mailbox_status import write_mailbox_status
from delivery.mailbox_store import append_message


def submit_message(
    message: Dict[str, Any],
    *,
    namespace: str | None = None,
    refresh_status: bool = True,
) -> Dict[str, Any]:
    ensure_mailbox_message_accepted(message)
    append_message(message, namespace=namespace)
    if refresh_status:
        write_mailbox_status(namespace=namespace)
    return message


def submit_packet(
    packet: Dict[str, Any],
    *,
    namespace: str | None = None,
    refresh_status: bool = True,
) -> Dict[str, Any]:
    if packet.get("kind") != "packet":
        raise RuntimeError("submit_packet requires kind='packet'")
    return submit_message(packet, namespace=namespace, refresh_status=refresh_status)


def submit_command(
    command: Dict[str, Any],
    *,
    namespace: str | None = None,
    refresh_status: bool = True,
) -> Dict[str, Any]:
    if command.get("kind") != "command":
        raise RuntimeError("submit_command requires kind='command'")
    return submit_message(command, namespace=namespace, refresh_status=refresh_status)
