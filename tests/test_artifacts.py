import json

from astrotransit.validation.artifacts import write_artifact


def test_artifact_writes_hash_manifest(tmp_path):
    path = write_artifact({"value": 3}, tmp_path / "report.json")
    manifest = json.loads(path.with_name("report.manifest.json").read_text())
    assert len(manifest["sha256"]) == 64
    assert len(manifest["output_hash"]) == 64
