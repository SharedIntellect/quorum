#!/usr/bin/env python3
"""
validate-docs.py — Detect stale documentation against critic-status.yaml.

Reads the manifest, counts shipped critics, and scans all public .md files for:
  1. Hardcoded critic counts that don't match shipped count
  2. Status markers (🔜, "Planned", "coming") for critics that are actually shipped
  3. "What's coming" / roadmap references to shipped features

Exit codes:
  0 = clean (no findings)
  1 = findings detected
  2 = error (missing manifest, bad YAML, etc.)
"""

import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(2)


def load_manifest(repo_root: Path) -> dict:
    """Load and parse critic-status.yaml."""
    manifest_path = repo_root / "critic-status.yaml"
    if not manifest_path.exists():
        print(f"ERROR: {manifest_path} not found", file=sys.stderr)
        sys.exit(2)
    with open(manifest_path) as f:
        return yaml.safe_load(f)


def get_shipped_critics(manifest: dict) -> dict[str, dict]:
    """Return dict of critic_name -> info for all shipped critics."""
    return {
        name: info
        for name, info in manifest.get("critics", {}).items()
        if info.get("status") == "shipped"
    }


def get_planned_critics(manifest: dict) -> dict[str, dict]:
    """Return dict of critic_name -> info for all planned critics."""
    return {
        name: info
        for name, info in manifest.get("critics", {}).items()
        if info.get("status") == "planned"
    }


def find_md_files(repo_root: Path) -> list[Path]:
    """Find all .md files in the repo, excluding dirs that shouldn't be validated."""
    exclude_dirs = {
        "venv", "node_modules", ".git", "quorum-runs", "__pycache__", "dist",
        ".hypothesis", "external-reviews",  # external reviews are point-in-time snapshots
    }
    exclude_files = {
        "SHIPPING.md",      # contains historical context about the problem
        "CHANGELOG.md",     # historical entries reflect state at time of release
    }
    results = []
    for p in repo_root.rglob("*.md"):
        parts = set(p.relative_to(repo_root).parts)
        if not parts & exclude_dirs and p.name not in exclude_files:
            results.append(p)
    return sorted(results)


def check_hardcoded_counts(lines: list[str], shipped_count: int, file_path: Path) -> list[str]:
    """Flag lines with hardcoded critic counts that don't match shipped count."""
    findings = []
    # Match patterns like "4 critics", "ships with 4", "currently 5 critics"
    count_pattern = re.compile(r'\b(\d+)\s+critics?\b', re.IGNORECASE)
    # Also match "ships with N", "ships N critics"
    ships_pattern = re.compile(r'ship[s]?\s+(?:with\s+)?(\d+)', re.IGNORECASE)

    for i, line in enumerate(lines, 1):
        # Skip lines that are clearly talking about the target architecture (9 critics)
        if "9" in line and ("target" in line.lower() or "architecture" in line.lower() or "full" in line.lower()):
            continue
        # Skip lines about thread pool / parallel limits (e.g., "max 4 critics in parallel")
        if "parallel" in line.lower() or "threadpool" in line.lower() or "max" in line.lower():
            continue

        for pattern in [count_pattern, ships_pattern]:
            for match in pattern.finditer(line):
                n = int(match.group(1))
                # Only flag if it looks like a shipped count that's wrong
                # Skip 9 (total architecture), 3 (planned), and the correct count
                if n != shipped_count and n in range(2, 9) and n != 9:
                    # Check if this line is about shipped/current critics (not planned/remaining)
                    line_lower = line.lower()
                    # Skip lines about specific depth profiles with intentionally fewer critics
                    # (e.g., "quick" depth legitimately runs 2 critics)
                    if "quick" in line_lower and n == 2:
                        continue
                    if any(kw in line_lower for kw in [
                        "ship", "current", "today", "implement", "available",
                        "standard", "have", "run"
                    ]):
                        findings.append(
                            f"  {file_path}:{i}: Hardcoded count '{match.group(0)}' "
                            f"(shipped={shipped_count}): {line.strip()[:120]}"
                        )
    return findings


def check_stale_status_markers(
    lines: list[str], shipped_critics: dict, file_path: Path
) -> list[str]:
    """Flag status markers (🔜, Planned, coming) for critics that are actually shipped."""
    findings = []
    shipped_names = {
        name.replace("_", "[ _-]?"): name
        for name in shipped_critics
    }
    # Also add display names
    display_map = {
        "cross.consistency": "cross_consistency",
        "cross.artifact": "cross_consistency",
        "code.hygiene": "code_hygiene",
    }

    for i, line in enumerate(lines, 1):
        line_lower = line.lower()
        # Check if line has a stale marker
        has_stale_marker = any(marker in line for marker in ["🔜", "Planned", "planned", "coming"])
        if not has_stale_marker:
            continue
        # Skip lines that also say "shipped" or "implemented" (describing current state)
        if any(kw in line_lower for kw in ["shipped", "implemented", "✅"]):
            continue

        # Check if line references a shipped critic by distinctive name
        # Skip generic words like "security", "correctness" that appear in other contexts
        distinctive_shipped = {
            name: info for name, info in shipped_critics.items()
            if name not in ("security", "correctness", "completeness")
        }
        distinctive_names = {
            name.replace("_", "[ _-]?"): name
            for name in distinctive_shipped
        }
        for pattern_name, canonical_name in list(distinctive_names.items()) + [
            (k, v) for k, v in display_map.items()
        ]:
            if re.search(pattern_name, line_lower) or canonical_name.replace("_", " ") in line_lower:
                findings.append(
                    f"  {file_path}:{i}: Stale marker for shipped critic "
                    f"'{canonical_name}': {line.strip()[:120]}"
                )
                break

    return findings


def check_roadmap_shipped(
    lines: list[str], shipped_critics: dict, file_path: Path
) -> list[str]:
    """Flag 'roadmap' or 'what's coming' sections that list shipped critics."""
    findings = []
    in_roadmap = False
    # Only check for critic names that are distinctive enough to not be common words.
    # "security" and "correctness" are too generic — they appear in rubric domain
    # descriptions, improvement roadmaps, etc. without referring to the critic.
    shipped_lower = set()
    shipped_lower.add("tester")
    shipped_lower.add("cross-consistency")
    shipped_lower.add("cross consistency")
    shipped_lower.add("cross artifact")
    shipped_lower.add("code hygiene")

    for i, line in enumerate(lines, 1):
        line_lower = line.lower()
        # Detect roadmap/coming sections
        if any(kw in line_lower for kw in ["what's coming", "roadmap", "what is coming", "planned"]):
            if line.startswith("#") or line.startswith("**"):
                in_roadmap = True
                continue
        # Exit roadmap section on next heading
        if in_roadmap and line.startswith("#") and "coming" not in line.lower() and "roadmap" not in line.lower():
            in_roadmap = False

        if in_roadmap:
            for critic_name in shipped_lower:
                if critic_name in line_lower:
                    findings.append(
                        f"  {file_path}:{i}: Shipped critic '{critic_name}' listed in "
                        f"roadmap/coming section: {line.strip()[:120]}"
                    )
                    break

    return findings


def main():
    # Find repo root (script is in tools/)
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent

    manifest = load_manifest(repo_root)
    shipped = get_shipped_critics(manifest)
    planned = get_planned_critics(manifest)
    shipped_count = len(shipped)
    manifest_version = manifest.get("version", "unknown")

    print(f"Manifest version: {manifest_version}")
    print(f"Shipped critics ({shipped_count}): {', '.join(shipped.keys())}")
    print(f"Planned critics ({len(planned)}): {', '.join(planned.keys())}")
    print()

    md_files = find_md_files(repo_root)
    print(f"Scanning {len(md_files)} markdown files...\n")

    all_findings = []
    for md_file in md_files:
        try:
            lines = md_file.read_text(encoding="utf-8").splitlines()
        except Exception as e:
            print(f"WARNING: Could not read {md_file}: {e}", file=sys.stderr)
            continue

        rel_path = md_file.relative_to(repo_root)
        all_findings.extend(check_hardcoded_counts(lines, shipped_count, rel_path))
        all_findings.extend(check_stale_status_markers(lines, shipped, rel_path))
        all_findings.extend(check_roadmap_shipped(lines, shipped, rel_path))

    if all_findings:
        print(f"FINDINGS ({len(all_findings)}):\n")
        for f in all_findings:
            print(f)
        print(f"\n❌ {len(all_findings)} documentation discrepancies found.")
        print("Update the listed files to match critic-status.yaml, then re-run.")
        return 1
    else:
        print("✅ All documentation matches critic-status.yaml. No stale references found.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
