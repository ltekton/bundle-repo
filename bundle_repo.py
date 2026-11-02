#!/usr/bin/env python3
"""bundle-repo: create, verify, and reconstruct auditable Git index bundles."""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unicodedata
import uuid
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, fields
from enum import StrEnum
from fnmatch import fnmatchcase
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Protocol, Self, cast

# Implemented normative requirements:
# BR-REQ-CREATE-001 BR-REQ-CREATE-002 BR-REQ-CREATE-003 BR-REQ-CREATE-004 BR-REQ-CREATE-005
# BR-REQ-VERIFY-001 BR-REQ-VERIFY-002 BR-REQ-VERIFY-003 BR-REQ-VERIFY-004 BR-REQ-RECON-001 BR-REQ-RECON-002 BR-REQ-RECON-003 BR-REQ-RECON-004 BR-REQ-CLI-001 BR-REQ-CLI-002 BR-REQ-CLI-003
# BR-SI-001 BR-SI-002 BR-SI-003 BR-SI-004 BR-SI-005 BR-SI-006 BR-SI-007 BR-SI-008 BR-SI-009 BR-SI-010 BR-SI-011 BR-SI-012

FORMAT = "bundle-repo"
VERSION = 1
MIN_PART_BYTES = 2048
MAX_MANIFEST_BYTES = 16 * 1024 * 1024
MAX_RECORD_BYTES = 64 * 1024 * 1024
MAX_PATH_BYTES = 4096
MAX_COMPONENT_BYTES = 255
MIN_CHUNK_BYTES = 1
DEFAULT_PART_BYTES = 4 * 1024 * 1024
DEFAULT_CHUNK_BYTES = 512 * 1024
HEX = frozenset("0123456789abcdef")


class BundleError(Exception):
    exit_code = 2


class RepositoryError(BundleError):
    pass


class FormatError(BundleError):
    pass


class IntegrityError(BundleError):
    pass


class ReconstructionError(BundleError):
    pass


@dataclass(frozen=True, slots=True)
class ResourceLimits:
    max_manifest_bytes: int = MAX_MANIFEST_BYTES
    max_record_bytes: int = MAX_RECORD_BYTES
    max_parts: int = 10_000
    max_entries: int = 1_000_000
    max_path_bytes: int = MAX_PATH_BYTES
    max_component_bytes: int = MAX_COMPONENT_BYTES
    max_payload_bytes: int = 1 << 40

    def __post_init__(self) -> None:
        for item in fields(self):
            value = getattr(self, item.name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise FormatError(f"{item.name} must be a positive integer")


def strict_json_loads(data: str | bytes) -> object:
    """Decode JSON while rejecting duplicate object member names."""

    def no_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise FormatError(f"duplicate JSON key: {key!r}")
            result[key] = value
        return result

    try:
        return json.loads(data, object_pairs_hook=no_duplicates)
    except FormatError:
        raise
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise FormatError(f"invalid JSON: {exc}") from exc


def require_fields(raw: dict[str, object], required: set[str], name: str) -> None:
    actual = set(raw)
    missing = required - actual
    unknown = actual - required
    require(not missing, f"{name} is missing fields: {sorted(missing)}")
    require(not unknown, f"{name} has unknown fields: {sorted(unknown)}")


def require(condition: bool, message: str, exc: type[BundleError] = FormatError) -> None:
    if not condition:
        raise exc(message)


def require_int(value: object, name: str, minimum: int = 0) -> int:
    require(
        not isinstance(value, bool) and isinstance(value, int) and value >= minimum,
        f"{name} must be an integer >= {minimum}",
    )
    return cast(int, value)


def require_str(value: object, name: str) -> str:
    require(isinstance(value, str), f"{name} must be a string")
    return cast(str, value)


def require_mapping(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise FormatError(f"{name} must be an object")
    return cast(dict[str, object], value)


def require_array(value: object, name: str) -> list[object]:
    if not isinstance(value, list):
        raise FormatError(f"{name} must be an array")
    return cast(list[object], value)


def require_sha256(value: object, name: str) -> str:
    text = require_str(value, name)
    require(
        len(text) == 64 and all(c in HEX for c in text),
        f"{name} must be a lowercase SHA-256 digest",
    )
    return text


def require_oid(value: object, name: str) -> str:
    text = require_str(value, name)
    require(
        len(text) in (40, 64) and all(c in HEX for c in text),
        f"{name} must be a lowercase Git object ID",
    )
    return text


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("ascii")


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    tmp = Path(name)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


class EntryType(StrEnum):
    FILE = "file"
    SYMLINK = "symlink"
    GITLINK = "gitlink"


@dataclass(frozen=True, slots=True)
class RepositoryPath:
    value: PurePosixPath

    @classmethod
    def parse(cls, raw: object) -> Self:
        text = require_str(raw, "path")
        p = PurePosixPath(text)
        encoded = text.encode("utf-8", "surrogateescape")
        portable_unsafe = set('<>:"|?*')
        reserved = {
            "CON",
            "PRN",
            "AUX",
            "NUL",
            *(f"COM{i}" for i in range(1, 10)),
            *(f"LPT{i}" for i in range(1, 10)),
        }
        require(
            bool(text)
            and "\x00" not in text
            and "\\" not in text
            and not p.is_absolute()
            and ".." not in p.parts
            and all(part not in ("", ".") for part in p.parts),
            f"unsafe repository path: {text!r}",
        )
        require(
            unicodedata.normalize("NFC", text) == text,
            f"repository path is not NFC-normalized: {text!r}",
        )
        require(
            len(encoded) <= MAX_PATH_BYTES, f"repository path exceeds {MAX_PATH_BYTES} UTF-8 bytes"
        )
        for part in p.parts:
            require(
                len(part.encode("utf-8", "surrogateescape")) <= MAX_COMPONENT_BYTES,
                "repository path component is too long",
            )
            require(
                not any(ord(c) < 32 or c in portable_unsafe for c in part),
                f"non-portable repository path component: {part!r}",
            )
            require(
                not part.endswith((".", " ")), f"non-portable repository path component: {part!r}"
            )
            stem = part.split(".", 1)[0].upper()
            require(stem not in reserved, f"reserved repository path component: {part!r}")
        return cls(p)

    def __str__(self) -> str:
        return self.value.as_posix()

    @property
    def parts(self) -> tuple[str, ...]:
        return self.value.parts


@dataclass(frozen=True, slots=True)
class GitEntry:
    path: RepositoryPath
    mode: str
    object_id: str

    def __post_init__(self) -> None:
        require(
            self.mode in {"100644", "100755", "120000", "160000"},
            f"unsupported Git mode: {self.mode}",
            RepositoryError,
        )
        require_oid(self.object_id, "Git object ID")

    @property
    def kind(self) -> EntryType:
        return (
            EntryType.GITLINK
            if self.mode == "160000"
            else EntryType.SYMLINK
            if self.mode == "120000"
            else EntryType.FILE
        )


@dataclass(frozen=True, slots=True)
class RepositoryMetadata:
    branch: str | None
    commit: str | None
    dirty: bool

    def __post_init__(self) -> None:
        if self.commit is not None:
            require_oid(self.commit, "repository commit")

    def to_dict(self) -> dict[str, object]:
        return {"branch": self.branch, "commit": self.commit, "dirty": self.dirty}

    @classmethod
    def from_dict(cls, raw: object) -> Self:
        require(isinstance(raw, dict), "repository must be an object")
        raw = cast(dict[str, object], raw)
        require_fields(raw, {"branch", "commit", "dirty"}, "repository")
        branch = raw.get("branch")
        commit = raw.get("commit")
        dirty = raw.get("dirty")
        if branch is not None and not isinstance(branch, str):
            raise FormatError("repository.branch must be string or null")
        if commit is not None and not isinstance(commit, str):
            raise FormatError("repository.commit must be string or null")
        if not isinstance(dirty, bool):
            raise FormatError("repository.dirty must be boolean")
        return cls(branch, commit, dirty)


@dataclass(frozen=True, slots=True)
class SelectionPolicy:
    includes: tuple[str, ...] = ()
    excludes: tuple[str, ...] = ()

    def matches(self, path: RepositoryPath) -> bool:
        text = str(path)
        included = not self.includes or any(pattern_matches(text, p) for p in self.includes)
        excluded = any(pattern_matches(text, p) for p in self.excludes)
        return included and not excluded


def pattern_matches(path: str, pattern: str) -> bool:
    pattern = pattern.strip()
    require(
        bool(pattern)
        and "\x00" not in pattern
        and "\\" not in pattern
        and not pattern.startswith("/")
        and ".." not in PurePosixPath(pattern.rstrip("/")).parts,
        f"unsafe selection pattern: {pattern!r}",
    )
    if pattern.endswith("/"):
        base = pattern.rstrip("/")
        return path == base or path.startswith(base + "/")
    if "/" in pattern:
        return fnmatchcase(path, pattern)
    return any(fnmatchcase(part, pattern) for part in PurePosixPath(path).parts)


@dataclass(frozen=True, slots=True)
class ManifestEntry:
    path: RepositoryPath
    mode: str
    kind: EntryType
    git_object: str
    size: int
    sha256: str | None
    chunks: int

    def __post_init__(self) -> None:
        require(self.mode in {"100644", "100755", "120000", "160000"}, f"invalid mode: {self.mode}")
        require((self.mode == "160000") == (self.kind is EntryType.GITLINK), "mode/type mismatch")
        require((self.mode == "120000") == (self.kind is EntryType.SYMLINK), "mode/type mismatch")
        require_oid(self.git_object, "entry git_object")
        require_int(self.size, "entry bytes")
        require_int(self.chunks, "entry chunks")
        if self.kind is EntryType.GITLINK:
            require(
                self.size == 0 and self.sha256 is None and self.chunks == 0,
                "gitlink metadata is inconsistent",
            )
        else:
            require_sha256(self.sha256, "entry sha256")
            require(self.chunks >= 1, "content entry must have at least one chunk")

    def to_dict(self) -> dict[str, object]:
        return {
            "path": str(self.path),
            "mode": self.mode,
            "type": self.kind.value,
            "git_object": self.git_object,
            "bytes": self.size,
            "sha256": self.sha256,
            "chunks": self.chunks,
        }

    @classmethod
    def from_dict(cls, raw: object) -> Self:
        require(isinstance(raw, dict), "entry must be an object")
        raw = cast(dict[str, object], raw)
        require_fields(
            raw, {"path", "mode", "type", "git_object", "bytes", "sha256", "chunks"}, "entry"
        )
        try:
            kind = EntryType(require_str(raw.get("type"), "entry type"))
        except ValueError as exc:
            raise FormatError("unknown entry type") from exc
        sha = raw.get("sha256")
        return cls(
            RepositoryPath.parse(raw.get("path")),
            require_str(raw.get("mode"), "entry mode"),
            kind,
            require_oid(raw.get("git_object"), "entry git_object"),
            require_int(raw.get("bytes"), "entry bytes"),
            None if sha is None else require_sha256(sha, "entry sha256"),
            require_int(raw.get("chunks"), "entry chunks"),
        )


@dataclass(frozen=True, slots=True)
class PartInfo:
    number: int
    name: str
    size: int
    sha256: str

    def __post_init__(self) -> None:
        require_int(self.number, "part number", 1)
        require_int(self.size, "part bytes")
        require_sha256(self.sha256, "part sha256")
        require(
            self.name == Path(self.name).name and self.name not in ("", ".", ".."),
            "unsafe part name",
        )

    def to_dict(self) -> dict[str, object]:
        return {"number": self.number, "name": self.name, "bytes": self.size, "sha256": self.sha256}

    @classmethod
    def from_dict(cls, raw: object) -> Self:
        require(isinstance(raw, dict), "part must be an object")
        raw = cast(dict[str, object], raw)
        require_fields(raw, {"number", "name", "bytes", "sha256"}, "part")
        return cls(
            require_int(raw.get("number"), "part number", 1),
            require_str(raw.get("name"), "part name"),
            require_int(raw.get("bytes"), "part bytes"),
            require_sha256(raw.get("sha256"), "part sha256"),
        )


@dataclass(frozen=True, slots=True)
class ContentRecord:
    path: RepositoryPath
    mode: str
    chunk: int
    chunks: int
    file_bytes: int
    sha256: str
    data: bytes

    def to_dict(self) -> dict[str, object]:
        return {
            "record": "content",
            "path": str(self.path),
            "mode": self.mode,
            "chunk": self.chunk,
            "chunks": self.chunks,
            "file_bytes": self.file_bytes,
            "sha256": self.sha256,
            "data": base64.b64encode(self.data).decode("ascii"),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> Self:
        require_fields(
            raw,
            {"record", "path", "mode", "chunk", "chunks", "file_bytes", "sha256", "data"},
            "content record",
        )
        try:
            data = base64.b64decode(require_str(raw.get("data"), "record data"), validate=True)
        except (binascii.Error, ValueError) as exc:
            raise FormatError("invalid base64 record data") from exc
        return cls(
            RepositoryPath.parse(raw.get("path")),
            require_str(raw.get("mode"), "record mode"),
            require_int(raw.get("chunk"), "record chunk", 1),
            require_int(raw.get("chunks"), "record chunks", 1),
            require_int(raw.get("file_bytes"), "record file_bytes"),
            require_sha256(raw.get("sha256"), "record sha256"),
            data,
        )


@dataclass(frozen=True, slots=True)
class GitlinkRecord:
    path: RepositoryPath
    mode: str
    commit: str

    def to_dict(self) -> dict[str, object]:
        return {
            "record": "gitlink",
            "path": str(self.path),
            "mode": self.mode,
            "commit": self.commit,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> Self:
        require_fields(raw, {"record", "path", "mode", "commit"}, "gitlink record")
        return cls(
            RepositoryPath.parse(raw.get("path")),
            require_str(raw.get("mode"), "record mode"),
            require_oid(raw.get("commit"), "gitlink commit"),
        )


BundleRecord = ContentRecord | GitlinkRecord


@dataclass(frozen=True, slots=True)
class Manifest:
    bundle_id: str
    repository: RepositoryMetadata
    includes: tuple[str, ...]
    excludes: tuple[str, ...]
    entries: tuple[ManifestEntry, ...]
    parts: tuple[PartInfo, ...]
    source_entries: int

    def payload_dict(self) -> dict[str, object]:
        payload = sum(e.size for e in self.entries if e.kind is not EntryType.GITLINK)
        return {
            "format": FORMAT,
            "version": VERSION,
            "bundle_id": self.bundle_id,
            "repository": self.repository.to_dict(),
            "selection": {
                "include": list(self.includes),
                "exclude": list(self.excludes),
                "complete": not self.includes and not self.excludes,
            },
            "entries": [e.to_dict() for e in self.entries],
            "parts": [p.to_dict() for p in self.parts],
            "summary": {
                "source_entries": self.source_entries,
                "bundled_entries": len(self.entries),
                "omitted_entries": self.source_entries - len(self.entries),
                "payload_bytes": payload,
            },
        }

    def to_dict(self) -> dict[str, object]:
        out = self.payload_dict()
        out["manifest_sha256"] = sha256_bytes(canonical_json(out))
        return out

    @classmethod
    def from_dict(cls, raw: object) -> Self:
        require(isinstance(raw, dict), "manifest root must be an object")
        raw = cast(dict[str, object], raw)
        require_fields(
            raw,
            {
                "format",
                "version",
                "bundle_id",
                "repository",
                "selection",
                "entries",
                "parts",
                "summary",
                "manifest_sha256",
            },
            "manifest",
        )
        require(
            raw.get("format") == FORMAT and raw.get("version") == VERSION,
            "unsupported bundle format or version",
        )
        expected = require_sha256(raw.get("manifest_sha256"), "manifest_sha256")
        unsigned = dict(raw)
        unsigned.pop("manifest_sha256", None)
        require(
            sha256_bytes(canonical_json(unsigned)) == expected,
            "manifest SHA-256 mismatch",
            IntegrityError,
        )
        bundle_id = require_str(raw.get("bundle_id"), "bundle_id")
        require(bool(bundle_id), "bundle_id must not be empty")
        selection = require_mapping(raw.get("selection"), "selection")
        summary = require_mapping(raw.get("summary"), "summary")
        include_raw = require_array(selection.get("include", []), "selection.include")
        exclude_raw = require_array(selection.get("exclude", []), "selection.exclude")
        includes = tuple(require_str(x, "include pattern") for x in include_raw)
        excludes = tuple(require_str(x, "exclude pattern") for x in exclude_raw)
        for p in includes + excludes:
            pattern_matches("x", p)
        entries_raw = require_array(raw.get("entries"), "entries")
        parts_raw = require_array(raw.get("parts"), "parts")
        entries = tuple(ManifestEntry.from_dict(x) for x in entries_raw)
        parts = tuple(PartInfo.from_dict(x) for x in parts_raw)
        paths = [str(x.path) for x in entries]
        require(len(paths) == len(set(paths)), "duplicate entry paths")
        for path in paths:
            components = PurePosixPath(path).parts
            for i in range(1, len(components)):
                require(
                    "/".join(components[:i]) not in set(paths), "file/descendant path collision"
                )
        require(
            [p.number for p in parts] == list(range(1, len(parts) + 1)),
            "part numbering must be contiguous",
        )
        source = require_int(summary.get("source_entries"), "summary.source_entries")
        require(
            summary.get("bundled_entries") == len(entries)
            and summary.get("omitted_entries") == source - len(entries),
            "manifest entry counts are inconsistent",
        )
        return cls(
            bundle_id,
            RepositoryMetadata.from_dict(raw.get("repository")),
            includes,
            excludes,
            entries,
            parts,
            source,
        )


class Repository(Protocol):
    def index_entries(self) -> tuple[GitEntry, ...]: ...
    def read_blob(self, oid: str) -> bytes: ...
    def metadata(self) -> RepositoryMetadata: ...


class GitRepository:
    def __init__(self, path: Path):
        self.path = path

    def _git(self, *args: str, check: bool = True) -> bytes:
        proc = subprocess.run(["git", "-C", str(self.path), *args], capture_output=True)
        if check and proc.returncode:
            raise RepositoryError(
                proc.stderr.decode("utf-8", "replace").strip() or "git command failed"
            )
        return proc.stdout

    def validate(self) -> None:
        if self._git("rev-parse", "--is-inside-work-tree", check=False).strip() != b"true":
            raise RepositoryError(f"not a Git repository: {self.path}")

    def index_entries(self) -> tuple[GitEntry, ...]:
        self.validate()
        out = []
        for rec in self._git("ls-files", "-s", "-z").split(b"\0"):
            if not rec:
                continue
            meta, path_raw = rec.split(b"\t", 1)
            mode, oid, stage = meta.split(b" ", 2)
            if stage != b"0":
                raise RepositoryError("index contains unresolved merge stages")
            out.append(
                GitEntry(
                    RepositoryPath.parse(path_raw.decode("utf-8", "surrogateescape")),
                    mode.decode(),
                    oid.decode(),
                )
            )
        return tuple(sorted(out, key=lambda x: str(x.path)))

    def read_blob(self, oid: str) -> bytes:
        return self._git("cat-file", "blob", oid)

    def metadata(self) -> RepositoryMetadata:
        branch = (
            self._git("symbolic-ref", "--quiet", "--short", "HEAD", check=False).decode().strip()
            or None
        )
        commit = self._git("rev-parse", "--verify", "HEAD", check=False).decode().strip() or None
        if commit is not None and not (len(commit) in (40, 64) and all(c in HEX for c in commit)):
            commit = None
        dirty = bool(self._git("status", "--porcelain=v1", "-z", check=False))
        return RepositoryMetadata(branch, commit, dirty)


class PartWriter:
    def __init__(self, directory: Path, prefix: str, max_bytes: int, bundle_id: str):
        require_int(max_bytes, "part bytes", MIN_PART_BYTES)
        self.directory = directory
        self.prefix = prefix
        self.max_bytes = max_bytes
        self.bundle_id = bundle_id
        self._number = 0
        self._fh = None
        self._path = None
        self._size = 0
        self._parts = []

    def _open(self) -> None:
        self._number += 1
        self._path = self.directory / f"{self.prefix}.part-{self._number:04d}.jsonl"
        self._fh = self._path.open("xb")
        header = canonical_json(
            {
                "record": "header",
                "format": FORMAT,
                "version": VERSION,
                "bundle_id": self.bundle_id,
                "part": self._number,
            }
        )
        require(len(header) <= self.max_bytes, "part size too small for header")
        self._fh.write(header)
        self._size = len(header)

    def _close(self) -> None:
        if self._fh is None:
            return
        self._fh.flush()
        os.fsync(self._fh.fileno())
        self._fh.close()
        assert self._path
        self._parts.append(
            PartInfo(
                self._number, self._path.name, self._path.stat().st_size, sha256_file(self._path)
            )
        )
        self._fh = None

    def write(self, record: BundleRecord) -> None:
        line = canonical_json(record.to_dict())
        require(len(line) <= self.max_bytes, "one encoded record exceeds the part-size limit")
        if self._fh is None:
            self._open()
        if self._size + len(line) > self.max_bytes:
            self._close()
            self._open()
        assert self._fh
        self._fh.write(line)
        self._size += len(line)

    def close(self) -> tuple[PartInfo, ...]:
        self._close()
        return tuple(self._parts)


class PartReader:
    def __init__(self, paths: Iterable[Path], bundle_id: str):
        self.paths = tuple(paths)
        self.bundle_id = bundle_id

    def records(self) -> Iterator[BundleRecord]:
        for number, path in enumerate(self.paths, 1):
            try:
                with path.open("rb") as fh:
                    header = strict_json_loads(fh.readline())
                    require(
                        header
                        == {
                            "bundle_id": self.bundle_id,
                            "format": FORMAT,
                            "part": number,
                            "record": "header",
                            "version": VERSION,
                        },
                        f"unexpected part header: {path.name}",
                    )
                    for lineno, line in enumerate(fh, 2):
                        try:
                            raw = strict_json_loads(line)
                        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                            raise FormatError(f"invalid JSON in {path.name}:{lineno}") from exc
                        raw = require_mapping(raw, "record")
                        kind = raw.get("record")
                        if kind == "content":
                            yield ContentRecord.from_dict(raw)
                        elif kind == "gitlink":
                            yield GitlinkRecord.from_dict(raw)
                        else:
                            raise FormatError(f"unknown record type: {kind!r}")
            except OSError as exc:
                raise FormatError(f"cannot read part {path}: {exc}") from exc


class ManifestCodec:
    @staticmethod
    def load(path: Path, limits: ResourceLimits | None = None) -> Manifest:
        limits = ResourceLimits() if limits is None else limits
        try:
            size = path.stat().st_size
            require(size <= limits.max_manifest_bytes, "manifest exceeds local size limit")
            raw = strict_json_loads(path.read_bytes())
        except OSError as exc:
            raise FormatError(f"cannot read manifest: {exc}") from exc
        return Manifest.from_dict(raw)

    @staticmethod
    def dump(manifest: Manifest, path: Path) -> None:
        atomic_write(
            path,
            json.dumps(manifest.to_dict(), ensure_ascii=True, sort_keys=True, indent=2).encode(
                "ascii"
            )
            + b"\n",
        )


@dataclass(frozen=True, slots=True)
class CreateOptions:
    repository: Path
    output: Path
    name: str = "bundle"
    part_bytes: int = DEFAULT_PART_BYTES
    chunk_bytes: int = DEFAULT_CHUNK_BYTES
    selection: SelectionPolicy = SelectionPolicy()

    def __post_init__(self) -> None:
        require(bool(self.name) and self.name == Path(self.name).name, "unsafe bundle name")
        require_int(self.part_bytes, "part bytes", MIN_PART_BYTES)
        require_int(self.chunk_bytes, "chunk bytes", MIN_CHUNK_BYTES)


@dataclass(frozen=True, slots=True)
class BundleResult:
    manifest: Path
    parts: tuple[Path, ...]
    bundled_entries: int
    payload_bytes: int

    def to_dict(self) -> dict[str, object]:
        return {
            "status": "ok",
            "manifest": str(self.manifest),
            "parts": [str(x) for x in self.parts],
            "bundled_entries": self.bundled_entries,
            "payload_bytes": self.payload_bytes,
        }


class BundleBuilder:
    """Build into private staging, verify, then atomically publish the directory."""

    def __init__(self, repository: Repository, options: CreateOptions):
        self.repository = repository
        self.options = options

    def build(self) -> BundleResult:
        final = self.options.output
        require(not final.exists(), "output path already exists")
        final.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=f".{final.name}.bundle-repo-", dir=final.parent))
        published = False
        try:
            source = self.repository.index_entries()
            selected = tuple(e for e in source if self.options.selection.matches(e.path))
            bundle_id = uuid.uuid4().hex
            writer = PartWriter(staging, self.options.name, self.options.part_bytes, bundle_id)
            manifest_entries: list[ManifestEntry] = []
            for entry in selected:
                if entry.kind is EntryType.GITLINK:
                    writer.write(GitlinkRecord(entry.path, entry.mode, entry.object_id))
                    manifest_entries.append(
                        ManifestEntry(
                            entry.path, entry.mode, entry.kind, entry.object_id, 0, None, 0
                        )
                    )
                    continue
                data = self.repository.read_blob(entry.object_id)
                digest = sha256_bytes(data)
                chunks = max(
                    1, (len(data) + self.options.chunk_bytes - 1) // self.options.chunk_bytes
                )
                manifest_entries.append(
                    ManifestEntry(
                        entry.path,
                        entry.mode,
                        entry.kind,
                        entry.object_id,
                        len(data),
                        digest,
                        chunks,
                    )
                )
                for i in range(chunks):
                    writer.write(
                        ContentRecord(
                            entry.path,
                            entry.mode,
                            i + 1,
                            chunks,
                            len(data),
                            digest,
                            data[i * self.options.chunk_bytes : (i + 1) * self.options.chunk_bytes],
                        )
                    )
            parts = writer.close()
            manifest = Manifest(
                bundle_id,
                self.repository.metadata(),
                self.options.selection.includes,
                self.options.selection.excludes,
                tuple(manifest_entries),
                parts,
                len(source),
            )
            staged_manifest = staging / f"{self.options.name}.manifest.json"
            ManifestCodec.dump(manifest, staged_manifest)
            BundleVerifier(copy_parts=False).verify(staged_manifest)
            os.replace(staging, final)
            published = True
            manifest_path = final / staged_manifest.name
            return BundleResult(
                manifest_path,
                tuple(final / info.name for info in parts),
                len(manifest_entries),
                sum(e.size for e in manifest_entries),
            )
        finally:
            if not published:
                shutil.rmtree(staging, ignore_errors=True)


@dataclass(frozen=True, slots=True)
class VerifiedBundle:
    manifest_path: Path
    manifest: Manifest
    parts: tuple[Path, ...]
    workspace: Path | None = None

    def close(self) -> None:
        if self.workspace is not None:
            shutil.rmtree(self.workspace, ignore_errors=True)


class VerificationState:
    def __init__(self, manifest: Manifest):
        self.expected = {str(e.path): e for e in manifest.entries}
        self.next = dict.fromkeys(self.expected, 1)
        self.buffers = {
            p: hashlib.sha256() for p, e in self.expected.items() if e.kind is not EntryType.GITLINK
        }
        self.bytes = dict.fromkeys(self.buffers, 0)
        self.gitlinks: set[str] = set()

    def consume(self, record: BundleRecord) -> None:
        path = str(record.path)
        require(
            path in self.expected, f"record references unmanifested path: {path}", IntegrityError
        )
        entry = self.expected[path]
        if isinstance(record, GitlinkRecord):
            require(
                entry.kind is EntryType.GITLINK
                and record.mode == entry.mode
                and record.commit == entry.git_object,
                "inconsistent gitlink record",
                IntegrityError,
            )
            require(path not in self.gitlinks, "duplicate gitlink record", IntegrityError)
            self.gitlinks.add(path)
            return
        require(
            entry.kind is not EntryType.GITLINK,
            "content record supplied for gitlink",
            IntegrityError,
        )
        require(
            record.mode == entry.mode
            and record.chunks == entry.chunks
            and record.file_bytes == entry.size
            and record.sha256 == entry.sha256,
            "content record metadata mismatch",
            IntegrityError,
        )
        require(record.chunk == self.next[path], f"out-of-order chunk for {path}", IntegrityError)
        self.next[path] += 1
        self.buffers[path].update(record.data)
        self.bytes[path] += len(record.data)

    def finish(self) -> None:
        for path, entry in self.expected.items():
            if entry.kind is EntryType.GITLINK:
                require(path in self.gitlinks, f"missing gitlink record: {path}", IntegrityError)
            else:
                require(
                    self.next[path] == entry.chunks + 1,
                    f"chunk-count mismatch: {path}",
                    IntegrityError,
                )
                require(
                    self.bytes[path] == entry.size, f"byte-count mismatch: {path}", IntegrityError
                )
                require(
                    self.buffers[path].hexdigest() == entry.sha256,
                    f"content SHA-256 mismatch: {path}",
                    IntegrityError,
                )


class BundleVerifier:
    """Copy Parts to a private workspace and verify those exact bytes."""

    def __init__(self, limits: ResourceLimits | None = None, *, copy_parts: bool = True):
        self.limits = ResourceLimits() if limits is None else limits
        self.copy_parts = copy_parts

    def verify(self, manifest_path: Path) -> VerifiedBundle:
        manifest = ManifestCodec.load(manifest_path, self.limits)
        require(
            len(manifest.parts) <= self.limits.max_parts, "bundle exceeds local part-count limit"
        )
        require(
            len(manifest.entries) <= self.limits.max_entries,
            "bundle exceeds local entry-count limit",
        )
        require(
            sum(e.size for e in manifest.entries) <= self.limits.max_payload_bytes,
            "bundle exceeds local payload limit",
        )
        workspace: Path | None = None
        root = manifest_path.parent
        if self.copy_parts:
            workspace = Path(
                tempfile.mkdtemp(prefix=".bundle-repo-verify-", dir=manifest_path.parent.parent)
            )
            root = workspace
        parts: list[Path] = []
        try:
            for info in manifest.parts:
                source = manifest_path.parent / info.name
                require(source.is_file(), f"missing bundle part: {info.name}", IntegrityError)
                target = root / info.name
                if self.copy_parts:
                    shutil.copyfile(source, target)
                else:
                    target = source
                require(
                    target.stat().st_size == info.size,
                    f"part byte-count mismatch: {info.name}",
                    IntegrityError,
                )
                require(
                    sha256_file(target) == info.sha256,
                    f"part SHA-256 mismatch: {info.name}",
                    IntegrityError,
                )
                parts.append(target)
            state = VerificationState(manifest)
            for record in PartReader(parts, manifest.bundle_id).records():
                state.consume(record)
            state.finish()
            return VerifiedBundle(manifest_path, manifest, tuple(parts), workspace)
        except Exception:
            if workspace is not None:
                shutil.rmtree(workspace, ignore_errors=True)
            raise


def _publish_tree(staging: Path, destination: Path, force: bool) -> None:
    """Publish one whole tree, rolling back the previous destination on failure."""
    if destination.exists() or destination.is_symlink():
        require(force, "destination exists; use --force", ReconstructionError)
    destination.parent.mkdir(parents=True, exist_ok=True)
    backup = destination.parent / f".{destination.name}.bundle-repo-backup-{uuid.uuid4().hex}"
    had_old = destination.exists() or destination.is_symlink()
    try:
        if had_old:
            os.replace(destination, backup)
        try:
            os.replace(staging, destination)
        except Exception:
            if had_old and backup.exists():
                os.replace(backup, destination)
            raise
        if backup.exists():
            if backup.is_dir() and not backup.is_symlink():
                shutil.rmtree(backup)
            else:
                backup.unlink()
    except OSError as exc:
        raise ReconstructionError(f"transactional publication failed: {exc}") from exc


class BundleReconstructor:
    def reconstruct(self, bundle: VerifiedBundle, destination: Path, force: bool = False) -> None:
        staging = Path(
            tempfile.mkdtemp(
                prefix=f".{destination.name}.bundle-repo-tree-", dir=destination.parent
            )
        )
        handles: dict[str, BinaryIO] = {}
        published = False
        try:
            expected = {str(e.path): e for e in bundle.manifest.entries}
            for rec in PartReader(bundle.parts, bundle.manifest.bundle_id).records():
                target = staging.joinpath(*rec.path.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                if isinstance(rec, GitlinkRecord):
                    target.mkdir()
                    (target / ".gitlink-commit").write_text(rec.commit + "\n")
                    continue
                fh = handles.get(str(rec.path))
                if fh is None:
                    fh = target.open("wb")
                    handles[str(rec.path)] = fh
                fh.write(rec.data)
            for fh in handles.values():
                fh.close()
            handles.clear()
            for path, entry in expected.items():
                source = staging.joinpath(*entry.path.parts)
                if entry.kind is EntryType.GITLINK:
                    continue
                require(
                    source.stat().st_size == entry.size and sha256_file(source) == entry.sha256,
                    f"reconstructed content failed verification: {path}",
                    ReconstructionError,
                )
                if entry.kind is EntryType.SYMLINK:
                    link = source.read_bytes().decode("utf-8", "surrogateescape")
                    source.unlink()
                    os.symlink(link, source)
                elif entry.mode == "100755":
                    source.chmod(source.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            current = destination.parent
            require(
                not current.is_symlink(),
                f"destination parent is a symlink: {current}",
                ReconstructionError,
            )
            _publish_tree(staging, destination, force)
            published = True
        finally:
            for fh in handles.values():
                fh.close()
            if not published:
                shutil.rmtree(staging, ignore_errors=True)
            bundle.close()


def load_patterns(values: list[str] | None, files: list[str] | None) -> tuple[str, ...]:
    result = list(values or [])
    for filename in files or []:
        try:
            lines = Path(filename).read_text("utf-8").splitlines()
        except OSError as exc:
            raise BundleError(f"cannot read pattern file {filename!r}: {exc}") from exc
        result.extend(
            line.strip() for line in lines if line.strip() and not line.lstrip().startswith("#")
        )
    for p in result:
        pattern_matches("x", p)
    return tuple(result)


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bundle-repo",
        description="Create, verify, and reconstruct hardened Git repository bundles.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    c = sub.add_parser("create")
    c.add_argument("repository", type=Path)
    c.add_argument("-o", "--output", type=Path, required=True)
    c.add_argument("-n", "--name", default="bundle")
    c.add_argument("--part-bytes", type=int, default=DEFAULT_PART_BYTES)
    c.add_argument("--chunk-bytes", type=int, default=DEFAULT_CHUNK_BYTES)
    c.add_argument("--include", action="append")
    c.add_argument("--exclude", action="append")
    c.add_argument("--include-from", action="append")
    c.add_argument("--exclude-from", action="append")
    c.add_argument("--json", action="store_true")
    v = sub.add_parser("verify")
    v.add_argument("manifest", type=Path)
    v.add_argument("--json", action="store_true")
    r = sub.add_parser("reconstruct")
    r.add_argument("manifest", type=Path)
    r.add_argument("destination", type=Path)
    r.add_argument("--force", action="store_true")
    r.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = make_parser().parse_args(argv)
    try:
        if args.command == "create":
            policy = SelectionPolicy(
                load_patterns(args.include, args.include_from),
                load_patterns(args.exclude, args.exclude_from),
            )
            result = BundleBuilder(
                GitRepository(args.repository),
                CreateOptions(
                    args.repository,
                    args.output,
                    args.name,
                    args.part_bytes,
                    args.chunk_bytes,
                    policy,
                ),
            ).build()
            print(json.dumps(result.to_dict(), indent=2))
        elif args.command == "verify":
            bundle = BundleVerifier().verify(args.manifest)
            print(
                json.dumps(
                    {
                        "status": "ok",
                        "manifest": str(bundle.manifest_path),
                        "entries": len(bundle.manifest.entries),
                        "parts": len(bundle.parts),
                    },
                    indent=2,
                )
            )
        else:
            bundle = BundleVerifier().verify(args.manifest)
            BundleReconstructor().reconstruct(bundle, args.destination, args.force)
            print(
                json.dumps(
                    {
                        "status": "ok",
                        "destination": str(args.destination),
                        "entries": len(bundle.manifest.entries),
                    },
                    indent=2,
                )
            )
        return 0
    except BundleError as exc:
        if getattr(args, "json", False):
            print(
                json.dumps(
                    {
                        "status": "error",
                        "error": type(exc).__name__,
                        "message": str(exc),
                        "exit_code": exc.exit_code,
                    }
                ),
                file=sys.stderr,
            )
        else:
            print(f"error: {exc}", file=sys.stderr)
        return exc.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
