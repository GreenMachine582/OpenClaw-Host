#!/usr/bin/env python3
# scripts/validate_credentials.py
# Validates all configured API keys and tokens by making lightweight API calls.
#
# Usage:
#   python scripts/validate_credentials.py
#   python scripts/validate_credentials.py --integration anthropic
#   python scripts/validate_credentials.py --integration github

import argparse
import os
import sys
import urllib.request
import urllib.error
import json
from pathlib import Path

GREEN = "\033[0;32m"
RED = "\033[0;31m"
YELLOW = "\033[1;33m"
NC = "\033[0m"


def load_env(path: Path) -> dict:
    """Load key=value pairs from an env file, ignoring comments and blanks."""
    env = {}
    if not path.exists():
        return env
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip()
    return env


def get(key: str, env_overlay: dict) -> str:
    return env_overlay.get(key) or os.environ.get(key, "")


def pass_(msg): print(f"{GREEN}✓{NC} {msg}")
def fail(msg): print(f"{RED}✗{NC} {msg}"); return False
def warn(msg): print(f"{YELLOW}!{NC} {msg}")


def validate_anthropic(env: dict) -> bool:
    api_key = get("ANTHROPIC_API_KEY", env)
    if not api_key or api_key == "your_key_here":
        return fail("ANTHROPIC_API_KEY is not set")

    try:
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/models",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                pass_("Anthropic API key is valid")
                return True
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return fail("Anthropic API key is invalid or revoked")
        return fail(f"Anthropic API returned HTTP {e.code}")
    except Exception as e:
        return fail(f"Anthropic connectivity error: {e}")
    return False


def validate_github(env: dict) -> bool:
    token = get("GITHUB_TOKEN", env)
    owner = get("GITHUB_OWNER", env)

    if not token or token == "your_token_here":
        return fail("GITHUB_TOKEN is not set")

    ok = True
    try:
        req = urllib.request.Request(
            "https://api.github.com/user",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            authed_user = data.get("login", "unknown")
            pass_(f"GitHub token is valid (authenticated as: {authed_user})")

            # Warn if owner doesn't match authenticated user
            if owner and owner != authed_user:
                warn(f"GITHUB_OWNER '{owner}' differs from authenticated user '{authed_user}' — OK if using an org token")

    except urllib.error.HTTPError as e:
        if e.code == 401:
            ok = fail("GitHub token is invalid or revoked")
        else:
            ok = fail(f"GitHub API returned HTTP {e.code}")
    except Exception as e:
        ok = fail(f"GitHub connectivity error: {e}")

    # Fine-grained PATs do not expose scopes via X-OAuth-Scopes.
    # Permission validation must be done by attempting an actual API call.
    try:
        req = urllib.request.Request(
            f"https://api.github.com/repos/{get('GITHUB_OWNER', env)}",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.headers.get("X-OAuth-Scopes"):
                warn("Classic token detected — fine-grained PAT recommended (see integrations/github/README.md)")
            else:
                pass_("Fine-grained PAT detected")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            warn("Could not verify repo access — check GITHUB_OWNER and token resource scope")
    except Exception:
        pass  # Non-critical

    return ok


VALIDATORS = {
    "anthropic": validate_anthropic,
    "github": validate_github,
}


def main():
    parser = argparse.ArgumentParser(description="Validate OpenClaw credentials")
    parser.add_argument("--integration", choices=list(VALIDATORS), help="Validate a specific integration only")
    args = parser.parse_args()

    targets = [args.integration] if args.integration else list(VALIDATORS)
    results = []

    for name in targets:
        print(f"\n--- {name.capitalize()} ---")
        env_file = Path(f"integrations/{name}/.env")
        env = load_env(env_file)
        if not env_file.exists():
            warn(f"No .env found at {env_file} — falling back to environment variables")
        result = VALIDATORS[name](env)
        results.append(result)

    print("")
    if all(results):
        print(f"{GREEN}All credentials valid.{NC}")
    else:
        print(f"{RED}One or more credentials failed validation.{NC}")
        sys.exit(1)


if __name__ == "__main__":
    main()
