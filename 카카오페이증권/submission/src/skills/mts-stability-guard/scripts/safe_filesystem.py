"""Descriptor-safe filesystem transactions for pipeline artifacts."""

from __future__ import annotations

import contextlib
import os
import secrets
import stat
from pathlib import Path
from typing import Final, Union

PathInput = Union[str, Path]
_ERR_REGULAR_FILE: Final = "path is not a regular file"
_ERR_PATH: Final = "path contains an unsafe component"
_DIRECTORY_FLAGS: Final = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


class SafeFilesystemError(Exception):
    """A descriptor-safe filesystem operation rejected an unsafe path."""


def _open_platform_alias(root: int, name: str) -> int:
    link = os.stat(name, dir_fd=root, follow_symlinks=False)
    if not stat.S_ISLNK(link.st_mode) or link.st_uid != 0:
        raise SafeFilesystemError(_ERR_PATH)
    target = Path(os.readlink(name, dir_fd=root))
    if target.is_absolute() or ".." in target.parts:
        raise SafeFilesystemError(_ERR_PATH)
    descriptor = os.dup(root)
    try:
        for component in target.parts:
            child = os.open(component, _DIRECTORY_FLAGS, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
    except OSError:
        os.close(descriptor)
        raise SafeFilesystemError(_ERR_PATH) from None
    target_stat = os.fstat(descriptor)
    writable = target_stat.st_mode & 0o022
    if target_stat.st_uid != 0 or (writable and not target_stat.st_mode & stat.S_ISVTX):
        os.close(descriptor)
        raise SafeFilesystemError(_ERR_PATH)
    return descriptor


def _close_if_open(descriptor: int) -> None:
    if descriptor >= 0:
        os.close(descriptor)


def open_parent(path: Path, *, create: bool) -> tuple[int, str]:
    """Open a path parent without following unverified symlinks."""
    if ".." in path.parts or not path.name:
        raise SafeFilesystemError(_ERR_PATH)
    absolute = path if path.is_absolute() else Path.cwd() / path
    descriptor = -1
    try:
        descriptor = os.open(absolute.anchor, _DIRECTORY_FLAGS)
        for index, component in enumerate(absolute.parent.parts[1:]):
            try:
                child = os.open(component, _DIRECTORY_FLAGS, dir_fd=descriptor)
            except FileNotFoundError:
                if not create:
                    os.close(descriptor)
                    raise SafeFilesystemError(_ERR_REGULAR_FILE) from None
                with contextlib.suppress(FileExistsError):
                    os.mkdir(component, mode=0o700, dir_fd=descriptor)
                child = os.open(component, _DIRECTORY_FLAGS, dir_fd=descriptor)
            except OSError:
                if index != 0:
                    raise
                child = _open_platform_alias(descriptor, component)
            os.close(descriptor)
            descriptor = child
    except SafeFilesystemError:
        _close_if_open(descriptor)
        raise
    except OSError:
        _close_if_open(descriptor)
        raise SafeFilesystemError(_ERR_PATH) from None
    return descriptor, absolute.name


def replace_from(parent: int, name: str, text: str) -> None:
    """Atomically replace a regular file relative to an open parent."""
    try:
        target = os.stat(name, dir_fd=parent, follow_symlinks=False)
    except FileNotFoundError:
        target = None
    if target is not None and not stat.S_ISREG(target.st_mode):
        raise SafeFilesystemError(_ERR_REGULAR_FILE)
    temporary_name = f".{name}.{secrets.token_hex(16)}"
    descriptor = os.open(
        temporary_name,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        mode=0o600,
        dir_fd=parent,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            _ = handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, name, src_dir_fd=parent, dst_dir_fd=parent)
        os.fsync(parent)
    finally:
        with contextlib.suppress(FileNotFoundError):
            _ = os.stat(temporary_name, dir_fd=parent, follow_symlinks=False)
            os.unlink(temporary_name, dir_fd=parent)


def write_text(path: PathInput, text: str) -> None:
    """Atomically replace a file beneath an already-created directory."""
    parent, name = open_parent(Path(path), create=False)
    try:
        replace_from(parent, name, text)
    finally:
        os.close(parent)


def reserve_directories(primary: PathInput, secondary: PathInput) -> None:
    """Reserve two directories while rolling back only invocation-owned state."""
    primary_parent, primary_name = open_parent(Path(primary), create=True)
    try:
        secondary_parent, secondary_name = open_parent(Path(secondary), create=True)
        try:
            os.mkdir(primary_name, mode=0o700, dir_fd=primary_parent)
            secondary_created = False
            try:
                os.mkdir(secondary_name, mode=0o700, dir_fd=secondary_parent)
                secondary_created = True
            finally:
                if not secondary_created:
                    with contextlib.suppress(OSError):
                        os.rmdir(primary_name, dir_fd=primary_parent)
            os.fsync(primary_parent)
            os.fsync(secondary_parent)
        finally:
            os.close(secondary_parent)
    finally:
        os.close(primary_parent)
