"""PTC engine primitives extracted behind compatibility-preserving imports."""

from __future__ import annotations


def render_default_pathfinder_program(*, recent_limit: int) -> str:
    return (
        "region = tools['find_region'](query_text=query_text)\n"
        "anchor = tools['find_topic_anchor'](query_text=query_text, region_id=region['region_id'])\n"
        "if anchor['topic_id'] is None:\n"
        "    RESULT = tools['build_unanchored_bundle'](query_text=query_text)\n"
        "else:\n"
        "    origin_rows = tools['get_origin_claims'](topic_id=anchor['topic_id'], limit=1)\n"
        f"    recent_rows = tools['get_recent_episodes'](topic_id=anchor['topic_id'], limit={max(1, recent_limit)})\n"
        "    claim_ids = [row['claim_id'] for row in recent_rows + origin_rows if row.get('claim_id')]\n"
        "    source_paths = tools['get_raw_sources'](topic_id=anchor['topic_id'], claim_ids=claim_ids)\n"
        "    RESULT = tools['build_support_bundle'](\n"
        "        query_text=query_text,\n"
        "        anchor=anchor,\n"
        "        origin_rows=origin_rows,\n"
        "        recent_rows=recent_rows,\n"
        "        source_paths=source_paths,\n"
        "    )\n"
    )


__all__ = ["render_default_pathfinder_program"]
