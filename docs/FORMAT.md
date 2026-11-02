# Bundle-Repo Format Version 1

## Status of This Memo

This document specifies version 1 of the `bundle-repo` interchange format. The key words **MUST**, **MUST NOT**, **REQUIRED**, **SHALL**, **SHALL NOT**, **SHOULD**, **SHOULD NOT**, **RECOMMENDED**, **NOT RECOMMENDED**, **MAY**, and **OPTIONAL** are to be interpreted as described by RFC 2119 and RFC 8174 when, and only when, they appear in all capitals.

## 1. Introduction

`bundle-repo` serializes a snapshot of the Git index into an audit-friendly manifest plus numbered JSON Lines part files. Version 1 is intentionally independent of earlier repository-bundle formats.

The format is designed for lossless reconstruction of regular files, executable files, symbolic links, and Gitlinks represented by the Git index. It does not serialize `.git` metadata, untracked files, ignored files, or submodule working-tree contents.

## 2. Conventions

All JSON objects MUST be valid JSON. Manifest files MUST be UTF-8. Producers defined by this specification emit ASCII-only JSON by escaping non-ASCII characters; consumers MUST accept valid UTF-8 JSON.

A SHA-256 value is exactly 64 lowercase hexadecimal characters. A Git object ID is exactly 40 or 64 lowercase hexadecimal characters.

Repository paths use `/` separators regardless of host operating system.

## 3. Bundle Layout

A bundle consists of exactly one manifest and zero or more numbered part files in one directory.

A producer using bundle name `audit` emits:

```text
audit.manifest.json
audit.part-0001.jsonl
audit.part-0002.jsonl
...
```

Part numbering starts at 1 and MUST be contiguous. The authoritative part names, lengths, ordering, and SHA-256 digests are declared by the manifest.

An empty selected snapshot MAY contain zero part files.

## 4. Canonical JSON

Whenever this specification hashes a JSON value, it MUST be serialized using these rules:

1. object member keys sorted lexicographically;
2. no insignificant whitespace;
3. separators exactly `,` and `:`;
4. non-ASCII characters escaped;
5. exactly one LF byte (`0x0A`) appended.

Python-equivalent definition:

```python
(json.dumps(value, ensure_ascii=True, sort_keys=True,
            separators=(",", ":")) + "\n").encode("ascii")
```

## 5. Manifest

The manifest is a JSON object with these REQUIRED members:

- `format`: string, MUST equal `bundle-repo`.
- `version`: integer, MUST equal `1`.
- `bundle_id`: non-empty opaque string identifying this bundle.
- `repository`: repository metadata object.
- `selection`: selection metadata object.
- `entries`: ordered array of entry objects.
- `parts`: ordered array of part objects.
- `summary`: summary object.
- `manifest_sha256`: SHA-256 digest.

### 5.1 Manifest Self-Digest

To calculate `manifest_sha256`, the producer MUST remove `manifest_sha256` from the manifest, serialize the remaining object using Canonical JSON, and calculate SHA-256 over those bytes.

A consumer MUST verify this digest before trusting any manifest metadata.

### 5.2 Repository Object

`repository` contains:

- `branch`: current symbolic branch name or `null` for detached HEAD;
- `commit`: Git object ID of HEAD, or `null` for an unborn repository;
- `dirty`: boolean indicating whether `git status --porcelain=v1` produced output at creation time.

`dirty` is informational. Bundle contents come from the Git index and MUST NOT be inferred from the worktree.

### 5.3 Selection Object

`selection` contains:

- `include`: array of include patterns;
- `exclude`: array of exclude patterns;
- `complete`: boolean, true iff both pattern arrays are empty.

A path is selected when it matches an include pattern, or there are no include patterns, and it does not match any exclude pattern. Exclusion takes precedence.

A pattern ending in `/` matches that path and its descendants. A pattern containing `/` matches the whole repository-relative path using shell-style glob semantics. A pattern without `/` matches any path component.

Absolute patterns, backslashes, NUL, and `..` components MUST be rejected.

### 5.4 Entry Object

Every entry contains:

- `path`: safe repository-relative POSIX path;
- `mode`: one of `100644`, `100755`, `120000`, `160000`;
- `type`: `file`, `symlink`, or `gitlink`;
- `git_object`: Git object ID recorded by the index;
- `bytes`: decoded payload length;
- `sha256`: decoded payload SHA-256, or `null` for a gitlink;
- `chunks`: number of content records, or zero for a gitlink.

Mode/type relationships are normative:

| Mode | Type |
|---|---|
| `100644` | `file` |
| `100755` | `file` |
| `120000` | `symlink` |
| `160000` | `gitlink` |

Non-gitlink entries MUST have `chunks >= 1`. Gitlinks MUST have `bytes = 0`, `sha256 = null`, and `chunks = 0`.

Entry paths MUST be unique. No entry path may be an ancestor of another entry path.

### 5.5 Part Object

Every part contains:

- `number`: one-based contiguous integer;
- `name`: basename-only file name;
- `bytes`: exact byte size of the part;
- `sha256`: SHA-256 over the complete part file.

### 5.6 Summary Object

`summary` contains:

- `source_entries`: number of Git index stage-0 entries before selection;
- `bundled_entries`: number of entries in the manifest;
- `omitted_entries`: `source_entries - bundled_entries`;
- `payload_bytes`: sum of `bytes` for all non-gitlink entries.

Summary values are redundant integrity/diagnostic metadata and MUST be internally consistent.

## 6. Repository Path Safety

A repository path MUST:

- be non-empty;
- be relative;
- use `/` separators;
- contain no NUL;
- contain no backslash;
- contain no `.` or `..` path component.

Consumers MUST treat paths as untrusted until these checks succeed. Reconstruction MUST additionally ensure that no existing destination ancestor traversed for an entry is a symbolic link.

## 7. Part Files

Each part is JSON Lines. Every line is one complete JSON object terminated by LF.

The first line MUST be a header object:

```json
{"bundle_id":"...","format":"bundle-repo","part":1,"record":"header","version":1}
```

The `bundle_id`, format, version, and one-based part number MUST match the manifest and physical sequence.

Subsequent lines contain records.

## 8. Content Record

A regular file or symlink payload is represented by one or more `content` records:

```json
{
  "record": "content",
  "path": "src/main.py",
  "mode": "100644",
  "chunk": 1,
  "chunks": 1,
  "file_bytes": 10,
  "sha256": "...",
  "data": "...base64..."
}
```

`data` MUST be strict Base64. After Base64 decoding, records for one path MUST occur in strictly increasing chunk order beginning at 1. The concatenated decoded bytes MUST have the manifest-declared byte count and SHA-256 digest.

The record `mode`, `chunks`, `file_bytes`, and `sha256` MUST equal the corresponding manifest values.

For a symlink, the decoded payload is the raw link-target bytes stored by Git. During reconstruction those bytes are decoded using UTF-8 with surrogate escape semantics and used as the symbolic-link target.

## 9. Gitlink Record

A Gitlink is represented by exactly one record:

```json
{
  "record": "gitlink",
  "path": "vendor/project",
  "mode": "160000",
  "commit": "...git-object-id..."
}
```

`commit` MUST equal the manifest `git_object` for that path.

Because Git index data stores only the Gitlink commit ID and not the submodule working tree, reconstruction represents a Gitlink as a directory containing `.gitlink-commit` with the commit ID followed by LF.

## 10. Verification

A conforming verifier MUST, before reporting success:

1. parse and validate the manifest schema;
2. verify `manifest_sha256`;
3. validate all repository paths and entry topology;
4. validate contiguous part numbering and safe part names;
5. verify existence, byte size, and SHA-256 of every declared part;
6. verify every part header;
7. reject unknown record types;
8. strictly decode Base64 payloads;
9. reject records referencing undeclared paths;
10. verify record metadata against manifest metadata;
11. enforce chunk order and exact chunk counts;
12. verify reconstructed byte counts and content SHA-256 values;
13. verify every Gitlink record and reject duplicates or omissions.

A verifier MUST fail closed on an unknown format version.

## 11. Reconstruction

Reconstruction MUST only operate on a bundle that has successfully completed verification.

A reconstructor MUST stage decoded content outside the requested destination tree or otherwise ensure that complete record verification occurs before destination files are replaced.

Before moving any entry to its destination, every existing ancestor below the destination root MUST be checked and MUST NOT be a symbolic link.

Mode `100755` MUST reconstruct as executable. Mode `120000` MUST reconstruct as a symbolic link. Mode `160000` MUST use the Gitlink representation described in Section 9.

A non-empty destination MUST NOT be modified unless the caller has explicitly requested force behavior.

## 12. Limits and Denial-of-Service Considerations

The format itself does not prescribe maximum manifest size, entry count, part count, path length, payload size, or decompressed size because payloads are not compressed. Implementations MAY enforce documented resource limits. Implementations MUST NOT silently truncate verified data.

A part writer MUST reject a single encoded record that cannot fit within its configured maximum part size.

## 13. Security Considerations

The SHA-256 fields provide integrity detection, not authenticity. An attacker capable of replacing an entire bundle can recompute all unkeyed hashes. Applications requiring provenance or authenticity SHOULD authenticate the manifest externally, for example with a detached digital signature.

Consumers MUST NOT trust manifest paths, part names, Base64 payloads, declared lengths, hashes, modes, or record ordering before validation.

Symlink ancestor checks are REQUIRED to prevent destination escape during reconstruction.

Git object IDs identify source index objects but are not substitutes for SHA-256 integrity of bundled payload bytes.

## 14. Versioning

Consumers implementing this specification MUST accept only `format = "bundle-repo"` and `version = 1`. Future incompatible formats MUST increment `version`. Version 1 readers MUST fail closed on later versions they do not implement.
