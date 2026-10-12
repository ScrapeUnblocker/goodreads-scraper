"""Search Goodreads and save the books as JSON (one edition per work).

export SCRAPEUNBLOCKER_KEY=your_key
python examples/search_to_json.py "project hail mary"
python examples/search_to_json.py "brandon sanderson" 3
"""

from __future__ import annotations

import sys

from goodreads_scraper import GoodreadsScraper, write_json


def main() -> None:
    query = sys.argv[1] if len(sys.argv) > 1 else "project hail mary"
    pages = int(sys.argv[2]) if len(sys.argv) > 2 else 1

    goodreads = GoodreadsScraper()  # reads SCRAPEUNBLOCKER_KEY
    books = goodreads.search(query, pages=pages, one_per_work=True, min_ratings=50)

    for book in books[:10]:
        rating = f"{book.average_rating:.2f}" if book.average_rating else "  - "
        print(f"{rating}  {book.ratings_count or 0:>10,} ratings  {book.title} - {book.author}")
    path = "books.json"
    print(f"saved {write_json(books, path)} books to {path}")


if __name__ == "__main__":
    main()
