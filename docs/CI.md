# CI and Release Security

## Required checks

The protected `main` branch SHOULD require the following GitHub checks before merge:

- `Quality / Linux / Python 3.14`
- all `Tests / <platform> / Python 3.14` matrix jobs
- `Build / consumer smoke`
- `Analyze Python` from CodeQL

Require pull requests, dismiss stale approvals on new commits, require conversation resolution, block force pushes/deletions, and require branches to be current before merge.

## Dependency locks

`uv.lock` is REQUIRED in CI. Generate it after changing `pyproject.toml`:

```sh
uv lock
uv sync --all-groups --locked
```

CI deliberately fails if `uv.lock` is absent or stale. `mise.lock` SHOULD also be committed after `mise install`/lock resolution so the Python/uv toolchain is reproducible across declared platforms.

## Coverage

The release gate measures only `bundle_repo` and requires **75.00% total branch-aware coverage**. CI passes `--cov-branch` and an explicit `--cov-fail-under=75`; `pyproject.toml` carries the same policy. `relative_files = true` makes recorded paths portable between workspaces.

Coverage exclusions are intentionally narrow: the `__main__` launcher, `TYPE_CHECKING` branches, and overload declarations only. Error handling, rollback, resource-limit failures, and platform safety paths are not excluded to inflate coverage.

## Action supply chain

Checkout, Python setup, uv setup, and CodeQL actions are pinned to commit SHAs. Dependabot is configured for both GitHub Actions and uv dependencies. Checkout does not persist credentials.

## Releases

Tag releases run the quality, traceability, test, coverage, build, and consumer-smoke gates independently. The `release` GitHub Environment SHOULD be configured with appropriate reviewers. The tag must exactly equal `v<project.version>`.

Release assets include wheel, sdist, and `SHA256SUMS`.

GitHub Artifact Attestations are recommended once the repository/plan supports them and the selected `actions/attest` release is pinned according to repository action policy. Attestation requires `id-token: write` and `attestations: write`; do not grant those permissions to normal PR CI.

## Maintainer release procedure

The step-by-step maintainer runbook is `docs/PLAYBOOK.md`. It is the operational checklist from archive download through lock creation, local quality gates, GitHub protection, signed tagging, workflow observation, checksum verification, and post-release validation.
