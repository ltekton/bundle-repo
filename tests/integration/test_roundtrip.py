import os, stat
from pathlib import Path
import pytest
import bundle_repo as br
from conftest import git
pytestmark=pytest.mark.integration

@pytest.mark.req("BR-REQ-RECON-002", 'BR-REQ-CREATE-001','BR-REQ-CREATE-002','BR-REQ-VERIFY-001','BR-REQ-VERIFY-003','BR-SI-004')
def test_full_roundtrip(repo:Path,tmp_path:Path):
    data={"hello.txt":b"hello\n","empty":b"","bin":bytes(range(256)),"unicode/文件":"Grüße".encode()}
    for rel,b in data.items(): p=repo/rel; p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(b)
    script=repo/"run.sh"; script.write_text("#!/bin/sh\n"); script.chmod(0o755)
    try: os.symlink("hello.txt",repo/"link")
    except OSError as exc: pytest.skip(str(exc))
    git(repo,"add","-A"); git(repo,"commit","-qm","content")
    result=br.BundleBuilder(br.GitRepository(repo),br.CreateOptions(repo,tmp_path/"bundle",part_bytes=4096,chunk_bytes=64)).build()
    verified=br.BundleVerifier().verify(result.manifest); dest=tmp_path/"dest"; br.BundleReconstructor().reconstruct(verified,dest)
    for rel,b in data.items(): assert (dest/rel).read_bytes()==b
    assert (dest/"run.sh").stat().st_mode & stat.S_IXUSR
    assert (dest/"link").is_symlink() and os.readlink(dest/"link")=="hello.txt"
