# bundle-repo Product Definition

**Status:** Normative design baseline  
**Product:** bundle-repo  
**CLI:** `bundle-repo`

## Vision

`bundle-repo` creates deterministic, text-safe bundles from the stage-0 Git index, verifies every integrity relationship, and reconstructs a complete filesystem tree without trusting bundle metadata.

## Principles

- **BR-P-001 Data-only boundary.** A bundle is data. Records MUST NOT trigger executable behavior.
- **BR-P-002 Losslessness.** Regular files, executable mode, symlink targets, arbitrary bytes, Unicode paths, empty files, and Gitlink commit IDs MUST round-trip.
- **BR-P-003 Honest snapshot semantics.** The Git index and object database are authoritative. The worktree is not payload authority.
- **BR-P-004 Verify before publish.** Created bundles and reconstructed trees MUST be fully verified before final publication.
- **BR-P-005 Safe reconstruction.** Path traversal, topology collisions, symlink escapes, and partial publication MUST be prevented.
- **BR-P-006 Determinism.** Given identical selected index state and options, ordering and canonical encodings MUST be deterministic. Bundle IDs may differ.
- **BR-P-007 Bounded streaming.** Consumers MUST enforce local resource limits.
- **BR-P-008 Strict parsing.** Duplicate keys, unknown fields, malformed encodings, and inconsistent metadata MUST fail closed.
- **BR-P-009 Consumer independence.** A verifier MUST NOT need the source repository.
- **BR-P-010 Clear authority.** The manifest and declared Parts are authoritative; human reports are derived.

## Goals

- **BR-G-001** Create a multipart bundle from the selected stage-0 Git index.
- **BR-G-002** Verify structure, hashes, metadata, ordering, and completeness independently.
- **BR-G-003** Reconstruct only from content that passed verification.
- **BR-G-004** Support regular files, executables, symlinks, Gitlinks, binary data, Unicode, and empty files.
- **BR-G-005** Keep production as one Python 3.14+ standard-library file.
- **BR-G-006** Provide stable human and JSON error behavior.
- **BR-G-007** Provide traceable requirements, tests, and CI quality gates.

## Non-goals for Version 1

- **BR-NG-001** Git history, refs, remotes, hooks, or `.git/` contents.
- **BR-NG-002** Untracked or ignored files that are not in the index.
- **BR-NG-003** Submodule working-tree contents. Gitlinks preserve only the indexed commit ID.
- **BR-NG-004** Compression, encryption, signatures, or authenticity. SHA-256 provides integrity detection only.
- **BR-NG-005** Legacy bundle compatibility.
- **BR-NG-006** Incremental, delta, or remote bundles.
- **BR-NG-007** ACL, xattr, ownership, hard-link, or sparse-file preservation.

## Version 1 Requirements

### Create

- **BR-REQ-CREATE-001** Create MUST snapshot stage-0 index entries and reject unresolved stages.
- **BR-REQ-CREATE-002** Payload bytes MUST come from indexed Git objects.
- **BR-REQ-CREATE-003** Include/exclude selection MUST be recorded; exclusion wins.
- **BR-REQ-CREATE-004** Output MUST be staged, verified, and then published.
- **BR-REQ-CREATE-005** A record that cannot fit in one Part MUST be rejected.

### Verify

- **BR-REQ-VERIFY-001** Verification MUST be independent of the source repository.
- **BR-REQ-VERIFY-002** Verification MUST fail closed for unknown format versions or fields.
- **BR-REQ-VERIFY-003** Verification MUST validate the complete manifest-to-record integrity chain.
- **BR-REQ-VERIFY-004** Consumer-owned resource limits MUST apply before allocation or decoding where practical.

### Reconstruct

- **BR-REQ-RECON-001** Reconstruction MUST use verified authoritative Part copies.
- **BR-REQ-RECON-002** A complete private staging tree MUST be verified before publication.
- **BR-REQ-RECON-003** Publication MUST be whole-tree and rollback-aware.
- **BR-REQ-RECON-004** `--force` MUST NOT weaken path, integrity, or symlink safety.

### CLI

- **BR-REQ-CLI-001** Commands are `create`, `verify`, and `reconstruct`.
- **BR-REQ-CLI-002** Domain failures MUST return stable nonzero exit codes and concise stderr.
- **BR-REQ-CLI-003** `--json` SHOULD provide structured machine-readable results and errors.
