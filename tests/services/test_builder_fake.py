from pathlib import Path

import bundle_repo as br
from tests.factories import OID


class FakeRepository:
    def __init__(self):
        self.data = {OID: b"abc"}

    def index_entries(self):
        return (br.GitEntry(br.RepositoryPath.parse("a.txt"), "100644", OID),)

    def read_blob(self, oid):
        return self.data[oid]

    def metadata(self):
        return br.RepositoryMetadata("main", OID, False)


def test_builder_accepts_repository_protocol(tmp_path: Path):
    result = br.BundleBuilder(
        FakeRepository(),
        br.CreateOptions(tmp_path, tmp_path / "out", part_bytes=2048, chunk_bytes=2),
    ).build()
    verified = br.BundleVerifier().verify(result.manifest)
    assert verified.manifest.entries[0].chunks == 2
    assert result.payload_bytes == 3
