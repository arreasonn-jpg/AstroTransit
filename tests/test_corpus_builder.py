import csv

from scripts.validation.build_labelled_corpus import load_csv


def test_labelled_csv_requires_explicit_reference(tmp_path):
    source = tmp_path / "cases.csv"
    with source.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["target_id", "label", "reference"])
        writer.writeheader()
        writer.writerow({"target_id": "TIC 1", "label": "quiet_star", "reference": "catalog-1"})
    assert load_csv(source)[0].label == "quiet_star"
