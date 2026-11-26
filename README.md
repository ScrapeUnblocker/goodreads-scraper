# Goodreads Scraper

[![CI](https://github.com/ScrapeUnblocker/goodreads-scraper/actions/workflows/ci.yml/badge.svg)](https://github.com/ScrapeUnblocker/goodreads-scraper/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Powered by ScrapeUnblocker](https://img.shields.io/badge/powered%20by-ScrapeUnblocker-6f42c1.svg)](https://scrapeunblocker.com/?utm_source=github&utm_medium=integration&utm_campaign=example-repos)

**Scrape [Goodreads](https://www.goodreads.com) into clean JSON or CSV: book search results,
full book details (ISBN-13, pages, publisher, genres, awards, series, rating histogram,
want-to-read counts), community reviews sorted and filtered the way the site does it,
Listopia lists, author profiles and bibliographies, and the most-shelved books for any genre.**
Goodreads stopped issuing new API keys in December 2020; this package reads the public pages
instead, so you get the same data readers see, as typed Python records or from the command line.
Built for book recommendation datasets, reading-trend and genre research, review and sentiment
analysis, catalogue enrichment and publishing market research.

Powered by [ScrapeUnblocker](https://scrapeunblocker.com/?utm_source=github&utm_medium=integration&utm_campaign=example-repos):
the `getPageSource` API loads each Goodreads page in a real browser and returns the rendered
HTML, and its browser `steps` drive the reviews page (sort, filters, text search, "Show more
reviews") inside the same call. This package parses the result into typed records. You don't
need proxies, a headless browser or retry logic of your own.

## Features

- **Book search.** Any title, author, ISBN or keywords, 20 books per page across as many pages
  as you need: book and work IDs, title, series with position, author with follower and work
  counts, co-authors / translators / illustrators with their roles, average rating, ratings and
  text-review counts, editions count, publication date, description, cover and Kindle price.
  Filter by minimum rating or number of ratings, and keep one edition per work.
- **Full book details.** ISBN, ISBN-13, ASIN, format, page count, publisher, language, edition
  and original publication dates, original title, genres, series, every author with role,
  awards (winner / nominee, category, year), characters, places, the 1-5 star rating
  histogram, currently-reading and want-to-read counts, quotes / questions / discussions
  counts, review counts per language, cover, Kindle price, editions link and the first 30
  community reviews.
- **Reviews, sorted and filtered.** Popular (Goodreads' default), newest or oldest first; only
  one language; only this edition; only 1-5 star reviews; only reviews that mention some text.
  Each review comes with its ID and link, star rating (quarter stars included), date, full text
  with paragraphs, spoiler flag, the reviewer's shelves, likes and comments, and the reviewer's
  name, profile, review count and followers. 30 reviews per page, paged in the browser.
- **Listopia lists.** Any list (Best Books Ever, Books That Everyone Should Read At Least
  Once, ...): rank, score, votes, rating and ratings count for 100 books per page, plus the
  list's title, description, size, voter count, creation date and tags.
- **Authors.** Profile (born / died with birthplace, website, Twitter, genres, influences,
  member since, bio, average rating, ratings, reviews, distinct works, most popular books) and
  the author's complete book list, 30 per page, sorted by popularity, publication year, title,
  rating or page count.
- **Genre shelves.** The most-shelved books for any shelf tag (`fantasy`, `science-fiction`,
  `historical-fiction`, ...) with how many readers put each book on that shelf.
- **Resilient.** Timeouts, transient API errors, pages that come back without their content
  and review pages that land on the wrong offset are retried with doubling backoff. Unknown
  books, authors and lists raise a clear not-found error.
- **JSON, JSON Lines or CSV.** CSV files are UTF-8 with a BOM, so Excel opens accented titles
  correctly; nested values (authors, series, histograms) become readable cells.
- **CLI + Python library.** Fully typed, and tested offline with a mocked client.

## Install

```bash
git clone https://github.com/ScrapeUnblocker/goodreads-scraper.git
cd goodreads-scraper
pip install .
```

Get an API key at [scrapeunblocker.com](https://scrapeunblocker.com/?utm_source=github&utm_medium=integration&utm_campaign=example-repos)
and expose it as `SCRAPEUNBLOCKER_KEY` (the official SDK reads it from there):

```bash
export SCRAPEUNBLOCKER_KEY=your_key_here        # Windows PowerShell: $env:SCRAPEUNBLOCKER_KEY="your_key_here"
```

You can also copy `.env.example` to `.env` and load it with your tool of choice.

## IDs and URLs

Every command accepts what you copy from the browser. A book can be `44767458`,
`44767458-dune` or `https://www.goodreads.com/book/show/44767458-dune`; an author `58`,
`58.Frank_Herbert` or the author URL; a list `1`, `1.Best_Books_Ever` or the list URL; a
shelf `fantasy`, `Science Fiction` or a `/shelf/show/` or `/genres/` URL.

## CLI usage

```bash
# Search: 3 pages (60 books), one edition per work, at least 1,000 ratings, to CSV
goodreads-scraper search "brandon sanderson" --pages 3 --one-per-work --min-ratings 1000 -o sanderson.csv

# Several queries in one run, merged and de-duplicated, with every book page opened
goodreads-scraper search "dune" "foundation" --limit 10 --details -o classics.json

# Full details of one or more books (add --no-reviews to skip the first 30 reviews)
goodreads-scraper book 44767458 https://www.goodreads.com/book/show/54493401-project-hail-mary --pretty

# Reviews: newest English 1-star reviews, two pages (60 reviews)
goodreads-scraper reviews 54493401 --sort newest --language en --rating 1 --pages 2 -o one_star.csv

# Reviews that mention a word, oldest first
goodreads-scraper reviews 44767458-dune --search "sandworm" --sort oldest -o sandworm.jsonl

# A Listopia list: top 300 with rank, score and votes
goodreads-scraper list 1.Best_Books_Ever --pages 3 -o best_books_ever.csv

# Author profiles, and everything an author wrote (newest first)
goodreads-scraper author 58 38550
goodreads-scraper author-books 38550.Brandon_Sanderson --sort published --pages 2 -o sanderson_books.csv

# The 50 most-shelved books for genre shelves
goodreads-scraper shelf fantasy science-fiction -o shelves.csv
```

Common options: `-o/--output FILE` (format from the extension: `.json`, `.jsonl`, `.csv`),
`-f/--format json|jsonl|csv` (stdout otherwise), `--pretty`, `--pages N`, `--limit N`,
`--country CODE` (route requests through a country), `--retries N`, `-q/--quiet`. Progress goes
to stderr. Run `goodreads-scraper <command> -h` for everything.

## Library usage

```python
from goodreads_scraper import GoodreadsScraper, write_csv

# Reads SCRAPEUNBLOCKER_KEY; GoodreadsScraper(api_key="...") also works
goodreads = GoodreadsScraper()

# Search
books = goodreads.search("project hail mary", pages=2, one_per_work=True, min_ratings=100)
for book in books[:5]:
    print(book.title, book.author, book.average_rating, book.ratings_count, book.url)
write_csv(books, "books.csv")

# Book details (a search result, a list row, an ID or a URL all work)
book = goodreads.book(books[0])
print(book.isbn13, book.pages, book.publisher, book.genres)
print(book.rating_histogram, book.want_to_read, [a.name for a in book.awards])

# Reviews: newest 2-star reviews in English, pages 1-3
reviews = goodreads.reviews(book, sort="newest", language="en", rating=2, pages=3)
for review in reviews[:3]:
    print(review.rating, review.date, review.likes, review.text[:80])

# Only reviews that mention something
spice = goodreads.reviews("44767458", search="spice", pages=2)

# Listopia, authors, shelves
best = goodreads.listopia("1.Best_Books_Ever", pages=2)  # 200 books with rank / score / votes
author = goodreads.author(58)  # profile + most popular books
everything = goodreads.author_books(58, sort="published", pages=5)
fantasy = goodreads.shelf("fantasy").books  # most-shelved first
```

Every record has `to_dict()`. `write_csv`, `write_json`, `to_json` and `to_jsonl` export any
list of records. `search_page`, `reviews_page`, `listopia_page` and `author_books_page` return a
single page with its metadata (totals, applied filters, last page).

Errors: `GoodreadsNotFoundError` (no such book, author, list or shelf, or a review language
the book has no reviews in) and `GoodreadsParseError` (a page came back without its content
after all retries) derive from `GoodreadsError`. API errors from the official SDK (for example
an invalid key) are passed through.

## Example output

A search result (`goodreads-scraper search "project hail mary"`, trimmed):

```json
{
  "book_id": 54493401,
  "title": "Project Hail Mary",
  "url": "https://www.goodreads.com/book/show/54493401-project-hail-mary",
  "author": "Andy Weir",
  "author_id": 6540057,
  "author_url": "https://www.goodreads.com/author/show/6540057.Andy_Weir",
  "author_followers": 76764,
  "author_works": 61,
  "series": [],
  "work_id": 79106958,
  "average_rating": 4.51,
  "ratings_count": 1903608,
  "reviews_count": 262538,
  "editions_count": 5,
  "publication_date": "2021-05-04",
  "description": "Ryland Grace is the sole survivor on a desperate, last-chance mission...",
  "cover": "https://m.media-amazon.com/images/S/compressed.photo.goodreads.com/books/1764703833i/54493401.jpg",
  "kindle_price": 14.99,
  "position": 1,
  "page": 1,
  "query": "project hail mary"
}
```

Book details (`goodreads-scraper book 54493401`, trimmed):

```json
{
  "book_id": 54493401,
  "title": "Project Hail Mary",
  "work_id": 79106958,
  "genres": ["Science Fiction", "Fiction", "Audiobook", "Book Club", "Fantasy", "Space"],
  "average_rating": 4.51,
  "ratings_count": 1903608,
  "reviews_count": 262538,
  "rating_histogram": {"1": 8753, "2": 28062, "3": 139006, "4": 536426, "5": 1191361},
  "currently_reading": 152570,
  "want_to_read": 1360824,
  "format": "Hardcover",
  "pages": 476,
  "publisher": "Ballantine Books",
  "language": "English",
  "isbn": "0593135202",
  "isbn13": "9780593135204",
  "asin": "0593135202",
  "publication_date": "2021-05-04",
  "original_publication_date": "2021-05-04",
  "awards": [
    {"name": "Hugo Award", "category": "Best Novel", "designation": "nominee", "year": 2022,
     "url": "https://www.goodreads.com/award/show/9-hugo-award"}
  ],
  "characters": ["Ryland Grace", "Rocky", "Eva Stratt"],
  "places": ["Tau Ceti System", "Outer Space"],
  "quotes_count": 918,
  "questions_count": 121,
  "kindle_price": 14.99,
  "reviews": ["... the first 30 reviews ..."]
}
```

A review (`goodreads-scraper reviews 54493401 --sort newest --language en --rating 2 --pages 2`):

```json
{
  "review_id": 8700941111,
  "url": "https://www.goodreads.com/review/show/8700941111",
  "rating": 2.0,
  "date": "2026-10-03",
  "text": "I wanted to love the book the same way I loved the movie. But I don’t. ...",
  "has_spoilers": false,
  "shelves": [],
  "likes": 0,
  "comments": 0,
  "reviewer": "Jessica",
  "reviewer_id": 8603035,
  "reviewer_url": "https://www.goodreads.com/user/show/8603035-jessica",
  "reviewer_is_author": false,
  "reviewer_reviews": 3,
  "book_id": 54493401,
  "position": 32,
  "page": 2
}
```

A Listopia row (`goodreads-scraper list 1`):

```json
{
  "book_id": 2767052,
  "title": "The Hunger Games",
  "author": "Suzanne Collins",
  "author_id": 153394,
  "series": "The Hunger Games",
  "series_position": "1",
  "average_rating": 4.36,
  "ratings_count": 10313973,
  "rank": 1,
  "score": 4558374,
  "votes": 46319,
  "cover": "https://i.gr-assets.com/images/S/compressed.photo.goodreads.com/books/1586722975i/2767052.jpg",
  "source": "list:1"
}
```

## Good to know

- **Work vs. edition.** Goodreads groups editions into a work. Ratings, review counts, awards,
  characters and places belong to the work (every edition); ISBNs, format, pages, publisher,
  language and `publication_date` belong to the edition you opened. Search results often list
  several editions of one work: `--one-per-work` keeps the first.
- **How review paging works.** The reviews page shows 30 reviews and "Show more reviews"
  replaces them with the next 30, so review page *n* is *n - 1* clicks in the browser and
  deeper pages take longer to load. A request runs at most 10 browser steps, so one request
  reaches page 10 without filters; sorting / language / edition filters, a star filter and
  text search each use some of those steps (sort only: page 6). The CLI tells you when you ask
  for more; `max_review_page(**filters)` gives the number in code.
- **Review fields.** `rating` can be a quarter-star value (`1.25`) and is `null` when the
  reviewer did not rate. For the first page of reviews, counts come straight from the page
  data; on later pages reviewer follower counts are rounded the way Goodreads shows them
  ("29.1k").
- **Unknown language filter.** A language the book has no reviews in is reported as
  not found; the book's `review_languages` lists the languages it has reviews in.
- **Shelves show 50 books** to signed-out visitors, most-shelved first. Listopia lists page in
  100s; the pagination of the biggest lists stops at page 100.
- **Search counts are rounded.** `total_results` is Goodreads' own figure ("over 108k").
- **Dates** are ISO (`2021-05-04`); author "member since" is a month (`2010-01`).
- Collect public data responsibly: keep request volumes reasonable and follow Goodreads' terms
  and the data-protection rules that apply to you. Reviews carry reviewers' public display
  names and profile links.

## Project layout

```
goodreads-scraper/
├── src/goodreads_scraper/
│   ├── __init__.py      # public API and package docs
│   ├── scraper.py       # GoodreadsScraper: search, books, reviews, lists, authors, shelves, retries
│   ├── parsing.py       # Goodreads pages -> typed records (page payload, Apollo cache, HTML)
│   ├── steps.py         # browser steps for review sorting, filters, search and paging
│   ├── models.py        # Book, BookDetails, Review, BookRow, Author, ListPage, ...
│   ├── urls.py          # IDs from any Goodreads link, URL builders, sort orders
│   ├── export.py        # JSON, JSON Lines and CSV writers
│   ├── cli.py           # the goodreads-scraper command
│   └── __main__.py      # python -m goodreads_scraper
├── examples/
│   ├── search_to_json.py            # one edition per work for a search, as JSON
│   ├── reviews_by_rating_to_csv.py  # newest 1-star and 5-star English reviews, to CSV
│   └── listopia_with_details.py     # top of a Listopia list enriched with ISBN, pages, genres
├── tests/                           # offline tests with a mocked client (no API calls)
├── pyproject.toml
├── requirements.txt
├── Makefile
└── .github/workflows/ci.yml
```

## Development

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
make install    # pip install -e ".[dev]"
make lint       # ruff check .
make format     # ruff format .
make test       # pytest -q (offline, no API key needed)
make run        # examples/search_to_json.py "project hail mary" (needs SCRAPEUNBLOCKER_KEY)
```

`pre-commit install` enables the ruff hooks from `.pre-commit-config.yaml`.

## Links

- [ScrapeUnblocker](https://scrapeunblocker.com/?utm_source=github&utm_medium=integration&utm_campaign=example-repos) - web scraping API that returns rendered HTML from protected sites
- [Documentation](https://docs.scrapeunblocker.com/?utm_source=github&utm_medium=integration&utm_campaign=example-repos) - `getPageSource`, browser steps, SDKs, parameters and errors
- Official SDK: `pip install scrapeunblocker`

## License

[MIT](LICENSE) - Copyright (c) 2026 ScrapeUnblocker
