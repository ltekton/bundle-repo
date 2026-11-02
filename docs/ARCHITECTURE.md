# bundle-repo Architecture

**Status:** Normative design  
**Runtime artifact:** `bundle_repo.py`, Python 3.14+, standard library only

## Context

The source Repository and Git object database are trusted only as input to creation. Bundle files and reconstruction Destinations are untrusted. The CLI is an adapter around typed application services.

## Logical Components in the Single Production File

1. constants and exit codes;
2. structured exception hierarchy;
3. `ResourceLimits`;
4. strict JSON and canonical JSON;
5. path and schema validation;
6. immutable domain dataclasses;
7. `SelectionPolicy`;
8. `GitRepository`;
9. `PartWriter` and `PartReader`;
10. `ManifestCodec`;
11. `BundleBuilder`;
12. `VerificationState` and `VerifierSink`;
13. `BundleVerifier`;
14. `StagingSink` and `BundleReconstructor`;
15. transactional publication;
16. result/option dataclasses;
17. argparse and `main`.

Raw dictionaries are I/O representations only. Untrusted strings become `RepositoryPath` objects exactly once. Reconstruction accepts a `VerifiedBundle`, not a raw Manifest.

## Trust Transitions

```text
untrusted Git output / JSON / filesystem
                 |
          strict parsing
                 v
       immutable domain objects
                 |
          complete verify
                 v
          VerifiedBundle
                 |
    verified private staging tree
                 v
       transactional publication
```

## Security Invariants

- **BR-SI-001 Path containment:** Every Snapshot Entry remains below its intended root.
- **BR-SI-002 Topology uniqueness:** Paths are unique; no file/descendant or portable case-fold collision is allowed.
- **BR-SI-003 Verify before publish:** Neither bundles nor reconstructed trees are published before verification.
- **BR-SI-004 Complete integrity chain:** Manifest, Parts, records, metadata, bytes, and hashes form one checked chain.
- **BR-SI-005 Data-only interpretation:** Bundle values cannot select executable code paths beyond known record variants.
- **BR-SI-006 Strict parsing:** Duplicate keys, unknown fields, bad types, malformed Base64, and trailing data fail closed.
- **BR-SI-007 Resource bounds:** Consumer-owned limits bound manifests, records, Parts, entries, paths, and payload.
- **BR-SI-008 Symlink safety:** No Destination ancestor used for publication may be a symlink.
- **BR-SI-009 TOCTOU resistance:** Reconstruction consumes private copies that are the exact bytes verified.
- **BR-SI-010 Failure cleanup:** Failures remove private work and preserve or restore the prior visible tree.
- **BR-SI-011 Deterministic authority:** Canonical JSON and stable entry ordering define hashes and comparisons.
- **BR-SI-012 Force is not unsafe:** Force changes replacement policy only.

## Create Workflow

```text
validate repository and options
capture ordered stage-0 index
apply selection policy
read blobs from Git object database
write Manifest and Parts into private sibling staging
verify staged bundle from disk
fsync files/directories where supported
atomically publish staged bundle directory
return CreateResult
```

## Verify Workflow

```text
bound and strict-read Manifest
validate exact schemas and cross-field rules
copy declared Parts to private verifier workspace
verify copied Part size/hash/header
stream records through VerificationState and optional VerifierSink
finish completeness/hash checks
return VerifiedBundle referencing private authoritative copies
```

Standalone verification uses `NullSink`. Reconstruction uses `StagingSink`, so the same verifier owns record semantics.

## Reconstruct Workflow

```text
create private workspace beside Destination
copy and verify authoritative Parts
stream verified bytes to staging tree
apply executable, symlink, and Gitlink semantics
post-verify staged tree
check Destination ancestors
publish whole tree, backing up old Destination when forced
remove backup on success; rollback on failure
```

## ADRs

- **BR-ADR-001 Git index authority:** v1 captures stage-0 Git index state, not an arbitrary filesystem tree.
- **BR-ADR-002 Single runtime module:** deployment is one standard-library file; tests/docs remain decomposed.
- **BR-ADR-003 JSON + JSONL + Base64:** selected for text-safe transport and inspectability.
- **BR-ADR-004 SHA-256 integrity, no authenticity:** signatures remain external to v1.
- **BR-ADR-005 Exact schemas:** extensibility requires a format version change, not ignored fields.
- **BR-ADR-006 Whole-tree publication:** reconstruction never merges an incomplete staging tree into Destination.

## Test Architecture

- L1 pure unit;
- L2 schema and cross-field validation;
- L3 golden wire-format vectors;
- L4 Git/filesystem/CLI integration;
- L5 transactional failure injection;
- L6 Hypothesis properties;
- L7 adversarial security corpus.

Coverage is necessary but not sufficient. `scripts/traceability.py` joins normative requirements, explicit source references, and collected pytest requirement markers.
