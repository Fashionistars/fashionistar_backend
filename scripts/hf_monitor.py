#!/usr/bin/env python3
"""Monitor the FASHIONISTAR Hugging Face 4-Space deployment.

Polls the GitHub Actions API and HF Spaces API to verify the post-PR #25 state:
  - deploy-hf-all.yml completed successfully
  - api-v1, celery-beat, celery-queues, and ai-engine are all RUNNING
  - AI Engine logs show MediaPipe/SigLIP/LLM ready

Environment:
    HF_TOKEN    - Hugging Face token with read access to Spaces
    GITHUB_PAT  - GitHub PAT with repo access to read Actions runs

Usage:
    python scripts/hf_monitor.py
    python scripts/hf_monitor.py --poll --timeout 600 --poll-interval 15
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from typing import Any

import requests

# Space identifiers, in dependency order
SPACE_NAMES = [
    "fashionistar-api-v1",
    "fashionistar-celery-beat",
    "fashionistar-celery-queues",
    "fashionistar-ai-engine",
]

# Log patterns that indicate the AI engine is healthy or broken
HEALTHY_PATTERNS = [
    re.compile(r"MediaPipe:\s*✅"),
    re.compile(r"SigLIP:\s*✅"),
    re.compile(r"LLM:\s*✅"),
    re.compile(r"Startup complete", re.IGNORECASE),
]
ERROR_PATTERNS = [
    re.compile(r"BUILD_ERROR"),
    re.compile(r"RUNTIME_ERROR"),
    re.compile(r"OOM"),
    re.compile(r"Traceback \(most recent call last\)"),
    re.compile(r"(?:Error|ERROR):\s+"),
]


def _http_headers(token: str | None) -> dict[str, str]:
    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def get_latest_workflow_runs(
    owner: str, repo: str, workflow: str, pat: str | None
) -> list[dict[str, Any]]:
    """Return the latest workflow runs for a given workflow file."""
    url = (
        f"https://api.github.com/repos/{owner}/{repo}/actions/workflows/{workflow}/runs"
    )
    params = {"branch": "main", "per_page": "5"}
    headers = _http_headers(pat)
    headers["Accept"] = "application/vnd.github+json"
    headers["X-GitHub-Api-Version"] = "2022-11-28"

    response = requests.get(url, params=params, headers=headers, timeout=30)
    response.raise_for_status()
    return response.json().get("workflow_runs", [])


def get_space_status(hf_owner: str, space: str, token: str | None) -> dict[str, Any]:
    """Return the HF Space runtime status JSON."""
    url = f"https://huggingface.co/api/spaces/{hf_owner}/{space}"
    response = requests.get(url, headers=_http_headers(token), timeout=30)
    response.raise_for_status()
    return response.json()


def _extract_text_from_sse_payload(payload: str) -> str:
    """Try to extract a human-readable string from an SSE data payload."""
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return payload

    if isinstance(data, str):
        return data
    if isinstance(data, dict):
        for key in ("log", "message", "data", "text"):
            if key in data and isinstance(data[key], str):
                return data[key]
    return payload


def stream_space_logs(
    hf_owner: str, space: str, token: str | None, max_lines: int = 500
) -> list[str]:
    """Return the last N log lines from a HF Space run stream."""
    url = f"https://huggingface.co/api/spaces/{hf_owner}/{space}/logs/run"
    lines: list[str] = []
    try:
        with requests.get(
            url, headers=_http_headers(token), stream=True, timeout=(10, 60)
        ) as response:
            response.raise_for_status()
            for raw_line in response.iter_lines():
                if not raw_line:
                    continue
                line = raw_line.decode("utf-8", errors="replace")
                if line.startswith("data:"):
                    payload = _extract_text_from_sse_payload(line[5:].strip())
                    lines.append(payload)
                else:
                    lines.append(line)
                if len(lines) >= max_lines:
                    break
    except requests.exceptions.ReadTimeout:
        # Streaming logs often time out; use what we have collected
        pass
    return lines


def evaluate_ai_engine_logs(log_lines: list[str]) -> tuple[bool, list[str]]:
    """Return (healthy, errors) based on AI Engine log patterns."""
    healthy = any(p.search(line) for p in HEALTHY_PATTERNS for line in log_lines)
    errors = [
        line
        for p in ERROR_PATTERNS
        for line in log_lines
        if p.search(line)
    ]
    return healthy, errors


def check_spaces(
    hf_owner: str,
    spaces: list[str],
    token: str | None,
    poll: bool,
    timeout: int,
    poll_interval: int,
) -> bool:
    """Check all HF Spaces and optionally poll until RUNNING."""
    deadline = time.time() + timeout if poll else 0
    all_ready = False
    final_statuses: dict[str, str] = {}

    while True:
        all_ready = True
        final_statuses = {}
        for space in spaces:
            try:
                data = get_space_status(hf_owner, space, token)
                stage = data.get("runtime", {}).get("stage", "UNKNOWN")
                sha = data.get("sha", "n/a")[:7]
            except requests.HTTPError as exc:
                stage = f"HTTPError({exc.response.status_code})"
                all_ready = False
            except requests.RequestException as exc:
                stage = f"Error({exc})"
                all_ready = False

            final_statuses[space] = stage
            print(f"  {space}: stage={stage} sha={sha}")

            if stage != "RUNNING":
                all_ready = False

        if all_ready or not poll:
            break

        if time.time() > deadline:
            print(f"[!] Polling timeout reached ({timeout}s).")
            break

        print(f"  -> Waiting {poll_interval}s before next poll...\n")
        time.sleep(poll_interval)

    # AI Engine specific log analysis
    ai_engine = "fashionistar-ai-engine"
    if ai_engine in final_statuses and final_statuses[ai_engine] == "RUNNING":
        print(f"\nFetching logs for {ai_engine}...")
        logs = stream_space_logs(hf_owner, ai_engine, token)
        healthy, errors = evaluate_ai_engine_logs(logs)
        if healthy:
            print("  AI Engine logs indicate healthy startup (MediaPipe/SigLIP/LLM).")
        if errors:
            print("  AI Engine log errors detected:")
            for error in errors[:10]:
                print(f"    - {error}")
            all_ready = False

    if all_ready:
        print("\nAll HF Spaces are RUNNING and healthy.")
    else:
        print("\nNot all HF Spaces are RUNNING or log errors were detected.")

    return all_ready


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Monitor FASHIONISTAR HF 4-Space deployment."
    )
    parser.add_argument("--github-owner", default="Fashionistars")
    parser.add_argument("--github-repo", default="fashionistar_backend")
    parser.add_argument("--hf-owner", default="fashionistar")
    parser.add_argument(
        "--spaces",
        nargs="+",
        default=SPACE_NAMES,
        help="HF Space names to monitor",
    )
    parser.add_argument("--workflow", default="deploy-hf-all.yml")
    parser.add_argument("--github-pat", default=os.environ.get("GITHUB_PAT"))
    parser.add_argument("--hf-token", default=os.environ.get("HF_TOKEN"))
    parser.add_argument(
        "--poll", action="store_true", help="Poll spaces until RUNNING"
    )
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--poll-interval", type=int, default=15)
    parser.add_argument("--max-log-lines", type=int, default=500)
    args = parser.parse_args()

    if not args.hf_token or args.hf_token.startswith("hf_PLACEHOLDER"):
        print("[WARN] HF_TOKEN is not set or is a placeholder.", file=sys.stderr)
    if not args.github_pat or args.github_pat.startswith("github_pat_PLACEHOLDER"):
        print("[WARN] GITHUB_PAT is not set or is a placeholder.", file=sys.stderr)

    print("=" * 60)
    print("FASHIONISTAR HF 4-Space Deployment Monitor")
    print("=" * 60)

    # 1. GitHub Actions workflow status
    print(f"\nLatest '{args.workflow}' runs on main:")
    try:
        runs = get_latest_workflow_runs(
            args.github_owner, args.github_repo, args.workflow, args.github_pat
        )
        if not runs:
            print("  No workflow runs found.")
        for run in runs[:3]:
            print(
                f"  run #{run['run_number']}: {run['status']} / {run.get('conclusion', 'N/A')}"
                f" (sha={run['head_sha'][:7]})"
            )
    except requests.HTTPError as exc:
        print(f"  Could not fetch workflow runs: HTTP {exc.response.status_code}")
    except requests.RequestException as exc:
        print(f"  Could not fetch workflow runs: {exc}")

    # 2. HF Space status
    print("\nHF Space status:")
    healthy = check_spaces(
        args.hf_owner,
        args.spaces,
        args.hf_token,
        args.poll,
        args.timeout,
        args.poll_interval,
    )

    return 0 if healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())
