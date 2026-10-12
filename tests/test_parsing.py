from __future__ import annotations

import pytest
from bs4 import BeautifulSoup

from goodreads_scraper.parsing import (
    GoodreadsNotFoundError,
    GoodreadsParseError,
    flight_rows,
    flight_text,
    full_size,
    html_to_text,
    ms_to_date,
    node_text,
    parse_author_books_page,
    parse_author_page,
    parse_book_page,
    parse_count,
    parse_date,
    parse_list_page,
    parse_reviews_page,
    parse_search_page,
    parse_shelf_page,
    split_series,
)

from .conftest import (
    author_books_html,
    author_html,
    book_html,
    empty_reviews_html,
    list_html,
    missing_book_html,
    review_card,
    reviews_html,
    search_html,
    shelf_html,
)

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "text, expected",
    [
        ("1,717,578 ratings", 1717578),
        ("29.1k followers", 29100),
        ("108k", 108000),
        ("2m", 2000000),
        ("3 books", 3),
        ("no digits", None),
        (None, None),
        (42, 42),
    ],
)
def test_parse_count(text, expected):
    assert parse_count(text) == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("December 5, 2006", "2006-12-05"),
        ("October 08, 1920", "1920-10-08"),
        ("May 13th, 2008", "2008-05-13"),
        ("January 2010", "2010-01"),
        ("Sept 2010", None),
        ("", None),
    ],
)
def test_parse_date(text, expected):
    assert parse_date(text) == expected


def test_ms_to_date_handles_dates_before_1970():
    assert ms_to_date(1569913200000) == "2019-10-01"
    assert ms_to_date(-144694800000) == "1965-06-01"
    assert ms_to_date(None) is None
    assert ms_to_date("soon") is None


def test_full_size_and_series_split():
    assert full_size("https://x/books/1i/2767052._SX50_.jpg") == "https://x/books/1i/2767052.jpg"
    assert full_size("https://x/a/58._UX200_CR0,0,200,200_.jpg") == "https://x/a/58.jpg"
    assert split_series("Dune (Dune, #1)") == ("Dune", "Dune", "1")
    assert split_series("Chapterhouse: Dune (Dune #6)") == ("Chapterhouse: Dune", "Dune", "6")
    assert split_series("Hunting Harkonnens (Legends of Dune, #0.5)")[2] == "0.5"
    assert split_series("The Road (Movie Tie-In)") == ("The Road (Movie Tie-In)", None, None)


def test_node_text_rejoins_pretty_printed_html():
    soup = BeautifulSoup(
        "<span>\n   I am so\n   glad\n   <i>\n    Dune\n   </i>\n   ends.\n"
        "   <br/>\n   <br/>\n   Next   paragraph.\n</span>",
        "html.parser",
    )
    assert node_text(soup.span) == "I am so glad Dune ends.\n\nNext paragraph."
    assert html_to_text("A<br /><br />B <b>bold</b>") == "A\n\nB bold"
    assert html_to_text("") is None


# --------------------------------------------------------------------------- #
# Search
# --------------------------------------------------------------------------- #


def test_flight_payload_rows_and_text_rows():
    payload = flight_text(search_html())
    rows = flight_rows(payload)
    assert rows["9"].startswith("var x = 1;")
    assert rows["9"].endswith(": é');")
    assert rows["7"]["node"]["name"] == "Frank Herbert"
    assert isinstance(rows["1"], list)


def test_search_page_books_and_references():
    page = parse_search_page(search_html(), "dune", 1, "https://example/search")
    assert [b.book_id for b in page.books] == [44767458, 44492285, 1111]
    assert page.total_results == 108000
    assert page.has_next is False  # fewer than 20 results
    dune, messiah, _ = page.books
    assert dune.title == "Dune"
    assert dune.author == "Frank Herbert" and dune.author_id == 58
    assert dune.author_followers == 17573 and dune.author_works == 634
    assert [(s.title, s.position) for s in dune.series] == [("Dune", "1")]
    assert dune.series[0].url.endswith("/series/45935-dune")
    assert dune.work_id == 3634639
    assert dune.average_rating == 4.29 and dune.ratings_count == 1717579
    assert dune.reviews_count == 171757
    assert dune.editions_count == 540
    assert dune.publication_date == "2019-10-01"
    assert dune.description == "First line.\n\nSecond line."
    assert dune.kindle_price == 9.99
    assert dune.position == 1 and dune.page == 1 and dune.query == "dune"
    # the second book's author is a "$7:node" row reference
    assert messiah.author == "Frank Herbert" and messiah.author_followers == 17573
    intro = messiah.contributors[1]
    assert (intro.name, intro.role, intro.author_id) == ("Brian Herbert", "Introduction", 56)


def test_search_page_positions_continue_across_pages():
    page = parse_search_page(search_html(first=21), "dune", 2, "u")
    assert [b.position for b in page.books] == [21, 22, 23]


def test_empty_search_page():
    page = parse_search_page(search_html(books=[]), "zzzz", 1, "u")
    assert page.books == [] and page.has_next is False


def test_search_page_without_payload_is_a_parse_error():
    with pytest.raises(GoodreadsParseError):
        parse_search_page("<html><body>Just a moment...</body></html>", "dune", 1, "u")


# --------------------------------------------------------------------------- #
# Book pages
# --------------------------------------------------------------------------- #


def test_book_page_details():
    book = parse_book_page(book_html(), "https://www.goodreads.com/book/show/44767458")
    assert book.book_id == 44767458 and book.title == "Dune"
    assert book.title_complete == "Dune (Dune, #1)"
    assert book.work_id == 3634639 and book.original_title == "Dune"
    assert [(a.name, a.role, a.author_id) for a in book.authors] == [
        ("Frank Herbert", "Author", 58),
        ("Brian Herbert", "Introduction", 56),
    ]
    assert book.series[0].title == "Dune" and book.series[0].position == "1"
    assert book.description == "Set on the desert planet Arrakis.\n\nA classic."
    assert book.genres == ["Science Fiction", "Classics"]
    assert book.rating_histogram == {"1": 26182, "2": 56084, "3": 206414, "4": 528033, "5": 900866}
    assert (book.currently_reading, book.want_to_read) == (155686, 1441407)
    assert (book.isbn, book.isbn13, book.asin) == ("059309932X", "9780593099322", "059309932X")
    assert (book.format, book.pages, book.publisher, book.language) == (
        "Hardcover",
        658,
        "Ace",
        "English",
    )
    assert book.publication_date == "2019-10-01"
    assert book.original_publication_date == "1965-06-01"
    award = book.awards[0]
    assert (award.name, award.category, award.designation, award.year) == (
        "Hugo Award",
        "Best Novel",
        "winner",
        1966,
    )
    assert book.characters == ["Paul Atreides", "Stilgar"] and book.places == ["Arrakis"]
    assert (book.quotes_count, book.questions_count, book.discussions_count) == (1457, 78, 405)
    assert list(book.review_languages) == ["en", "de"]
    assert book.kindle_price == 9.99
    assert book.editions_url.endswith("/work/editions/3634639")


def test_book_page_reviews_are_enriched_from_the_cache():
    book = parse_book_page(book_html(), "https://www.goodreads.com/book/show/44767458")
    first, second = book.reviews
    # the card had a star skeleton: the rating comes from the Apollo cache
    assert first.rating == 5.0
    assert first.likes == 3071 and first.comments == 116
    assert first.reviewer_is_author and first.reviewer_books == 3
    assert first.reviewer_followers == 29123
    assert first.position == 1 and first.book_id == 44767458
    # a rendered card keeps its own rating
    assert second.rating == 1.0
    assert second.has_spoilers
    assert second.reviewer_reviews == 771


def test_missing_book_is_not_found():
    with pytest.raises(GoodreadsNotFoundError):
        parse_book_page(missing_book_html(), "https://www.goodreads.com/book/show/1")


def test_book_page_without_data_is_a_parse_error():
    with pytest.raises(GoodreadsParseError):
        parse_book_page("<html><body>blocked</body></html>", "u")


# --------------------------------------------------------------------------- #
# Reviews
# --------------------------------------------------------------------------- #


def test_review_card_fields():
    page = parse_reviews_page(
        reviews_html(cards=[review_card(554, "Elizabeth", rating="Rating 1.25 out of 5")]),
        44767458,
        1,
        "u",
    )
    review = page.reviews[0]
    assert review.review_id == 554
    assert review.url == "https://www.goodreads.com/review/show/554"
    assert review.rating == 1.25
    assert review.date == "2006-12-05"
    assert review.text == "Loved it.\n\nWould read again."
    assert review.shelves == ["fiction", "sci-fi"]
    assert (review.likes, review.comments) == (125, 31)
    assert review.reviewer == "Elizabeth" and review.reviewer_id == 561
    assert review.reviewer_url.endswith("/user/show/561-elizabeth")
    assert review.reviewer_reviews == 771 and review.reviewer_followers == 29100
    assert not review.reviewer_is_author and not review.has_spoilers


def test_reviews_page_span_and_filters():
    page = parse_reviews_page(
        reviews_html(first=31, total="1,582", filters=["English", "Newest first", "1 star"]),
        44767458,
        2,
        "u",
    )
    assert (page.first, page.last, page.total) == (31, 60, 1582)
    assert page.applied_filters == ["English", "Newest first", "1 star"]
    assert page.has_next
    assert [r.position for r in page.reviews[:2]] == [31, 32]


def test_last_reviews_page_has_no_next():
    page = parse_reviews_page(reviews_html(first=31, total="60"), 1, 2, "u")
    assert not page.has_next


def test_no_matching_reviews():
    page = parse_reviews_page(empty_reviews_html(), 1, 1, "u")
    assert page.reviews == [] and page.total == 0 and not page.has_next
    assert page.applied_filters == ["Mentions: xyz"]


def test_reviews_page_that_did_not_render():
    with pytest.raises(GoodreadsParseError):
        parse_reviews_page("<html><body>Access denied</body></html>", 1, 1, "u")


# --------------------------------------------------------------------------- #
# Listopia, authors, shelves
# --------------------------------------------------------------------------- #


def test_list_page():
    page = parse_list_page(list_html(), 1, 1, "u")
    assert page.title == "Best Books Ever"
    assert page.description == (
        "The best books ever, as voted on by the general Goodreads community."
        "\n\nNote to librarians."
    )
    assert (page.books_count, page.voters_count) == (79754, 297180)
    assert page.created == "2008-05-13" and page.created_by == "Michael Economy"
    assert page.tags == ["best", "fiction"]
    assert (page.last_page, page.has_next) == (3, True)
    first, second = page.books
    assert first.book_id == 2767052 and first.title == "The Hunger Games"
    assert (first.series, first.series_position) == ("The Hunger Games", "1")
    assert first.author == "Suzanne Collins" and first.author_id == 153394
    assert (first.average_rating, first.ratings_count) == (4.36, 10313973)
    assert (first.rank, first.score, first.votes) == (1, 4558374, 46319)
    assert first.cover == "https://i.gr-assets.com/books/1586722975i/2767052.jpg"
    assert first.source == "list:1"
    assert second.votes == 1 and second.series is None


def test_last_list_page():
    page = parse_list_page(list_html(page=3), 1, 3, "u")
    assert page.has_next is False and page.books[0].rank == 201


def test_author_page():
    author = parse_author_page(author_html(), 58, "https://www.goodreads.com/author/show/58")
    assert author.name == "Frank Herbert"
    assert author.url == "https://www.goodreads.com/author/show/58.Frank_Herbert"
    assert author.born == "1920-10-08" and author.died == "1986-02-11"
    assert author.birthplace == "Tacoma, Washington, The United States"
    assert author.website == "http://www.dunenovels.com/"
    assert author.twitter == "dune"
    assert author.genres == ["Science Fiction", "Fantasy"]
    assert author.influences == ["Isaac Asimov"]
    assert author.member_since == "2010-01"
    assert author.about == "Full bio of Dune's author.\n\nSecond paragraph."
    assert author.image == "https://images.example/authors/58.jpg"
    assert (author.average_rating, author.ratings_count, author.reviews_count) == (
        4.14,
        2965839,
        161830,
    )
    assert author.works_count == 636
    top = author.top_books[0]
    assert (top.title, top.series, top.published_year, top.editions_count) == (
        "Dune",
        "Dune",
        1965,
        3,
    )
    assert top.source == "author:58"


def test_author_books_page():
    page = parse_author_books_page(author_books_html(), 58, 1, "u", "published")
    assert page.author == "Frank Herbert" and page.sort == "published"
    assert (page.last_page, page.has_next) == (2, True)
    messiah = page.books[0]
    assert [(c.name, c.role) for c in messiah.contributors] == [
        ("Suzanne Collins", "Author"),
        ("Brian Herbert", "Introduction"),
    ]
    assert messiah.published_year == 1969 and messiah.editions_count == 275
    last = parse_author_books_page(author_books_html(page=2), 58, 2, "u")
    assert last.has_next is False


def test_shelf_page():
    page = parse_shelf_page(shelf_html(), "science-fiction", "u")
    assert page.title == "Science Fiction Books"
    assert len(page.books) == 1  # the video entry is skipped
    book = page.books[0]
    assert (book.book_id, book.title, book.series, book.series_position) == (
        44767458,
        "Dune",
        "Dune",
        "1",
    )
    assert book.shelved_count == 22035
    assert (book.average_rating, book.ratings_count, book.published_year) == (4.29, 1717578, 1965)
    assert book.rank == 1 and book.source == "shelf:science-fiction"
    assert book.cover == "https://i.gr-assets.com/books/1555447414l/44767458.jpg"
