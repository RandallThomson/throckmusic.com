#!/usr/bin/env python3
"""
Build the site, then commit and push the changes so GitHub Actions
picks them up and publishes them to the public site.

Usage:
    python build-publish.py
"""

import subprocess
import sys

from build import build


def run(cmd):
    print(f"$ {' '.join(cmd)}")
    return subprocess.run(cmd, check=True)


def main():
    print("Building site...\n")
    build()

    run(["git", "add", "-A"])

    status = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
    )
    if status.returncode == 0:
        print("\nNo changes to publish.")
        return

    run(["git", "commit", "-m", "na"])
    run(["git", "push"])
    print("\nPublished. GitHub Actions will deploy the update shortly.")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        print(f"\nCommand failed: {e}", file=sys.stderr)
        sys.exit(1)
