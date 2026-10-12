from __future__ import annotations

import json

from goodreads_scraper.export import csv_string, flatten, to_json, to_jsonl, write_csv, write_json
from goodreads_scraper.models import Award, BookDetails, Contributor, SeriesRef


def sample() -> BookDetails:
    return BookDetails(
        book_id=1,
        title="Dune",
        url="https://www.goodreads.com/book/show/1",
        authors=[
            Contributor(name="Frank Herbert", role="Author"),
            Contributor(name="Brian Herbert", role="Introduction"),
        ],
        series=[SeriesRef(title="Dune", position="1")],
        genres=["Science Fiction", "Classics"],
        rating_histogram={"1": 10, "5": 90},
        awards=[Award(name="Hugo Award", category="Best Novel", designation="winner", year=1966)],
        average_rating=4.0,
        pages=None,
    )


def test_flatten_labels_nested_values():
    row = flatten(sample())
    assert row["authors"] == "Frank Herbert | Brian Herbert (Introduction)"
    assert row["series"] == "Dune #1"
    assert row["genres"] == "Science Fiction | Classics"
    assert row["rating_histogram"] == "1: 10 | 5: 90"
    assert row["awards"] == "Hugo Award - Best Novel - winner - 1966"
    assert row["average_rating"] == 4
    assert row["pages"] == ""


def test_flatten_can_drop_fields():
    assert "reviews" not in flatten(sample(), drop=("reviews",))


def test_csv_and_json_round_trip(tmp_path):
    text = csv_string([sample()], drop=("reviews",))
    assert text.splitlines()[0].startswith("book_id,title,url,")
    assert json.loads(to_json([sample()]))[0]["authors"][1]["role"] == "Introduction"
    assert json.loads(to_jsonl([sample(), {"x": 1}]).splitlines()[1]) == {"x": 1}
    path = tmp_path / "out.csv"
    assert write_csv([sample()], path) == 1
    assert path.read_bytes().startswith(b"\xef\xbb\xbf")
    json_path = tmp_path / "out.json"
    assert write_json([sample()], json_path) == 1
    assert json.loads(json_path.read_text(encoding="utf-8"))[0]["title"] == "Dune"
