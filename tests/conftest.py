"""Offline fixtures: small Goodreads pages shaped like the real ones, and a fake SDK client.

No test touches the network or spends API credit.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import pytest

from goodreads_scraper import GoodreadsScraper

# --------------------------------------------------------------------------- #
# Search results (React Server Components payload)
# --------------------------------------------------------------------------- #

AUTHOR_NODE = {
    "__typename": "Contributor",
    "legacyId": 58,
    "name": "Frank Herbert",
    "webUrl": "https://www.goodreads.com/author/show/58.Frank_Herbert",
    "isGrAuthor": False,
    "followers": {"__typename": "ContributorFollowersConnection", "totalCount": 17573},
    "works": {"__typename": "ContributorWorksConnection", "totalCount": 634},
    "profileImageUrl": "https://images.example/authors/58.jpg",
}


def _search_book(
    legacy_id: int,
    title: str,
    work_id: int,
    *,
    node: Any = None,
    series: Any = None,
    rating: float = 4.0,
    ratings: int = 100,
) -> dict[str, Any]:
    return {
        "__typename": "Book",
        "details": {"__typename": "BookDetails", "publicationTime": 1569913200000},
        "id": f"kca://book/{legacy_id}",
        "legacyId": legacy_id,
        "title": title,
        "imageUrl": f"https://images.example/books/{legacy_id}.jpg",
        "webUrl": f"https://www.goodreads.com/book/show/{legacy_id}-slug",
        "description": "First line.<br /><br />Second <i>line</i>.",
        "bookSeries": series or [],
        "primaryContributorEdge": {
            "__typename": "BookContributorEdge",
            "node": node if node is not None else AUTHOR_NODE,
            "role": "Author",
        },
        "secondaryContributorEdges": [
            {
                "__typename": "BookContributorEdge",
                "node": {
                    "name": "Brian Herbert",
                    "webUrl": "https://www.goodreads.com/author/show/56.Brian_Herbert",
                },
                "role": "Introduction",
            }
        ],
        "work": {
            "__typename": "Work",
            "details": {"__typename": "WorkDetails", "booksCount": 540},
            "legacyId": work_id,
            "stats": {
                "__typename": "BookOrWorkStats",
                "averageRating": rating,
                "ratingsCount": ratings,
                "textReviewsCount": ratings // 10,
            },
        },
        "links": {"primaryAffiliateLink": {"name": "Amazon", "ebookPrice": "9.99"}},
    }


def _element(props: dict[str, Any]) -> list[Any]:
    return ["$", "div", None, props]


def push_scripts(payload: str, parts: int = 2) -> str:
    """``self.__next_f.push`` scripts carrying ``payload``, split across ``parts``."""
    size = max(1, len(payload) // parts + 1)
    chunks = [payload[i : i + size] for i in range(0, len(payload), size)]
    scripts = "".join(
        f"<script>self.__next_f.push([1,{json.dumps(chunk)}])</script>\n" for chunk in chunks
    )
    return "<script>self.__next_f.push([0])</script>\n" + scripts


def search_html(
    books: list[dict[str, Any]] | None = None, total: str = "108k", first: int = 1
) -> str:
    """A search page: the books (positions 1..n) plus rows that the books reference."""
    books = books if books is not None else default_search_books()
    rows: list[str] = []
    rows.append('0:["$","html",null,{"children":"$L1"}]')
    rows.append("7:" + json.dumps({"node": AUTHOR_NODE}))
    series = {
        "__typename": "Series",
        "title": "Dune",
        "webUrl": "https://www.goodreads.com/series/45935-dune",
    }
    rows.append("8:" + json.dumps(_element({"series": series})))
    text = "var x = 1;\nconsole.log('row with a newline: é');"
    rows.append(f"9:T{len(text.encode('utf-8')):x},{text}")
    items = []
    for position, book in enumerate(books, start=1):
        wrapper = {"position": position, "tab": "books", "children": _element({"book": book})}
        items.append(["$", "li", f"k{position}", {"children": ["$", "$L5", None, wrapper]}])
    rows.append("1:" + json.dumps(["$", "ul", None, {"children": items}]))
    last = first + len(books) - 1
    showing = ["Showing ", first, "-", last, " of over ", total, " results"]
    rows.append("a:" + json.dumps(["$", "span", None, {"children": showing}]))
    payload = "\n".join(rows) + "\n"
    return (
        "<html><head><title>Book search results | Goodreads</title></head><body>"
        + push_scripts(payload)
        + "</body></html>"
    )


def default_search_books() -> list[dict[str, Any]]:
    dune = _search_book(
        44767458,
        "Dune",
        3634639,
        series=[{"__typename": "BookSeries", "seriesPlacement": "1", "series": "$8:props:series"}],
        rating=4.29,
        ratings=1717579,
    )
    messiah = _search_book(
        44492285, "Dune Messiah", 3634570, node="$7:node", rating=3.9, ratings=449303
    )
    other_edition = _search_book(1111, "Dune (Illustrated)", 3634639, rating=4.29, ratings=1717579)
    return [dune, messiah, other_edition]


# --------------------------------------------------------------------------- #
# Review cards
# --------------------------------------------------------------------------- #


def review_card(
    review_id: int,
    reviewer: str,
    *,
    rating: str | None = "Rating 4 out of 5",
    date: str = "December 5, 2006",
    text: str = "Loved it.<br/><br/>Would read again.",
    author: bool = False,
    likes: str = "125 likes",
    spoiler: bool = False,
) -> str:
    stars = (
        f'<span aria-label="{rating}" class="RatingStars RatingStars__small" role="img"></span>'
        if rating
        else '<div aria-hidden="true" class="BookRatingStarsSkeleton"></div>'
    )
    meta = (
        "<span>Author</span><span>3 books</span><span><span>2,052 followers</span></span>"
        if author
        else "<span>771 reviews</span><span><span>29.1k followers</span></span>"
    )
    hidden = (
        '<input class="spoiler__control" type="checkbox"/><label class="spoiler">secret</label>'
        if spoiler
        else ""
    )
    return f"""
    <article aria-label="Review by {reviewer}" class="ReviewCard">
      <div class="ReviewCard__profile"><div class="ReviewerProfile">
        <section class="ReviewerProfile__info">
          <span class="Text"><div class="ReviewerProfile__name" data-testid="name">
            <a href="https://www.goodreads.com/user/show/{review_id + 7}-{reviewer.lower()}">
              {reviewer}
            </a>
          </div></span>
          <span class="Text"><div class="ReviewerProfile__meta">{meta}</div></span>
        </section>
      </div></div>
      <section class="ReviewCard__content">
        <section class="ReviewCard__row">
          <div class="ShelfStatus">{stars}</div>
          <span class="Text"><a href="https://www.goodreads.com/review/show/{review_id}">
            {date}
          </a></span>
        </section>
        <section class="ReviewText"><section class="ReviewText__content">
          <div class="TruncatedContent"><div class="TruncatedContent__text">
            <span class="Formatted">{text}{hidden}</span>
          </div></div>
        </section></section>
        <section class="ReviewCard__tags"><ul>
          <a class="Button Button--tag" href="/review/list/5?shelf=fiction">
            <span class="Button__labelItem">fiction</span></a>
          <a class="Button Button--tag" href="/review/list/5?shelf=sci-fi">
            <span class="Button__labelItem">sci-fi</span></a>
        </ul></section>
        <footer class="SocialFooter"><div data-testid="stats">
          <div class="Button__container"><button><span class="Button__labelItem">
            {likes}</span></button></div>
          <div class="Button__container"><button><span class="Button__labelItem">
            31 comments</span></button></div>
        </div></footer>
      </section>
    </article>"""


def reviews_html(
    first: int = 1,
    total: str = "89,855",
    cards: list[str] | None = None,
    filters: list[str] | None = None,
    state: dict[str, Any] | None = None,
) -> str:
    cards = (
        cards
        if cards is not None
        else [review_card(first * 1000 + i, f"Reader{first + i}") for i in range(30)]
    )
    last = first + len(cards) - 1
    chips = "".join(
        f'<div class="ReviewFilters__filterButton"><button>'
        f'<span class="Button__labelItem">{name}</span></button></div>'
        for name in filters or []
    )
    data = ""
    if state is not None:
        data = (
            '<script id="__NEXT_DATA__" type="application/json">'
            + json.dumps({"props": {"pageProps": {"apolloState": state}}})
            + "</script>"
        )
    return f"""<html><body>
    <div class="ReviewFilters__appliedFilters" data-testid="appliedFilters">{chips}</div>
    <div class="ReviewsList">
      <div class="ReviewsList__listContext"><span>
        Displaying {first} - {last} of {total} reviews
      </span></div>
      {"".join(cards)}
    </div>{data}</body></html>"""


def empty_reviews_html() -> str:
    return """<html><body><div data-testid="appliedFilters" class="ReviewFilters__appliedFilters">
    <div class="ReviewFilters__filterButton"><button><span class="Button__labelItem">
    Mentions: xyz</span></button></div></div>
    <div class="ReviewsList"><div class="Alert"><div class="ErrorCard" data-testid="error-card">
    There are 0 reviews and 1717579 ratings matching your filters.</div></div></div>
    </body></html>"""


# --------------------------------------------------------------------------- #
# Book page (Apollo cache in __NEXT_DATA__)
# --------------------------------------------------------------------------- #

BOOK_KEY = "Book:kca://book/amzn1.gr.book.v1.dune"


def book_state(review_ids: tuple[int, ...] = (156120010, 554)) -> dict[str, Any]:
    state: dict[str, Any] = {
        "ROOT_QUERY": {
            "__typename": "Query",
            'getBookByLegacyId({"legacyId":"44767458"})': {"__ref": BOOK_KEY},
            "getReviews": {"__typename": "BookReviewsConnection", "totalCount": 89855},
            'getSocialSignals({"bookId":"x","shelfStatus":["CURRENTLY_READING","TO_READ"]})': [
                {"__typename": "SocialSignal", "name": "CURRENTLY_READING", "count": 155686},
                {"__typename": "SocialSignal", "name": "TO_READ", "count": 1441407},
            ],
        },
        BOOK_KEY: {
            "__typename": "Book",
            "legacyId": 44767458,
            "webUrl": "https://www.goodreads.com/book/show/44767458-dune",
            "title": "Dune",
            "titleComplete": "Dune (Dune, #1)",
            "description": "Set on the desert planet Arrakis.<br /><br />A <i>classic</i>.",
            "primaryContributorEdge": {
                "node": {"__ref": "Contributor:frank"},
                "role": "Author",
            },
            "secondaryContributorEdges": [
                {"node": {"__ref": "Contributor:brian"}, "role": "Introduction"}
            ],
            "imageUrl": "https://images.example/books/44767458.jpg",
            "bookSeries": [
                {"userPosition": "1", "series": {"__ref": "Series:dune"}},
            ],
            "bookGenres": [
                {"genre": {"name": "Science Fiction"}},
                {"genre": {"name": "Classics"}},
            ],
            "details": {
                "asin": "059309932X",
                "format": "Hardcover",
                "numPages": 658,
                "publicationTime": 1569913200000,
                "publisher": "Ace",
                "isbn": "059309932X",
                "isbn13": "9780593099322",
                "language": {"name": "English"},
            },
            "work": {"__ref": "Work:dune"},
            "links": {"primaryAffiliateLink": {"ebookPrice": "9.99"}},
        },
        "Contributor:frank": dict(AUTHOR_NODE),
        "Contributor:brian": {
            "legacyId": 56,
            "name": "Brian Herbert",
            "webUrl": "https://www.goodreads.com/author/show/56.Brian_Herbert",
        },
        "Series:dune": {"title": "Dune", "webUrl": "https://www.goodreads.com/series/45935-dune"},
        "Work:dune": {
            "legacyId": 3634639,
            "details": {
                "originalTitle": "Dune",
                "publicationTime": -144694800000,
                "awardsWon": [
                    {
                        "name": "Hugo Award",
                        "webUrl": "https://www.goodreads.com/award/show/9-hugo-award",
                        "awardedAt": -126201600000,
                        "category": "Best Novel",
                        "designation": "WINNER",
                    }
                ],
                "places": [{"name": "Arrakis"}],
                "characters": [{"name": "Paul Atreides"}, {"name": "Stilgar"}],
            },
            "stats": {
                "averageRating": 4.29,
                "ratingsCount": 1717579,
                "ratingsCountDist": [26182, 56084, 206414, 528033, 900866],
                "textReviewsCount": 90085,
                "textReviewsLanguageCounts": [
                    {"count": 406, "isoLanguageCode": "de"},
                    {"count": 75440, "isoLanguageCode": "en"},
                ],
            },
            'quotes({"pagination":{"limit":1}})': {"totalCount": 1457},
            'questions({"pagination":{"limit":1}})': {"totalCount": 78},
            'topics({"pagination":{"limit":1}})': {"totalCount": 405},
            "editions": {"webUrl": "https://www.goodreads.com/work/editions/3634639"},
        },
    }
    for review_id in review_ids:
        key = f"Review:{review_id}"
        state[key] = {
            "__typename": "Review",
            "creator": {"__ref": f"User:{review_id}"},
            "createdAt": 1300860593000,
            "spoilerStatus": False,
            "rating": 5,
            "preciseRating": 5,
            "likeCount": 3071,
            "commentCount": 116,
            "shelving": {"__ref": f"Shelving:{review_id}"},
        }
        state[f"Shelving:{review_id}"] = {
            "webUrl": f"https://www.goodreads.com/review/show/{review_id}"
        }
        state[f"User:{review_id}"] = {"followersCount": 29123, "textReviewsCount": 771}
    return state


def book_html(state: dict[str, Any] | None = None, cards: list[str] | None = None) -> str:
    state = state if state is not None else book_state()
    cards = (
        cards
        if cards is not None
        else [
            review_card(156120010, "Rajat", rating=None, author=True),
            review_card(554, "Elizabeth", rating="Rating 1 out of 5", spoiler=True),
        ]
    )
    data = json.dumps(
        {"page": "/book/show/[book_id]", "props": {"pageProps": {"apolloState": state}}}
    )
    return (
        "<html><head><title></title></head><body>"
        + "".join(cards)
        + '<script id="__NEXT_DATA__" type="application/json">'
        + data
        + "</script></body></html>"
    )


def missing_book_html() -> str:
    state = {"ROOT_QUERY": {"__typename": "Query", "getSiteHeaderBanner": {}}}
    return book_html(state=state, cards=[])


# --------------------------------------------------------------------------- #
# Classic HTML pages
# --------------------------------------------------------------------------- #


def book_row(
    book: int,
    title: str,
    *,
    rank: int | None = None,
    extra: str = "",
    second_author: bool = False,
) -> str:
    number = f'<td class="number" valign="top">{rank}</td>' if rank is not None else ""
    co = (
        """<div class="authorName__container">
        <a class="authorName" href="https://www.goodreads.com/author/show/56.Brian_Herbert">
        <span itemprop="name">Brian Herbert</span></a>
        <span class="authorName greyText smallText role">(Introduction)</span></div>"""
        if second_author
        else ""
    )
    return f"""
    <tr itemscope itemtype="http://schema.org/Book">
      {number}
      <td><a href="/book/show/{book}-slug" title="{title}">
        <img class="bookCover" itemprop="image"
             src="https://i.gr-assets.com/books/1586722975i/{book}._SX50_.jpg"/></a></td>
      <td>
        <a class="bookTitle" href="/book/show/{book}-slug" itemprop="url">
          <span itemprop="name" role="heading">{title}</span></a><br/>
        <span class="by">by</span>
        <span itemprop="author"><div class="authorName__container">
          <a class="authorName" href="https://www.goodreads.com/author/show/153394.Suzanne_Collins">
            <span itemprop="name">Suzanne Collins</span></a>,</div>{co}</span><br/>
        <div><span class="greyText smallText uitext">
          <span class="minirating"><span class="stars"></span>
            4.36 avg rating &mdash; 10,313,973 ratings</span>
          {extra}
        </span></div>
      </td>
      <td><form><input name="authenticity_token" value="abc"/>
        <button><span>Want to Read</span></button></form></td>
    </tr>"""


def list_html(page: int = 1, last_page: int = 3, rows: list[str] | None = None) -> str:
    rows = (
        rows
        if rows is not None
        else [
            book_row(
                2767052,
                "The Hunger Games (The Hunger Games, #1)",
                rank=(page - 1) * 100 + 1,
                extra="""<div><span class="smallText uitext"><a href="#">score: 4,558,374</a>,
            <span class="greyText">and</span> <a href="#">46,319 people voted</a></span></div>""",
            ),
            book_row(
                1885,
                "Pride and Prejudice",
                rank=(page - 1) * 100 + 2,
                extra="<div><a>score: 3,091,203</a> <a>1 person voted</a></div>",
            ),
        ]
    )
    links = "".join(
        f'<a href="/list/show/1.Best?page={n}">{n}</a>' for n in range(1, last_page + 1)
    )
    nxt = (
        f'<a class="next_page" href="/list/show/1.Best?page={page + 1}" rel="next">Next</a>'
        if page < last_page
        else '<span class="next_page disabled">Next</span>'
    )
    return f"""<html><head><title>
      Best Books Ever (79754 books)
    </title></head><body>
    <div class="leftContainer">
      <h1>Score</h1><p>A book's total score is based on how highly those voters ranked it.</p>
      <div class="u-paddingBottomMedium mediumText">
        The best books ever, as voted on by the general Goodreads community.<br/><br/>
        Note to librarians.
        <div class="right"><a class="flag" href="/flagged">flag</a></div>
      </div>
      <table class="tableList">{"".join(rows)}</table>
      <div class="pagination">{links}{nxt}</div>
      <div class="stacked">
        <div>
          79,754 books &middot;
          297,180 voters &middot;
          list created May 13th, 2008
          by <a href="/user/show/73-michael-economy">Michael Economy</a>
          <a href="/list/user_vote/1">(votes)</a>.
        </div>
        <div>Tags: <a href="/list/show_tag/best">best</a>,
          <a href="/list/show_tag/fiction">fiction</a></div>
      </div>
    </div></body></html>"""


def author_html() -> str:
    return f"""<html><head>
    <link href="https://www.goodreads.com/author/show/58.Frank_Herbert" rel="canonical"/>
    </head><body>
    <div class="leftContainer">
      <img alt="Frank Herbert" itemprop="image" src="https://images.example/authors/58.jpg"/>
    </div>
    <div class="rightContainer">
      <div><h1 class="authorName"><span itemprop="name">Frank Herbert</span></h1></div>
      <br class="clear"/>
      <div class="dataTitle">Born</div>
      in Tacoma, Washington, The United States
      <div class="dataItem" itemprop="birthDate">October 08, 1920</div>
      <br class="clear"/>
      <div class="dataTitle">Died</div>
      <div class="dataItem" itemprop="deathDate">February 11, 1986</div>
      <br class="clear"/>
      <div class="dataTitle">Website</div>
      <div class="dataItem"><a href="http://www.dunenovels.com/">http://www.dunenovels.com/</a></div>
      <br class="clear"/>
      <div class="dataTitle">Twitter</div>
      <div class="dataItem"><a href="https://twitter.com/dune">dune</a></div>
      <br class="clear"/>
      <div class="dataTitle">Genre</div>
      <div class="dataItem"><a href="/genres/science-fiction">Science Fiction</a>,
        <a href="/genres/fantasy">Fantasy</a></div>
      <br class="clear"/>
      <div class="dataTitle">Influences</div>
      <div class="dataItem"><a href="/author/show/1">Isaac Asimov</a></div>
      <br class="clear"/>
      <div class="dataTitle">Member Since</div>
      <div class="dataItem">January 2010</div>
      <br class="clear"/>
      <div class="aboutAuthorInfo">
        <span id="freeTextContainerauthor58">Short bio...</span>
        <span id="freeTextauthor58" style="display:none">Full bio of
          <i>Dune</i>'s author.<br/><br/>Second paragraph.</span>
      </div>
      <div class="hreview-aggregate">
        <span class="rating">Average rating: <span class="average">4.14</span></span>
        <span class="votes"><span content="2965839" itemprop="ratingCount">2,965,839</span></span>
        <span class="count"><span content="161830" itemprop="reviewCount">161,830</span></span>
        <a href="/author/list/58.Frank_Herbert">636 distinct works</a>
      </div>
      <table class="stacked tableList">
        {book_row(44767458, "Dune (Dune, #1)", extra="published 1965 &mdash; 3 editions")}
      </table>
    </div></body></html>"""


def author_books_html(page: int = 1, last_page: int = 2) -> str:
    nxt = (
        f'<a class="next_page" href="/author/list/58?page={page + 1}" rel="next">next</a>'
        if page < last_page
        else ""
    )
    links = "".join(f'<a href="/author/list/58?page={n}">{n}</a>' for n in range(1, last_page + 1))
    rows = [
        book_row(
            44492285 + page,
            f"Dune Messiah {page} (Dune, #2)",
            second_author=True,
            extra="&mdash; published 1969 &mdash; 275 editions",
        ),
        book_row(
            93450 + page, f"Direct Descent {page}", extra="published 1980 &mdash; 19 editions"
        ),
    ]
    return f"""<html><body><div class="leftContainer">
      <h1>Books by Frank Herbert</h1>
      <table class="tableList">{"".join(rows)}</table>
      <div><a class="previous_page" href="#">previous</a>{links}{nxt}</div>
    </div></body></html>"""


def shelf_html() -> str:
    row = """<div class="elementList">
      <div class="left">
        <a class="leftAlignedImage" href="/book/show/44767458-dune">
          <img src="https://i.gr-assets.com/books/1555447414l/44767458._SY75_.jpg"/></a>
        <a class="bookTitle" href="/book/show/44767458-dune">Dune (Dune, #1)</a><br/>
        <span class="by">by</span>
        <span itemprop="author"><div class="authorName__container">
          <a class="authorName" href="https://www.goodreads.com/author/show/58.Frank_Herbert">
            <span itemprop="name">Frank Herbert</span></a></div></span>
        (shelved 22035 times as <em>science-fiction</em>)<br/>
        <span class="greyText smallText">avg rating 4.29 &mdash; 1,717,578 ratings &mdash;
          published 1965</span>
      </div></div>"""
    video = """<div class="elementList"><a class="videoTitle" href="/videos/1">Trailer</a></div>"""
    return f"""<html><body><div class="leftContainer"><h1>Science Fiction Books</h1>
      {row}{video}</div></body></html>"""


# --------------------------------------------------------------------------- #
# Fake SDK client
# --------------------------------------------------------------------------- #


class TargetNotFoundError(Exception):
    """Stands in for the SDK's 404 error (matched by class name)."""


class StepFailedError(Exception):
    """Stands in for the SDK's failed-browser-step error."""

    def __init__(self, step_index: int, html: str = "") -> None:
        super().__init__(f"Browser step {step_index} failed")
        self.step_index = step_index
        self.html = html


class FakeClient:
    """Answers ``get_page_source`` from a handler and records every call."""

    def __init__(self, handler: Callable[[str, dict[str, Any]], Any]) -> None:
        self.handler = handler
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def get_page_source(self, url: str, **options: Any) -> str:
        self.calls.append((url, options))
        result = self.handler(url, options)
        if isinstance(result, BaseException):
            raise result
        return result


def sequence(*responses: Any) -> Callable[[str, dict[str, Any]], Any]:
    """A handler returning the given responses in order (the last one repeats)."""
    queue = list(responses)

    def handler(url: str, options: dict[str, Any]) -> Any:
        return queue.pop(0) if len(queue) > 1 else queue[0]

    return handler


@pytest.fixture
def make_scraper() -> Callable[..., tuple[GoodreadsScraper, FakeClient]]:
    def build(handler: Callable[[str, dict[str, Any]], Any], **options: Any):
        client = FakeClient(handler)
        options.setdefault("sleep", lambda seconds: None)
        options.setdefault("transient_errors", (TimeoutError,))
        return GoodreadsScraper(client=client, **options), client

    return build
