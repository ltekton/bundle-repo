import json
from pathlib import Path

import pytest

import bundle_repo as br
from tests.helpers import git

pytestmark = pytest.mark.integration


@pytest.mark.req("BR-REQ-CREATE-003")
def test_include_exclude(repo: Path, tmp_path: Path):
    for rel in ["src/a.py", "src/a_test.py", "README.md"]:
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(rel)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "c")
    policy = br.SelectionPolicy(("src/", "README.md"), ("*_test.py",))
    result = br.BundleBuilder(
        br.GitRepository(repo), br.CreateOptions(repo, tmp_path / "out", selection=policy)
    ).build()
    raw = json.loads(result.manifest.read_text())
    assert [e["path"] for e in raw["entries"]] == ["README.md", "src/a.py"]
