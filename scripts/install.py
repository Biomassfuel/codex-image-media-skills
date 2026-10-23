#!/usr/bin/env python3
"""Install the repository's relay-media skill without overwriting user files."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import tempfile
from uuid import uuid4


SKILL_NAME = "relay-media"
RESOURCE_DIRECTORIES = ("agents", "scripts", "references", "assets")
EXCLUDED_DIRECTORIES = {"__pycache__", "node_modules", "output", "outputs"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".pem", ".key", ".p12", ".pfx", ".jks", ".kdbx"}
PRIVATE_NAME = re.compile(
    r"(^|[._-])(secrets?|credentials?|tokens?|api[_-]?keys?|auth)([._-]|$)",
    re.IGNORECASE,
)


class InstallError(RuntimeError):
    """An installation cannot proceed without risking existing files."""


@dataclass(frozen=True)
class InstallResult:
    target: Path
    files: tuple[str, ...]
    backup: Path | None = None
    dry_run: bool = False


def default_destination() -> Path:
    """Return the skills parent directory, honoring a nonempty CODEX_HOME."""
    configured_home = os.environ.get("CODEX_HOME")
    return (Path(configured_home).expanduser() if configured_home else Path.home() / ".codex") / "skills"


def _exists(path: Path) -> bool:
    # exists() alone misses broken symlinks.
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    return True


def _plain_path(path: Path, label: str) -> Path:
    """Reject links and Windows junctions before resolving a candidate path."""
    candidate = path.expanduser().absolute()
    for part in (candidate, *candidate.parents):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        except OSError as error:
            raise InstallError(f"Cannot inspect {label} {part}: {error}") from error
        reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & reparse_flag:
            raise InstallError(f"Refusing {label}: symlink or junction at {part}")
        if part != candidate and not stat.S_ISDIR(info.st_mode):
            raise InstallError(f"Refusing {label}: parent is not a directory: {part}")
    return candidate.resolve()


def _excluded(path: Path) -> bool:
    return (
        path.name.startswith(".")
        or path.name.lower() in EXCLUDED_DIRECTORIES
        or path.suffix.lower() in EXCLUDED_SUFFIXES
        or PRIVATE_NAME.search(path.name) is not None
    )


def _skill_files(source: Path) -> tuple[Path, ...]:
    entrypoint = source / "SKILL.md"
    _plain_path(entrypoint, "skill entrypoint")
    if not entrypoint.is_file():
        raise InstallError(f"Skill entrypoint is missing: {entrypoint}")
    collected = [Path("SKILL.md")]
    for resource_name in RESOURCE_DIRECTORIES:
        resource = source / resource_name
        if not _exists(resource):
            continue
        _plain_path(resource, "skill resource")
        if not resource.is_dir():
            raise InstallError(f"Skill resource must be a directory: {resource}")
        for current, directories, filenames in os.walk(resource, followlinks=False):
            current_path = Path(current)
            kept_directories = []
            for name in sorted(directories):
                child = current_path / name
                if _excluded(child):
                    continue
                _plain_path(child, "skill resource")
                kept_directories.append(name)
            directories[:] = kept_directories
            for name in sorted(filenames):
                child = current_path / name
                if _excluded(child):
                    continue
                _plain_path(child, "skill resource")
                if not stat.S_ISREG(child.stat().st_mode):
                    raise InstallError(f"Skill resource must be a regular file: {child}")
                collected.append(child.relative_to(source))
    return tuple(collected)


def _backup_name(target: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    while True:
        candidate = target.with_name(f".{target.name}.backup-{stamp}-{uuid4().hex[:8]}")
        if not _exists(candidate):
            return candidate


def _publish(staging: Path, target: Path, force: bool) -> Path | None:
    _plain_path(target, "installation target")
    backup = None
    if _exists(target):
        if not target.is_dir():
            raise InstallError(f"Installation target is not a directory: {target}")
        if not force:
            raise InstallError(f"Skill already exists: {target}. Use --force to preserve it in a backup and replace it.")
        backup = _backup_name(target)
        target.rename(backup)
    try:
        # Recheck after preparing the backup; never deliberately replace a newly appeared target.
        if _exists(target):
            raise InstallError(f"Installation target appeared during installation: {target}")
        staging.rename(target)
    except (OSError, InstallError) as error:
        if backup is not None:
            if _exists(target):
                raise InstallError(f"Installation failed; original skill is preserved at {backup}: {error}") from error
            try:
                backup.rename(target)
            except OSError as recovery_error:
                raise InstallError(
                    f"Installation failed; restore the preserved original from {backup}. "
                    f"Restore error: {recovery_error}; install error: {error}"
                ) from error
            raise InstallError(f"Installation failed; the original skill was restored: {error}") from error
        raise InstallError(f"Installation failed: {error}") from error
    return backup


def install(source: Path, destination: Path, *, force: bool = False, dry_run: bool = False) -> InstallResult:
    """Install into a skills parent directory; force always preserves a sibling backup."""
    source = _plain_path(Path(source), "skill source")
    if not source.is_dir():
        raise InstallError(f"Skill source directory is missing: {source}")
    destination = _plain_path(Path(destination), "skills destination")
    if _exists(destination) and not destination.is_dir():
        raise InstallError(f"Skills destination is not a directory: {destination}")
    target = _plain_path(destination / SKILL_NAME, "installation target")
    if target == source or target.is_relative_to(source) or source.is_relative_to(target):
        raise InstallError(f"Source and target must not be the same or nested: {source} / {target}")
    if _exists(target):
        if not target.is_dir():
            raise InstallError(f"Installation target is not a directory: {target}")
        if not force:
            raise InstallError(f"Skill already exists: {target}. Use --force to preserve it in a backup and replace it.")
    files = _skill_files(source)
    file_names = tuple(path.as_posix() for path in files)
    if dry_run:
        return InstallResult(target=target, files=file_names, dry_run=True)

    destination.mkdir(parents=True, exist_ok=True)
    _plain_path(destination, "skills destination")
    staging = Path(tempfile.mkdtemp(prefix=f".{SKILL_NAME}.staging-", dir=destination))
    try:
        for relative in files:
            original = source / relative
            _plain_path(original, "skill resource")
            copied = staging / relative
            copied.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(original, copied)
        backup = _publish(staging, target, force)
    finally:
        # Only remove this invocation's newly created staging directory, never an existing skill or backup.
        if _exists(staging):
            checked = _plain_path(staging, "temporary staging directory")
            if checked.parent != destination or not checked.name.startswith(f".{SKILL_NAME}.staging-"):
                raise InstallError(f"Refusing to clean unexpected staging path: {checked}")
            shutil.rmtree(checked)
    return InstallResult(target=target, files=file_names, backup=backup)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install the relay-media skill into Codex.")
    parser.add_argument("--dest", type=Path, default=None, metavar="SKILLS_DIR", help="skills parent directory (default: CODEX_HOME/skills or ~/.codex/skills)")
    parser.add_argument("--force", action="store_true", help="preserve an existing skill in a sibling backup before replacement")
    parser.add_argument("--dry-run", action="store_true", help="validate and list files without creating or changing anything")
    arguments = parser.parse_args(argv)
    source = Path(__file__).resolve().parent.parent / "skills" / SKILL_NAME
    try:
        result = install(source, arguments.dest or default_destination(), force=arguments.force, dry_run=arguments.dry_run)
    except (InstallError, OSError) as error:
        print(f"Installation error: {error}", file=sys.stderr)
        return 1
    if result.dry_run:
        print(f"Dry run: would install {len(result.files)} files into {result.target}")
        if _exists(result.target) and arguments.force:
            print("The existing skill would be preserved in a sibling backup.")
        for name in result.files:
            print(f"  {name}")
    else:
        print(f"Installed {len(result.files)} files into {result.target}")
        if result.backup is not None:
            print(f"Previous skill preserved at {result.backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
