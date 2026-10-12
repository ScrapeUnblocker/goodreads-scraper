from __future__ import annotations

import pytest

from goodreads_scraper.urls import (
    absolute,
    author_books_url,
    author_id,
    author_url,
    book_id,
    book_url,
    list_id,
    list_url,
    reviews_url,
    search_url,
    shelf_slug,
    shelf_url,
)


@pytest.mark.parametrize(
    "value",
    [
        44767458,
        "44767458",
        "44767458-dune",
        "44767458.Dune",
        "https://www.goodreads.com/book/show/44767458-dune",
        "https://www.goodreads.com/book/show/44767458-dune/reviews?ref=x",
        " www.goodreads.com/book/show/44767458 ",
    ],
)
def test_book_id_forms(value):
    assert book_id(value) == 44767458


@pytest.mark.parametrize("value", ["", "dune", "https://www.goodreads.com/author/show/58", 0, True])
def test_book_id_rejects_garbage(value):
    with pytest.raises(ValueError):
        book_id(value)


def test_author_and_list_ids():
    assert author_id("58.Frank_Herbert") == 58
    assert author_id("https://www.goodreads.com/author/list/58.Frank_Herbert?page=2") == 58
    assert list_id("1.Best_Books_Ever") == 1
    assert list_id("https://www.goodreads.com/list/show/264.Books_That_Everyone_Should_Read") == 264


def test_search_url():
    assert search_url("project  hail mary") == (
        "https://www.goodreads.com/search?q=project+hail+mary&search_type=books"
    )
    assert search_url("dune", page=3).endswith("&page=3")
    with pytest.raises(ValueError):
        search_url("   ")
    with pytest.raises(ValueError):
        search_url("dune", page=0)


def test_page_urls():
    assert book_url("44767458-dune") == "https://www.goodreads.com/book/show/44767458"
    assert reviews_url(44767458) == "https://www.goodreads.com/book/show/44767458/reviews"
    assert list_url("1.Best_Books_Ever") == "https://www.goodreads.com/list/show/1"
    assert list_url(1, page=2) == "https://www.goodreads.com/list/show/1?page=2"
    assert author_url("58.Frank_Herbert") == "https://www.goodreads.com/author/show/58"


def test_author_books_url_sorts():
    assert author_books_url(58) == ("https://www.goodreads.com/author/list/58?page=1&per_page=30")
    assert author_books_url(58, page=2, sort="published").endswith(
        "?page=2&per_page=30&sort=original_publication_year"
    )
    with pytest.raises(ValueError, match="unknown sort"):
        author_books_url(58, sort="newest")


def test_shelf_slugs():
    assert shelf_slug("Science Fiction") == "science-fiction"
    assert shelf_slug("https://www.goodreads.com/shelf/show/historical-fiction") == (
        "historical-fiction"
    )
    assert shelf_slug("https://www.goodreads.com/genres/fantasy") == "fantasy"
    assert shelf_url("young-adult") == "https://www.goodreads.com/shelf/show/young-adult"
    with pytest.raises(ValueError):
        shelf_slug("sci/fi?")


def test_absolute():
    assert absolute("/book/show/1") == "https://www.goodreads.com/book/show/1"
    assert absolute("//images.example/x.jpg") == "https://images.example/x.jpg"
    assert absolute("https://x.example/") == "https://x.example/"
    assert absolute(None) is None
