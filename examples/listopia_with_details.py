"""Top books of a Listopia list, enriched with each book's page (ISBN-13, pages, genres, ...).

One request for the list page plus one per book, so keep the count small to start with.

    export SCRAPEUNBLOCKER_KEY=your_key
    python examples/listopia_with_details.py                       # Best Books Ever, top 10
    python examples/listopia_with_details.py 264.Books_That_Everyone_Should_Read_At_Least_Once 25
"""

from __future__ import annotations

import sys

from goodreads_scraper import GoodreadsScraper, write_csv


def main() -> None:
    listing = sys.argv[1] if len(sys.argv) > 1 else "1.Best_Books_Ever"
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 10

    goodreads = GoodreadsScraper()  # reads SCRAPEUNBLOCKER_KEY
    ranked = goodreads.listopia(listing, limit=count)
    details = goodreads.books(
        ranked, on_error=lambda item, error: print(f"skipped {item}: {error}", file=sys.stderr)
    )
    by_id = {book.book_id: book for book in details}

    rows = []
    for row in ranked:
        book = by_id.get(row.book_id)
        if book is None:
            continue
        rows.append(
            {
                "rank": row.rank,
                "title": book.title,
                "author": row.author,
                "votes": row.votes,
                "average_rating": book.average_rating,
                "ratings_count": book.ratings_count,
                "first_published": book.original_publication_date,
                "pages": book.pages,
                "isbn13": book.isbn13,
                "genres": book.genres[:5],
                "awards": len(book.awards),
                "url": book.url,
            }
        )
        print(f"#{row.rank:<3} {book.title} ({book.original_publication_date or '?'})")

    path = "listopia.csv"
    print(f"saved {write_csv(rows, path)} books to {path}")


if __name__ == "__main__":
    main()
