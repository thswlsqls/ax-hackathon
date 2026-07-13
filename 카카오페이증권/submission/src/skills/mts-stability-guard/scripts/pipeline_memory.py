"""Persist bounded pipeline memory without trusting stored or appended text."""

from __future__ import annotations

import fcntl
import os
import re
import stat
import unicodedata
from pathlib import Path
from typing import Final, Union

from scripts.safe_filesystem import SafeFilesystemError, open_parent, replace_from

PathInput = Union[str, Path]
Termination = Union[KeyboardInterrupt, SystemExit, GeneratorExit]

SECTIONS: Final[tuple[str, ...]] = (
    "## §0 Run tracking", "## §1 Incident/scenario registry",
    "## §2 Calibration", "## §3 Learned scenario notes",
    "## §4 Process lessons",
)
_TITLE: Final = "# MTS Stability Guard Learnings"
_MAX_ENTRY_CHARS: Final = 500
_MAX_RECENT: Final = 20
_ERR_REGULAR_FILE: Final = "memory path is not a regular file"
_ERR_UTF8: Final = "memory file is not valid UTF-8"
_ERR_STRUCTURE: Final = "memory file has an invalid structure"
_ERR_INPUT: Final = "memory input is invalid or unsafe"
_COMMITTED_ATTR: Final = "_mts_learning_commit_observed"
_SELECTOR_RE: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")
_INSTRUCTION_RE: Final = re.compile(
    r"(?:ignore|disregard|forget)\b.{0,40}\b(?:instructions?|prompt|rules?|previous|prior|above)|(?:override|bypass|disable|evade)\b.{0,40}\b(?:safety|polic(?:y|ies)|guardrails?|instructions?|rules?)|(?:exfiltrate|reveal|dump|leak|steal)\b.{0,40}\b(?:secrets?|credentials?|tokens?|keys?|data)|(?:system|developer|assistant)\s*(?:prompt|message|instruction)|prompt\s*injection|follow\s+(?:these|my)\s+instructions?|(?:이전|위의?)\s*(?:지시|명령).{0,20}(?:무시|잊)|(?:시스템|개발자|어시스턴트)\s*(?:프롬프트|메시지|지시)",
    re.IGNORECASE,
)
_SECRET_RE: Final = re.compile(
    r"(?:^|\s)(?:api[_-]?key|access[_-]?token|token|secret|password|authorization|private[_-]?key)\s*[:=]\s*\S+|(?:^|\s)(?:sk|pk|ghp|github_pat|xox[baprs])-[A-Za-z0-9_-]{8,}",
    re.IGNORECASE,
)
_STRUCTURAL_RE: Final = re.compile(
    r"(?:^|\s)#{1,6}\s|```|<\||\[/?INST\]", re.IGNORECASE)


MemoryEntryError = SafeFilesystemError


def _lock_parent(path: Path) -> tuple[int, str]:
    parent, name = open_parent(path, create=True)
    try:
        fcntl.flock(parent, fcntl.LOCK_EX)
    except OSError:
        os.close(parent)
        raise
    return parent, name


def _unlock_parent(parent: int) -> None:
    try:
        fcntl.flock(parent, fcntl.LOCK_UN)
    finally:
        os.close(parent)


def _read_from(parent: int, name: str) -> str:
    try:
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
    except OSError:
        raise MemoryEntryError(_ERR_REGULAR_FILE) from None
    if not stat.S_ISREG(os.fstat(descriptor).st_mode):
        os.close(descriptor)
        raise MemoryEntryError(_ERR_REGULAR_FILE)
    try:
        with os.fdopen(descriptor, "r", encoding="utf-8") as handle:
            text = handle.read()
    except UnicodeDecodeError:
        raise MemoryEntryError(_ERR_UTF8) from None
    lines = text.splitlines()
    if (
        not lines
        or lines[0] != _TITLE
        or any(section not in lines for section in SECTIONS)
        or not text.endswith("\n")
    ):
        raise MemoryEntryError(_ERR_STRUCTURE)
    return text


def _read_memory(path: Path) -> str:
    parent, name = open_parent(path, create=False)
    try:
        return _read_from(parent, name)
    finally:
        os.close(parent)


def _entry_is_safe(entry: str) -> bool:
    return (
        bool(entry)
        and entry == entry.strip()
        and len(entry) <= _MAX_ENTRY_CHARS
        and "\n" not in entry
        and "\r" not in entry
        and not any(unicodedata.category(char) in {"Cc", "Cf", "Cs"} for char in entry)
        and _INSTRUCTION_RE.search(entry) is None
        and _SECRET_RE.search(entry) is None
        and _STRUCTURAL_RE.search(entry) is None
    )


def _field_matches(entry: str, name: str, value: str) -> bool:
    return (
        re.search(rf"(?:^| ){re.escape(name)}={re.escape(value)}(?: |$)", entry)
        is not None
    )


def _ensure_from(parent: int, name: str) -> None:
    try:
        target = os.stat(name, dir_fd=parent, follow_symlinks=False)
    except FileNotFoundError:
        target = None
    if target is not None:
        _ = _read_from(parent, name)
        return
    lines = [_TITLE, ""]
    for section in SECTIONS:
        lines.extend([section, ""])
    replace_from(parent, name, "\n".join(lines))


def ensure_memory(path: PathInput) -> Path:
    """Create a valid memory file when absent and return its path."""
    memory_path = Path(path)
    parent, name = _lock_parent(memory_path)
    try:
        _ensure_from(parent, name)
    finally:
        _unlock_parent(parent)
    return memory_path


def _append_committed(parent: int, name: str, current: str, line: str) -> bool:
    if current.splitlines().count(line) != 0:
        return False
    try:
        return _read_from(parent, name) == f"{current}{line}\n"
    except (OSError, MemoryEntryError):
        return False


def is_committed_termination(error: Termination) -> bool:
    return getattr(error, _COMMITTED_ATTR, False) is True


def append_learning(path: PathInput, section: str, entry: str) -> bool:
    """Append one learning and report whether parent durability was confirmed."""
    if section not in SECTIONS:
        raise MemoryEntryError(_ERR_INPUT)
    if not _entry_is_safe(entry):
        raise MemoryEntryError(_ERR_INPUT)

    memory_path = Path(path)
    parent, name = _lock_parent(memory_path)
    try:
        _ensure_from(parent, name)
        current = _read_from(parent, name)
        line = f"{section} {entry}"
        try:
            replace_from(parent, name, f"{current}{line}\n")
        except (OSError, MemoryEntryError):
            if not _append_committed(parent, name, current, line):
                raise
            return False
        except (KeyboardInterrupt, SystemExit, GeneratorExit) as termination:
            if not _append_committed(parent, name, current, line):
                raise
            setattr(termination, _COMMITTED_ATTR, True)
            raise
        return True
    finally:
        _unlock_parent(parent)


def select_context(
    path: PathInput,
    pattern: str | None = None,
    status: str = "pending",
    recent: int = 5,
) -> str:
    """Select bounded recent lessons matching status and optional pattern."""
    if not _SELECTOR_RE.fullmatch(status):
        raise MemoryEntryError(_ERR_INPUT)
    if pattern is not None and not _SELECTOR_RE.fullmatch(pattern):
        raise MemoryEntryError(_ERR_INPUT)
    if recent < 1 or recent > _MAX_RECENT:
        raise MemoryEntryError(_ERR_INPUT)

    memory_path = ensure_memory(path)
    lines = _read_memory(memory_path).splitlines()
    entries = [
        line[len(section) + 1 :]
        for line in lines
        for section in SECTIONS
        if line.startswith(f"{section} ") and _entry_is_safe(line[len(section) + 1 :])
    ]
    status_entries = [
        entry for entry in entries if _field_matches(entry, "status", status)
    ]
    pattern_entries = (
        [entry for entry in status_entries if _field_matches(entry, "pattern", pattern)]
        if pattern is not None
        else []
    )
    generic_entries = [
        entry
        for entry in status_entries
        if pattern is None or not _field_matches(entry, "pattern", pattern)
    ]
    selected = pattern_entries[-recent:] + generic_entries[-recent:]
    if not selected:
        return "No prior matching lessons."
    return "\n".join(selected)
