from __future__ import annotations

import re
import uuid
from pathlib import PurePosixPath


CLAIM_NAMESPACE = uuid.UUID("0f0f1f0d-9f4f-46b9-b7f7-3a7a6f6d9a10")


def normalize_key(value: str) -> str:
    text = value.strip().lower()
    text = text.replace("\\", "/")
    text = re.sub(r"\.md$", "", text)
    text = re.sub(r"[^a-z0-9/_-]+", "-", text)
    text = re.sub(r"-{2,}", "-", text)
    text = re.sub(r"/{2,}", "/", text)
    text = text.strip("-/")
    return text or "untitled"


def build_topic_id(topic_key: str) -> str:
    return f"topic:{normalize_key(topic_key)}"


def build_episode_id(*, topic_id: str, episode_key: str) -> str:
    if not topic_id.startswith("topic:"):
        raise ValueError("topic_id must start with 'topic:'")
    topic_key = topic_id.split(":", 1)[1]
    return f"episode:{topic_key}:{normalize_key(episode_key)}"


def build_page_id(relative_path: str) -> str:
    canonical = normalize_key(relative_path)
    canonical = PurePosixPath(canonical).as_posix()
    return f"page:{canonical}"


def build_claim_id(*, topic_id: str, claim_key: str) -> str:
    if not topic_id.startswith("topic:"):
        raise ValueError("topic_id must start with 'topic:'")
    claim_name = f"{topic_id}|{normalize_key(claim_key)}"
    return f"claim:{uuid.uuid5(CLAIM_NAMESPACE, claim_name).hex}"
