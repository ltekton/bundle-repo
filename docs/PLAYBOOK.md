# bundle-repo: Download-to-Release Playbook

This is the maintainer runbook for a clean macOS/Linux development machine and GitHub-hosted CI. Commands assume the repository is named `bundle-repo` and releases use tags `v<project.version>`.

## 0. One-time prerequisites

Install Git and mise. On macOS with Homebrew:

```sh
brew install git mise gh
```

Activate mise in your shell according to `mise activate` for that shell, then verify:

```sh
git --version
mise --version
gh --version
```

Authenticate the GitHub CLI if you plan to create/configure the repository from the terminal:

```sh
gh auth login
```

## 1. Download and unpack

If you received `bundle-repo-release-ready.zip`:

```sh
mkdir -p ~/git/github.com/ltekton
cd ~/git/github.com/ltekton
unzip ~/Downloads/bundle-repo-release-ready.zip
mv bundle-repo-complete bundle-repo 2>/dev/null || true
cd bundle-repo
```

Confirm the expected files:

```sh
ls bundle_repo.py pyproject.toml mise.toml .python-version
ls docs/PRODUCT.md docs/ARCHITECTURE.md docs/FORMAT.md docs/GLOSSARY.md docs/CI.md
ls .github/workflows/ci.yml .github/workflows/codeql.yml .github/workflows/release.yml
```

## 2. Initialize Git if necessary

Only do this if the directory is not already a clone:

```sh
git init -b main
git add .
git commit -m "Initial bundle-repo implementation"
```

For an existing GitHub repository:

```sh
git remote add origin git@github.com:ltekton/bundle-repo.git
git remote -v
```

Or create a new public repository with GitHub CLI:

```sh
gh repo create ltekton/bundle-repo --public --source=. --remote=origin
```

Do not push yet.

## 3. Install the pinned toolchain

The project requests Python 3.14 and uv through mise:

```sh
mise install
mise current
python --version
uv --version
```

Python must be 3.14.x.

## 4. Create the Python dependency lock

This is mandatory. CI deliberately fails without `uv.lock`.

```sh
uv lock
uv lock --check
uv sync --all-groups --locked
```

With `lockfile = true`, mise also maintains its tool lock when resolving configured tools. Confirm the lock state present on your mise version:

```sh
ls -l uv.lock
ls -l mise.lock 2>/dev/null || true
```

Commit generated lockfiles that are present:

```sh
git add uv.lock mise.lock 2>/dev/null || git add uv.lock
git commit -m "Lock development toolchain and dependencies"
```

## 5. Normalize formatting before diagnosing lint

```sh
mise run format
mise run lint-fix
mise run format-check
mise run lint
```

Review every automatic change:

```sh
git diff
```

Never globally disable a Ruff rule merely to make the first run green. Use a narrow `# noqa: CODE - reason` only when the construct is intentional.

Commit formatting separately:

```sh
git add bundle_repo.py tests scripts pyproject.toml
git commit -m "Normalize Ruff formatting and lint"
```

## 6. Fix static typing

Run:

```sh
mise run typecheck
```

Fix Pyrefly findings rather than switching to the legacy preset. Re-run until clean:

```sh
mise run typecheck
```

Then commit:

```sh
git add bundle_repo.py tests scripts pyproject.toml
git commit -m "Satisfy Pyrefly type checking"
```

## 7. Run functional and security tests

```sh
mise run test-unit
mise run test-services
mise run test-security
mise run test-property
mise run test-failure
mise run test-integration
mise run test
```

Hypothesis is a required dev dependency. A missing Hypothesis installation is an error, not a skipped property suite.

## 8. Run traceability

```sh
mise run traceability
mise run traceability-report
```

Inspect:

```sh
git diff -- docs/TRACEABILITY.md
```

Unknown requirement IDs, duplicate definitions, and malformed requirement markers must be fixed before proceeding.

## 9. Run branch coverage

The release threshold is **75% branch-aware coverage**.

```sh
mise run test-coverage
```

Open `htmlcov/index.html` if the threshold fails. Add tests for uncovered validation, rollback, error, and security branches. Do not add broad `coverage.py` exclusions to make the percentage green.

For additional machine-readable analysis:

```sh
uv run python -m pytest tests \
  --cov=bundle_repo \
  --cov-branch \
  --cov-context=test \
  --cov-report=term-missing \
  --cov-report=json:coverage.json \
  --cov-fail-under=75
```

## 10. Run the full local quality gate

```sh
mise run check
```

Before publishing any tag, also run:

```sh
mise run release-check
```

Both must exit 0.

## 11. Manually smoke-test the product

Create a disposable Git repository:

```sh
tmp="$(mktemp -d)"
mkdir "$tmp/source"
cd "$tmp/source"
git init -q
git config user.email test@example.invalid
git config user.name Test
printf 'hello\n' > hello.txt
git add hello.txt
git commit -qm init
```

From the bundle-repo project environment, exercise all commands:

```sh
cd /path/to/bundle-repo
uv run bundle-repo create "$tmp/source" --output "$tmp/bundle"
uv run bundle-repo verify "$tmp/bundle/bundle.manifest.json"
uv run bundle-repo reconstruct "$tmp/bundle/bundle.manifest.json" "$tmp/restored"
cmp "$tmp/source/hello.txt" "$tmp/restored/hello.txt"
```

## 12. Commit the release candidate

Ensure no generated caches or build artifacts are staged:

```sh
git status --short
git diff --check
```

Then:

```sh
git add .
git commit -m "Prepare bundle-repo 0.1.0"
```

## 13. Push the branch and let CI run

```sh
git push -u origin main
```

For normal development, push a feature branch and open a pull request instead of pushing directly to protected `main`.

CI must pass:

- `Validate dependency lock`
- `Quality / Linux / Python 3.14`
- Ubuntu, macOS, and Windows test matrix
- `Build / consumer smoke`
- CodeQL `Analyze python`
- CodeQL `Analyze actions`

## 14. Configure GitHub repository protection before the first release

In **Settings -> Rules -> Rulesets** (or Branch protection), protect `main`:

1. require pull requests;
2. require at least one approval for a team repository;
3. dismiss stale approvals after new commits;
4. require conversation resolution;
5. require status checks to pass;
6. require branches to be up to date before merge;
7. select the CI and CodeQL checks listed above after they have run at least once;
8. block force pushes;
9. block branch deletion.

In **Settings -> Environments**, create `release` and configure required reviewers if the repository ownership model supports approvals. Limit deployment branches/tags so only version tags such as `v*` are eligible.

In **Settings -> Code security**, enable Dependabot alerts/security updates and Code scanning where available. Do not configure CodeQL default setup at the same time as the committed advanced CodeQL workflow unless you intentionally want duplicate analysis.

## 15. Verify the release version

The tag must exactly equal `v<project.version>`.

```sh
uv run python scripts/check_version.py
```

For version 0.1.0, create `v0.1.0` only after `main` is green.

## 16. Create and push the release tag

```sh
git checkout main
git pull --ff-only
git status --short
mise run release-check

git tag -s v0.1.0 -m "bundle-repo 0.1.0"
git push origin v0.1.0
```

If signed Git tags are not configured, configure Git/GPG or SSH signing first. The release workflow additionally verifies that the pushed tag matches `pyproject.toml`.

## 17. Observe the release workflow

```sh
gh run list --workflow release.yml --limit 5
gh run watch
```

The release job independently repeats quality/test/coverage checks, builds wheel and sdist, runs the isolated consumer smoke test, creates `SHA256SUMS`, and creates the GitHub Release.

## 18. Verify the published release

```sh
gh release view v0.1.0
```

Download assets into an empty directory:

```sh
verify_dir="$(mktemp -d)"
cd "$verify_dir"
gh release download v0.1.0 --repo ltekton/bundle-repo
sha256sum -c SHA256SUMS
```

On macOS where `sha256sum` is unavailable:

```sh
while read -r digest file; do
  actual="$(shasum -a 256 "$file" | awk '{print $1}')"
  test "$actual" = "$digest" || exit 1
done < SHA256SUMS
```

Install the wheel in a fresh environment and check the CLI:

```sh
python3 -m venv verify-venv
./verify-venv/bin/python -m pip install ./*.whl
./verify-venv/bin/bundle-repo --help
```

## 19. Post-release

Confirm:

- GitHub Release points at the intended signed tag;
- wheel, sdist, and `SHA256SUMS` are attached;
- CodeQL has no new release-blocking alerts;
- Dependabot is enabled;
- `CHANGELOG.md` records the release;
- the next development version/change section is prepared before new work begins.

## Abort conditions

Do not tag or release if any of the following is true:

- `uv.lock` is absent or stale;
- Ruff format/lint fails;
- Pyrefly fails;
- any pytest suite fails or is unexpectedly skipped;
- branch coverage is below 75%;
- traceability structural checks fail;
- package build or consumer smoke test fails;
- `main` required checks are not green;
- the release tag does not match `pyproject.toml`;
- the working tree is dirty when the tag is created.
