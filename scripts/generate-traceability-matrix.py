#!/usr/bin/env python3
"""Generate requirements traceability matrix from GitHub issues/PR references."""

from __future__ import annotations

import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass


@dataclass
class RequirementRow:
    req_id: str
    title: str
    state: str
    linked_prs: str


def _api_get(url: str, token: str) -> dict | list:
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "traceability-matrix-generator",
        },
    )
    with urllib.request.urlopen(req) as resp:
        return __import__("json").loads(resp.read().decode("utf-8"))


def _extract_refs(text: str) -> list[int]:
    if not text:
        return []
    return [int(n) for n in re.findall(r"#(\d+)", text)]


def main() -> int:
    token = os.getenv("GITHUB_TOKEN")
    repo = os.getenv("GITHUB_REPOSITORY")

    if not token or not repo:
        print("ERROR: GITHUB_TOKEN and GITHUB_REPOSITORY are required", file=sys.stderr)
        return 1

    owner, name = repo.split("/", 1)

    try:
        issues = _api_get(
            f"https://api.github.com/repos/{owner}/{name}/issues?state=all&labels=requirement&per_page=100",
            token,
        )
        prs = _api_get(
            f"https://api.github.com/repos/{owner}/{name}/pulls?state=all&per_page=100",
            token,
        )
    except urllib.error.HTTPError as exc:
        print(f"ERROR: GitHub API request failed ({exc.code})", file=sys.stderr)
        return 1

    req_to_prs: dict[int, list[int]] = {}
    for pr in prs:
        body = pr.get("body") or ""
        refs = _extract_refs(body)
        for ref in refs:
            req_to_prs.setdefault(ref, []).append(pr["number"])

    rows: list[RequirementRow] = []
    for issue in issues:
        if "pull_request" in issue:
            continue
        number = issue["number"]
        title = issue.get("title", "")
        req_id_match = re.search(r"\[(REQ-[^\]]+)\]", title)
        req_id = req_id_match.group(1) if req_id_match else f"#{number}"
        prs_for_req = req_to_prs.get(number, [])
        linked = ", ".join(f"#{n}" for n in sorted(set(prs_for_req))) if prs_for_req else "None"
        rows.append(
            RequirementRow(
                req_id=req_id,
                title=title,
                state=issue.get("state", "unknown"),
                linked_prs=linked,
            )
        )

    rows.sort(key=lambda r: r.req_id)

    print("# Requirements Traceability Matrix\n")
    print("| Req ID | Title | State | Implemented By |")
    print("|---|---|---|---|")
    for row in rows:
        safe_title = row.title.replace("|", "\\|")
        print(f"| {row.req_id} | {safe_title} | {row.state} | {row.linked_prs} |")

    print(f"\nTotal requirements: {len(rows)}")
    with_pr = sum(1 for r in rows if r.linked_prs != "None")
    print(f"Requirements with PR links: {with_pr}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())