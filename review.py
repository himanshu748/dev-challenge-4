from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.request
import urllib.error
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run PRReviewIQ against a repo or file.")
    parser.add_argument("--server-url", default="http://127.0.0.1:8000", help="FastAPI base URL")
    parser.add_argument("--repo", help="Path to a git repository")
    parser.add_argument("--file", help="Path to a file to review")
    parser.add_argument("--base-ref", default="main", help="Base ref for git diff")
    parser.add_argument("--pr-title", help="PR title to send to the API")
    parser.add_argument("--repo-name", help="Repository name override")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if bool(args.repo) == bool(args.file):
        print("Use exactly one of --repo or --file.", file=sys.stderr)
        return 1

    try:
        if args.repo:
            payload = build_repo_payload(args.repo, args.base_ref, args.pr_title, args.repo_name)
            endpoint = "/api/review-pr"
        else:
            payload = build_file_payload(args.file, args.pr_title, args.repo_name)
            endpoint = "/api/review-file"

        url = f"{args.server_url.rstrip('/')}{endpoint}"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (subprocess.CalledProcessError, FileNotFoundError, urllib.error.URLError) as exc:
        print(f"PRReviewIQ failed: {exc}", file=sys.stderr)
        return 1
    issues = data.get("issues", [])
    print(f"PRReviewIQ found {len(issues)} issue(s).")
    for issue in issues:
        print(
            f"- [{issue['severity']}/{issue['category']}] {issue['file']}: {issue['message']}"
        )
    print(f"Notion: {data.get('notion_url')}")
    print(f"Standards updated: {data.get('standards_updated', 0)}")
    return 0


def build_repo_payload(
    repo_path: str,
    base_ref: str,
    pr_title: str | None,
    repo_name: str | None,
) -> dict[str, str]:
    repo = Path(repo_path).expanduser().resolve()
    diff = run_git(repo, ["diff", f"{base_ref}...HEAD"])
    branch = run_git(repo, ["rev-parse", "--abbrev-ref", "HEAD"]).strip()
    return {
        "diff": diff,
        "pr_title": pr_title or f"Review {branch} against {base_ref}",
        "repo": repo_name or repo.name,
    }


def build_file_payload(
    file_path: str,
    pr_title: str | None,
    repo_name: str | None,
) -> dict[str, str]:
    path = Path(file_path).expanduser().resolve()
    content = path.read_text(encoding="utf-8")
    return {
        "filename": str(path.name),
        "content": content,
        "pr_title": pr_title or f"Single-file review for {path.name}",
        "repo": repo_name or path.parent.name,
    }


def run_git(repo: Path, args: list[str]) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout


if __name__ == "__main__":
    raise SystemExit(main())
