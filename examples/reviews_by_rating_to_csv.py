"""Collect a book's newest 1-star and 5-star English reviews into one CSV.

A ready-made input for sentiment analysis or "what do readers love / hate" summaries.
Each star rating is a separate filtered request; ``--pages`` fetches 30 reviews per page.

    export SCRAPEUNBLOCKER_KEY=your_key
    python examples/reviews_by_rating_to_csv.py 54493401
    python examples/reviews_by_rating_to_csv.py https://www.goodreads.com/book/show/44767458-dune 2
"""

from __future__ import annotations

import sys

from goodreads_scraper import GoodreadsScraper, write_csv

COLUMNS = ["rating", "date", "likes", "comments", "reviewer", "has_spoilers", "text", "url"]


def main() -> None:
    book = sys.argv[1] if len(sys.argv) > 1 else "54493401"  # Project Hail Mary
    pages = int(sys.argv[2]) if len(sys.argv) > 2 else 1

    goodreads = GoodreadsScraper()  # reads SCRAPEUNBLOCKER_KEY
    collected = []
    for stars in (1, 5):
        found = goodreads.reviews(book, sort="newest", language="en", rating=stars, pages=pages)
        print(f"{stars}-star: {len(found)} reviews")
        collected.extend(found)

    path = "reviews_by_rating.csv"
    print(f"saved {write_csv(collected, path, columns=COLUMNS)} reviews to {path}")


if __name__ == "__main__":
    main()
