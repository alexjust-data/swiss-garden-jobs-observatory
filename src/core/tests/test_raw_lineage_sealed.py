from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pytest

from core.models import RawArtifact
from core.raw_lineage import (
    RawLineageError,
    SourceRoot,
    build_designation,
    capture_manifest,
    consolidate_manifest,
    write_json,
)
from core.storage import RawObjectStore


@pytest.mark.django_db(transaction=True)
def test_designated_root_missing_object_fails_without_repair() -> None:
    key = "source/sealed.json"
    content = b"sealed"
    RawArtifact.objects.create(
        object_key=key,
        sha256_digest=__import__("hashlib").sha256(content).hexdigest(),
        byte_size=len(content),
        content_type="application/json",
    )
    with (
        TemporaryDirectory() as source_path,
        TemporaryDirectory() as destination_path,
        TemporaryDirectory() as evidence_path,
    ):
        source = Path(source_path)
        destination = Path(destination_path)
        RawObjectStore(source).write_bytes(key, content)
        roots = (SourceRoot.create("source", source),)
        manifest = capture_manifest(roots)
        designation_path = Path(evidence_path) / "designation.json"
        write_json(designation_path, build_designation(manifest))
        with patch("core.raw_lineage.DESIGNATION_PATH", designation_path):
            consolidate_manifest(manifest, roots, destination, dry_run=False)
            RawObjectStore(destination).object_path(key).unlink()
            with pytest.raises(RawLineageError, match="root is incomplete"):
                consolidate_manifest(manifest, roots, destination, dry_run=False)
        assert not RawObjectStore(destination).object_path(key).exists()
