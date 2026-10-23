#!/usr/bin/env python3
"""Check skill structure and local references without dependencies."""
from pathlib import Path
import re


def main() -> int:
    skill = Path(__file__).resolve().parents[1] / "skills" / "relay-media"
    source = (skill / "SKILL.md").read_text(encoding="utf-8")
    assert source.startswith("---\n"), "Missing frontmatter"
    header = source.split("---", 2)[1]
    assert re.search(r"^name: relay-media$", header, re.M), "Wrong name"
    assert re.search(r"^description: \S.+", header, re.M), "Missing description"
    assert "[TODO" not in source, "Unfinished scaffold"
    for target in re.findall(r"\]\(([^)]+)\)", source):
        if "://" not in target:
            assert (skill / target).is_file(), f"Missing reference: {target}"
    metadata = (skill / "agents" / "openai.yaml").read_text(encoding="utf-8")
    assert 'display_name: "Relay Media"' in metadata, "Missing UI title"
    assert (skill / "scripts" / "media.py").is_file(), "Missing client"
    print("Skill structure and local references are valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
