from __future__ import annotations

import bundle_repo as br

OID = "a" * 40


def entry(path="a.txt", mode="100644", data=b"hello"):
    kind = (
        br.EntryType.SYMLINK
        if mode == "120000"
        else br.EntryType.GITLINK
        if mode == "160000"
        else br.EntryType.FILE
    )
    return br.ManifestEntry(
        br.RepositoryPath.parse(path),
        mode,
        kind,
        OID,
        0 if kind is br.EntryType.GITLINK else len(data),
        None if kind is br.EntryType.GITLINK else br.sha256_bytes(data),
        0 if kind is br.EntryType.GITLINK else 1,
    )


def manifest(entries=None, parts=()):
    return br.Manifest(
        "test-bundle",
        br.RepositoryMetadata("main", OID, False),
        (),
        (),
        tuple(entries or [entry()]),
        tuple(parts),
        len(entries or [entry()]),
    )


def content(path="a.txt", data=b"hello", chunk=1, chunks=1):
    return br.ContentRecord(
        br.RepositoryPath.parse(path),
        "100644",
        chunk,
        chunks,
        len(data),
        br.sha256_bytes(data),
        data,
    )
