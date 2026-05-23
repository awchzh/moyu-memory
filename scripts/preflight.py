#!/usr/bin/env python3
"""preflight.py — Pre-build verification for MOYU releases.

Ensures no internal/private files leak into distributions.
Run before `python3 -m build`.

Exit code 0 = safe to build. Non-zero = fix issues first.
"""

import os
import sys
import glob

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORBIDDEN = [
    "墨羽项目.md",
    "墨羽项目_学习者模块设计.md",
    "moyu_toolkit/SKILL.md",
    "moyu_toolkit/墨羽项目.md",
    "moyu_toolkit/墨羽项目_学习者模块设计.md",
]

SDIST_FORBIDDEN = [
    "墨羽项目.md",
    "SKILL.md",
]


def check_source_tree():
    """Check source files for forbidden internal documents."""
    errors = []
    for pattern in FORBIDDEN:
        path = os.path.join(REPO_ROOT, pattern)
        if os.path.exists(path):
            tracked = os.popen(f"cd {REPO_ROOT} && git ls-files --error-unmatch '{path}' 2>/dev/null").read()
            if tracked:
                errors.append(f"  🔴 {pattern} is tracked by git — should not be committed!")
            # not tracked = intentional exclusion, silently pass

    # Check MANIFEST.in covers these
    manifest_path = os.path.join(REPO_ROOT, "MANIFEST.in")
    if os.path.exists(manifest_path):
        with open(manifest_path) as f:
            manifest = f.read()
        for fname in SDIST_FORBIDDEN:
            if fname not in manifest:
                errors.append(f"  🔴 {fname} not excluded in MANIFEST.in")
    else:
        errors.append("  🔴 MANIFEST.in not found — sdist will include everything")

    return errors


def check_pyproject():
    """Check pyproject.toml has exclude rules."""
    path = os.path.join(REPO_ROOT, "pyproject.toml")
    if not os.path.exists(path):
        return ["  🔴 pyproject.toml not found"]

    with open(path) as f:
        content = f.read()

    errors = []
    for section in ["exclude-package-data"]:
        if section not in content:
            errors.append(f"  🔴 [{section}] missing from pyproject.toml")
            return errors

    if "墨羽项目.md" not in content:
        errors.append("  🔴 墨羽项目.md not excluded in pyproject.toml exclude-package-data")
    if "SKILL.md" not in content:
        errors.append("  🔴 SKILL.md not excluded in pyproject.toml exclude-package-data")

    return errors


def main():
    print("🔍 MOYU Pre-flight Check")
    print("─" * 40)

    all_errors = []
    all_errors.extend(check_source_tree())
    all_errors.extend(check_pyproject())

    if all_errors:
        print("\n❌ Issues found (fix before build):")
        for e in all_errors:
            print(e)
        sys.exit(1)
    else:
        print("✅ All checks passed — safe to build.")
        sys.exit(0)


if __name__ == "__main__":
    main()
