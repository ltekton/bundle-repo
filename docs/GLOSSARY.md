# Ubiquitous Language

**Status:** Normative. Terms in documentation, source, tests, CLI help, and errors SHOULD use these meanings.

- **Repository:** The Git repository supplied to `create`.
- **Git Index Snapshot:** The ordered stage-0 index entries captured by `git ls-files -s -z`.
- **Snapshot Entry:** One regular file, executable file, symbolic link, or Gitlink in the selected index snapshot.
- **Selection Policy:** Include/exclude patterns applied to Snapshot Entries. Exclusion has precedence.
- **Gitlink:** Index mode `160000`, carrying an indexed commit ID but no submodule working-tree payload.
- **Bundle:** One Manifest and its ordered Parts.
- **Manifest:** The authoritative JSON metadata document describing repository metadata, selection, entries, Parts, and integrity values.
- **Part:** A numbered JSON Lines file authenticated by its Manifest declaration.
- **Part Header:** The first record of a Part, binding format, version, Bundle ID, and Part number.
- **Bundle Record:** A Content Record or Gitlink Record after the Part Header.
- **Content Record:** One strictly Base64-encoded chunk plus metadata binding it to one Manifest Entry.
- **Payload:** Concatenated decoded bytes of a non-Gitlink Snapshot Entry.
- **Structural Validity:** Conformance to exact schemas, types, paths, topology, and ordering rules.
- **Integrity Validity:** Agreement of hashes, byte counts, record metadata, chunks, and Parts with the Manifest.
- **Verified Bundle:** A capability object produced only after complete Structural and Integrity Validation.
- **Authoritative Part Copy:** A private copy verified and then reused for reconstruction to avoid source-file TOCTOU.
- **Staging Workspace:** A private temporary area holding authoritative Part copies or a candidate reconstructed tree.
- **Publication:** Whole-tree replacement that makes staged output visible at its final path.
- **Destination:** The requested reconstruction path.
- **Force:** Permission to replace an existing Destination, never permission to bypass safety.
