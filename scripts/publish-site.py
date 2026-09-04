#!/usr/bin/env python3
"""Guard, commit, push, and verify a themorningcommit release."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

EXPECTED_OWNER = "JohnnyWheelz"
EXPECTED_REMOTE = "https://github.com/JohnnyWheelz/themorningcommit.git"
EXPECTED_REPOSITORY = "JohnnyWheelz/themorningcommit"
LIVE_SMOKE_WORKFLOW = "live-smoke.yml"
PAGES_PROJECT = "themorningcommit"


def run(
    command: list[str],
    cwd: Path,
    env: dict[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command, cwd=cwd, env=env, text=True, capture_output=True
    )
    if check and result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"command failed: {command[0]}: {detail}")
    return result


def github_live_smoke(
    root: Path, env: dict[str, str], commit_hash: str, timeout: int
) -> str:
    """Verify the custom domains from an independent GitHub-hosted runner."""
    list_command = [
        "gh",
        "run",
        "list",
        "--repo",
        EXPECTED_REPOSITORY,
        "--workflow",
        LIVE_SMOKE_WORKFLOW,
        "--event",
        "workflow_dispatch",
        "--limit",
        "20",
        "--json",
        "databaseId,headSha,status,conclusion,url",
    ]
    previous = {
        item["databaseId"]
        for item in json.loads(run(list_command, root, env).stdout or "[]")
    }
    run(
        [
            "gh",
            "workflow",
            "run",
            LIVE_SMOKE_WORKFLOW,
            "--repo",
            EXPECTED_REPOSITORY,
            "--ref",
            "main",
        ],
        root,
        env,
    )
    deadline = time.time() + timeout
    run_id: int | None = None
    run_url = ""
    while time.time() < deadline and run_id is None:
        items = json.loads(run(list_command, root, env).stdout or "[]")
        for item in items:
            if item["databaseId"] not in previous and item["headSha"] == commit_hash:
                run_id = item["databaseId"]
                run_url = item["url"]
                break
        if run_id is None:
            time.sleep(2)
    if run_id is None:
        raise RuntimeError("external live-smoke run did not appear")
    while time.time() < deadline:
        view = json.loads(
            run(
                [
                    "gh",
                    "run",
                    "view",
                    str(run_id),
                    "--repo",
                    EXPECTED_REPOSITORY,
                    "--json",
                    "status,conclusion,headSha,url",
                ],
                root,
                env,
            ).stdout
        )
        if view["headSha"] != commit_hash:
            raise RuntimeError("external live-smoke checked the wrong Git commit")
        if view["status"] == "completed":
            if view["conclusion"] != "success":
                raise RuntimeError(f"external live-smoke failed: {view['url']}")
            return view["url"]
        time.sleep(3)
    raise RuntimeError(f"external live-smoke timed out: {run_url}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True)
    parser.add_argument("--live-url", default="https://themorningcommit.com/")
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    report = Path(args.report).resolve()
    run(
        [sys.executable, str(root / "scripts/build-site.py"), "--report", str(report)],
        root,
    )
    run(["node", str(root / "scripts/validate-public.mjs")], root)

    token = run(
        [
            "gh",
            "auth",
            "token",
            "--hostname",
            "github.com",
            "--user",
            EXPECTED_OWNER,
        ],
        root,
    ).stdout.strip()
    if not token:
        raise RuntimeError("JohnnyWheelz keyring token unavailable")
    env = os.environ.copy()
    env["GH_TOKEN"] = token
    who = run(["gh", "api", "user", "--jq", ".login"], root, env).stdout.strip()
    if who.casefold() != EXPECTED_OWNER.casefold():
        raise RuntimeError(f"wrong GitHub identity: {who}")
    remote = run(["git", "remote", "get-url", "origin"], root).stdout.strip()
    if remote != EXPECTED_REMOTE:
        raise RuntimeError(f"wrong Git remote: {remote}")
    branch = run(["git", "branch", "--show-current"], root).stdout.strip()
    if branch != "main":
        raise RuntimeError(f"wrong branch: {branch}")

    run(["git", "add", "public"], root)
    staged = run(["git", "diff", "--cached", "--quiet"], root, check=False).returncode != 0
    if staged:
        raw = (root / "public/index.html").read_text(encoding="utf-8")
        match = re.search(r"<strong>Date</strong><br>\s*([^<]+)", raw, re.I)
        human = match.group(1).strip() if match else "daily"
        run(["git", "commit", "-m", f"publish: {human} edition"], root)
        run(
            [
                "git",
                "-c",
                "credential.helper=",
                "-c",
                "credential.helper=!gh auth git-credential",
                "push",
                "origin",
                "main",
            ],
            root,
            env,
        )

    expected = (root / "public/index.html").read_bytes()
    expected_hash = hashlib.sha256(expected).hexdigest()
    commit_hash = run(["git", "rev-parse", "HEAD"], root).stdout.strip()
    commit_message = run(["git", "log", "-1", "--pretty=%s"], root).stdout.strip()
    state_path = root / ".release-state.json"

    def live_hash() -> str:
        request = urllib.request.Request(
            args.live_url,
            headers={
                "User-Agent": "themorningcommit-release-verifier/1.0",
                "Cache-Control": "no-cache",
            },
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            return hashlib.sha256(response.read()).hexdigest()

    state_matches = False
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state_matches = (
            state.get("commit") == commit_hash
            and state.get("homepage_sha256") == expected_hash
        )
        if state_matches and live_hash() == expected_hash:
            print(f"ALREADY_PUBLISHED url={args.live_url} sha256={expected_hash}")
            return 0
    except Exception:
        pass
    if state_matches:
        try:
            smoke_url = github_live_smoke(root, env, commit_hash, args.timeout)
            print(
                f"ALREADY_PUBLISHED_EXTERNAL url={args.live_url} "
                f"sha256={expected_hash} verification={smoke_url}"
            )
            return 0
        except Exception:
            pass

    npx_command = ["npx"]
    npx_path = shutil.which("npx")
    if os.name == "nt" and npx_path:
        npx_cli = Path(npx_path).resolve().parent / "node_modules/npm/bin/npx-cli.js"
        if npx_cli.is_file():
            npx_command = ["node", str(npx_cli)]
    run(
        npx_command
        + [
            "--no-install",
            "wrangler",
            "pages",
            "deploy",
            "public",
            "--project-name",
            PAGES_PROJECT,
            "--branch",
            "main",
            "--commit-hash",
            commit_hash,
            "--commit-message",
            commit_message,
            "--commit-dirty=false",
        ],
        root,
    )
    deadline = time.time() + min(args.timeout, 30)
    last = ""
    while time.time() < deadline:
        try:
            received_hash = live_hash()
            last = received_hash
            if received_hash == expected_hash:
                state_path.write_text(
                    json.dumps(
                        {"commit": commit_hash, "homepage_sha256": expected_hash},
                        sort_keys=True,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                print(f"PUBLISHED url={args.live_url} sha256={received_hash}")
                return 0
        except Exception as exc:
            last = str(exc)
        time.sleep(10)
    smoke_url = github_live_smoke(root, env, commit_hash, max(args.timeout, 60))
    state_path.write_text(
        json.dumps(
            {"commit": commit_hash, "homepage_sha256": expected_hash},
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        f"PUBLISHED_EXTERNAL url={args.live_url} sha256={expected_hash} "
        f"verification={smoke_url} local_error={last}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"PUBLISH_FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)
