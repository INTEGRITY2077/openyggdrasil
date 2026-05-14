#!/usr/bin/env python3
from __future__ import annotations

from hermes_ygg_hook_common import run_latest_provider_admission_hook


def main() -> int:
    run_latest_provider_admission_hook(event_name="post_llm_call")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
