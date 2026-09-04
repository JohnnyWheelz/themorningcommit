#!/usr/bin/env python3
"""Guard, commit, push, and verify a themorningcommit release."""
from __future__ import annotations

import argparse
import hashlib
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

    try:
        if live_hash() == expected_hash:
            print(f"ALREADY_PUBLISHED url={args.live_url} sha256={expected_hash}")
            return 0
    except Exception:
        pass

    commit_hash = run(["git", "rev-parse", "HEAD"], root).stdout.strip()
    commit_message = run(["git", "log", "-1", "--pretty=%s"], root).stdout.strip()
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
    deadline = time.time() + args.timeout
    last = ""
    while time.time() < deadline:
        try:
            received_hash = live_hash()
            last = received_hash
            if received_hash == expected_hash:
                print(f"PUBLISHED url={args.live_url} sha256={received_hash}")
                return 0
        except Exception as exc:
            last = str(exc)
        time.sleep(10)
    raise RuntimeError(
        f"live verification failed; expected {expected_hash}, last {last}"
    )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"PUBLISH_FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)
