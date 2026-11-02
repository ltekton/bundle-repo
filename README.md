# bundle-repo

`bundle-repo` creates, verifies, and reconstructs hardened text-safe bundles from a selected stage-0 Git index snapshot.

Production is one Python 3.14+ file, `bundle_repo.py`, and uses only the standard library. Development uses mise, uv, Hatchling, pytest, Hypothesis, Ruff, Pyrefly, pre-commit, and GitHub Actions.

## CLI

```sh
bundle-repo create . --output ./bundle
bundle-repo verify ./bundle/bundle.manifest.json
bundle-repo reconstruct ./bundle/bundle.manifest.json ./restored
```

## Development

```sh
mise install
mise run test
mise run test-security
mise run test-property
mise run traceability
mise run check
mise run release-check
```

## Documentation

- `docs/PRODUCT.md`: product principles, scope, goals, non-goals, and requirements.
- `docs/GLOSSARY.md`: normative domain language.
- `docs/ARCHITECTURE.md`: trust boundaries, components, workflows, invariants, and ADRs.
- `docs/FORMAT.md`: normative RFC-style bundle format.
- `docs/TRACEABILITY.md`: generated requirements-to-code-to-tests matrix.

## Guarantees and limits

The Git index and Git object database are payload authority. Bundles provide unkeyed SHA-256 integrity detection, not origin authentication. Version 1 does not include compression, encryption, signatures, Git history, untracked files, or submodule working-tree contents.
