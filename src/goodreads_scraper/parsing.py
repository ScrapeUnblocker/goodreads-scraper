"""Turn Goodreads pages (HTML from the ScrapeUnblocker ``getPageSource`` API) into records.

Goodreads is three generations of site in one, and each page type is read from
where its data actually lives:

* search results - the React Server Components payload (``self.__next_f``),
  which carries the same book objects the Goodreads app renders;
* book pages - the Apollo cache in ``__NEXT_DATA__`` (book, work, contributors,
  series, social signals), plus the review cards in the page;
* review pages - the rendered review cards (after the browser steps ran);
* Listopia lists, author pages, author book lists and shelves - classic HTML.

All parsers are pure functions of the HTML, so they are easy to test offline.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from typing import Any

from bs4 import BeautifulSoup, NavigableString, Tag

from .models import (
    Author,
    AuthorBooksPage,
    Award,
    Book,
    BookDetails,
    BookRow,
    Contributor,
    ListPage,
    Review,
    ReviewPage,
    SearchPage,
    SeriesRef,
    ShelfPage,
)
from .urls import SEARCH_PAGE_SIZE, absolute, book_id


class GoodreadsError(Exception):
    """Base class for scraper errors."""


class GoodreadsNotFoundError(GoodreadsError):
    """Goodreads has no such book, author, list or shelf (or page of it)."""


class GoodreadsParseError(GoodreadsError):
    """The page came back without the content we expected (worth a retry)."""


# --------------------------------------------------------------------------- #
# Small value helpers
# --------------------------------------------------------------------------- #

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_COUNT = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*([kKmM](?![a-zA-Z]))?")
_ORDINAL = re.compile(r"(\d+)(?:st|nd|rd|th)", re.I)
_DATE_FORMATS = (
    ("%B %d %Y", "%Y-%m-%d"),
    ("%b %d %Y", "%Y-%m-%d"),
    ("%B %Y", "%Y-%m"),
    ("%b %Y", "%Y-%m"),
    ("%Y", "%Y"),
)
_SIZE_SUFFIX = re.compile(r"\._[A-Za-z0-9,_]+_(?=\.(?:jpe?g|png|gif|webp)$)", re.I)
_SERIES_SUFFIX = re.compile(r"^(?P<title>.+?)\s*\((?P<series>[^()]+?),?\s*#(?P<pos>[^()]+)\)$")
_BLOCK_TAGS = {"p", "div", "li", "blockquote", "h1", "h2", "h3", "h4", "h5", "h6"}


def parse_count(value: Any) -> int | None:
    """A count as Goodreads prints it: ``"1,717,578"`` -> 1717578, ``"29.1k"`` -> 29100."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    match = _COUNT.search(str(value))
    if not match:
        return None
    number = float(match.group(1).replace(",", ""))
    number *= {"k": 1_000, "m": 1_000_000}.get((match.group(2) or "").lower(), 1)
    return int(round(number))


def parse_float(value: Any) -> float | None:
    """The first decimal number in a string (``"4.36 avg rating"`` -> 4.36)."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"\d+(?:\.\d+)?", str(value).replace(",", ""))
    return float(match.group(0)) if match else None


def parse_date(text: str | None) -> str | None:
    """``"December 5, 2006"`` -> ``"2006-12-05"``; ``"January 2010"`` -> ``"2010-01"``."""
    if not text:
        return None
    clean = " ".join(_ORDINAL.sub(r"\1", text).replace(",", " ").split())
    for pattern, out in _DATE_FORMATS:
        try:
            return datetime.strptime(clean, pattern).strftime(out)
        except ValueError:
            continue
    return None


def ms_to_date(value: Any) -> str | None:
    """A Goodreads timestamp (milliseconds since 1970, may be negative) as a date."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return (_EPOCH + timedelta(milliseconds=float(value))).date().isoformat()
    except (TypeError, ValueError, OverflowError):
        return None


def full_size(url: str | None) -> str | None:
    """Drop the thumbnail size suffix from a Goodreads image URL (``._SX50_``)."""
    return _SIZE_SUFFIX.sub("", url) if url else url


def split_series(title: str) -> tuple[str, str | None, str | None]:
    """``"Dune (Dune, #1)"`` -> ``("Dune", "Dune", "1")``."""
    match = _SERIES_SUFFIX.match(title.strip())
    if not match:
        return title.strip(), None, None
    return match.group("title").strip(), match.group("series").strip(), match.group("pos").strip()


def node_text(node: Tag | None) -> str:
    """The text of an element: ``<br>`` and blocks become line breaks, other
    whitespace collapses (the API may return pretty-printed HTML)."""
    if node is None:
        return ""
    chunks: list[str] = []
    for item in node.descendants:
        if isinstance(item, Tag):
            if item.name == "br" or item.name in _BLOCK_TAGS:
                chunks.append("\n")
        elif type(item) is NavigableString:
            chunks.append(re.sub(r"\s+", " ", str(item)))
    lines = [" ".join(line.split()) for line in "".join(chunks).split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def html_to_text(html: str | None) -> str | None:
    """Plain text from an HTML fragment (book descriptions, author bios)."""
    if not html:
        return None
    return node_text(BeautifulSoup(html, "html.parser")) or None


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html or "", "html.parser")


def _int_from(pattern: str, text: str) -> int | None:
    match = re.search(pattern, text, re.I)
    return parse_count(match.group(1)) if match else None


def _id_in(pattern: str, href: str | None) -> int | None:
    match = re.search(pattern, href or "")
    return int(match.group(1)) if match else None


# --------------------------------------------------------------------------- #
# Embedded JSON
# --------------------------------------------------------------------------- #

_FLIGHT_MARK = "self.__next_f.push([1,"
_NEXT_DATA = re.compile(r"<script[^>]*id=\"__NEXT_DATA__\"[^>]*>(.*?)</script>", re.S)


def flight_text(html: str) -> str:
    """The React Server Components payload of a page (``self.__next_f.push`` chunks)."""
    decoder = json.JSONDecoder()
    chunks: list[str] = []
    start = html.find(_FLIGHT_MARK)
    while start != -1:
        try:
            chunk, end = decoder.raw_decode(html, start + len(_FLIGHT_MARK))
        except ValueError:
            start = html.find(_FLIGHT_MARK, start + 1)
            continue
        if isinstance(chunk, str):
            chunks.append(chunk)
        start = html.find(_FLIGHT_MARK, end)
    return "".join(chunks)


_ROW_ID = re.compile(r"([0-9a-f]+):")
_REF = re.compile(r"^\$L?([0-9a-f]+)(?::(.+))?$")
_ELEMENT_KEYS = {"type": 1, "key": 2, "props": 3}


def _skip_utf8(text: str, start: int, size: int) -> int:
    """The index ``size`` UTF-8 bytes after ``start`` (text rows count bytes)."""
    position, counted = start, 0
    while counted < size and position < len(text):
        counted += len(text[position].encode("utf-8"))
        position += 1
    return position


def flight_rows(payload: str) -> dict[str, Any]:
    """Split a React Server Components payload into its rows: ``{row id: value}``."""
    decoder = json.JSONDecoder()
    rows: dict[str, Any] = {}
    position, size = 0, len(payload)
    while position < size:
        if payload[position] == "\n":
            position += 1
            continue
        match = _ROW_ID.match(payload, position)
        if match:
            key, position = match.group(1), match.end()
            if payload.startswith("T", position):  # T<hex byte length>,<text>
                comma = payload.find(",", position)
                try:
                    length = int(payload[position + 1 : comma], 16)
                except ValueError:
                    length = -1
                if comma != -1 and length >= 0:
                    end = _skip_utf8(payload, comma + 1, length)
                    rows[key] = payload[comma + 1 : end]
                    position = end
                    continue
            while position < size and payload[position].isupper():  # I[...], HL[...], E{...}
                position += 1
            try:
                rows[key], position = decoder.raw_decode(payload, position)
                continue
            except ValueError:
                pass
        newline = payload.find("\n", position)
        if newline == -1:
            break
        position = newline + 1
    return rows


def _follow(value: Any, rows: dict[str, Any], depth: int = 0) -> Any:
    """Follow a ``$<row>`` / ``$L<row>`` / ``$<row>:<path>`` reference to its value."""
    if depth > 40 or not isinstance(value, str):
        return value
    match = _REF.match(value)
    if not match or match.group(1) not in rows:
        return None if value == "$undefined" else value
    target = _follow(rows[match.group(1)], rows, depth + 1)
    for key in (match.group(2) or "").split(":") if match.group(2) else []:
        target = _follow(target, rows, depth + 1)
        if isinstance(target, list):
            if len(target) == 4 and target[0] == "$" and key in _ELEMENT_KEYS:
                target = target[_ELEMENT_KEYS[key]]
            elif key.isdigit() and int(key) < len(target):
                target = target[int(key)]
            else:
                return None
        elif isinstance(target, dict):
            target = target.get(key)
        else:
            return None
    return _follow(target, rows, depth + 1)


def _resolve(value: Any, rows: dict[str, Any], depth: int = 0) -> Any:
    """``value`` with every row reference inside it replaced by what it points to."""
    if depth > 40:
        return value
    if isinstance(value, str):
        followed = _follow(value, rows)
        return value if followed is value else _resolve(followed, rows, depth + 1)
    if isinstance(value, list):
        return [_resolve(item, rows, depth + 1) for item in value]
    if isinstance(value, dict):
        return {key: _resolve(item, rows, depth + 1) for key, item in value.items()}
    return value


def _find_books(value: Any, position: int | None = None) -> Iterator[tuple[int | None, dict]]:
    """Book objects in a payload tree, with the result position the page gives them."""
    if isinstance(value, dict):
        if isinstance(value.get("position"), int) and "tab" in value:
            position = value["position"]
        if value.get("__typename") == "Book" and value.get("legacyId") and value.get("title"):
            yield position, value
            return
        for item in value.values():
            yield from _find_books(item, position)
    elif isinstance(value, list):
        for item in value:
            yield from _find_books(item, position)


def next_data(html: str) -> dict[str, Any] | None:
    """The ``__NEXT_DATA__`` JSON of a page, or ``None``."""
    match = _NEXT_DATA.search(html or "")
    if not match:
        return None
    try:
        data = json.loads(match.group(1))
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _merge(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge(base[key], value)
        elif base.get(key) in (None, "", [], {}):
            base[key] = value
    return base


def _dig(data: Any, *path: str) -> Any:
    for key in path:
        if not isinstance(data, dict):
            return None
        data = data.get(key)
    return data


def _contributor(edge: dict[str, Any], resolve: Any = None) -> Contributor | None:
    node = edge.get("node") or {}
    if resolve is not None:
        node = resolve(node)
    name = node.get("name")
    if not name:
        return None
    return Contributor(
        name=name,
        role=edge.get("role") or None,
        author_id=node.get("legacyId") or _id_in(r"/author/show/(\d+)", node.get("webUrl")),
        url=node.get("webUrl"),
        followers=_dig(node, "followers", "totalCount"),
        works_count=_dig(node, "works", "totalCount"),
        goodreads_author=node.get("isGrAuthor"),
        image=node.get("profileImageUrl"),
    )


def _price(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", ""))
    except ValueError:
        return None


# --------------------------------------------------------------------------- #
# Search results
# --------------------------------------------------------------------------- #

_SHOWING = re.compile(
    r'"Showing ",\s*(\d+),\s*"-",\s*(\d+),\s*" of ([^"]*)",\s*"([^"]+)",\s*" results?"'
)


def _search_book(raw: dict[str, Any]) -> Book:
    edges = [raw.get("primaryContributorEdge") or {}, *(raw.get("secondaryContributorEdges") or [])]
    contributors = [c for c in (_contributor(edge) for edge in edges if edge) if c]
    primary = contributors[0] if contributors else None
    work = raw.get("work") or {}
    stats = work.get("stats") or {}
    book_number = int(raw["legacyId"])
    return Book(
        book_id=book_number,
        title=raw.get("title") or "",
        url=raw.get("webUrl") or absolute(f"/book/show/{book_number}") or "",
        author=primary.name if primary else None,
        author_id=primary.author_id if primary else None,
        author_url=primary.url if primary else None,
        author_followers=primary.followers if primary else None,
        author_works=primary.works_count if primary else None,
        contributors=contributors,
        series=[
            SeriesRef(
                title=_dig(entry, "series", "title") or "",
                position=entry.get("seriesPlacement") or entry.get("userPosition"),
                url=_dig(entry, "series", "webUrl"),
            )
            for entry in raw.get("bookSeries") or []
            if _dig(entry, "series", "title")
        ],
        work_id=work.get("legacyId"),
        average_rating=stats.get("averageRating"),
        ratings_count=stats.get("ratingsCount"),
        reviews_count=stats.get("textReviewsCount"),
        editions_count=_dig(work, "details", "booksCount"),
        publication_date=ms_to_date(_dig(raw, "details", "publicationTime")),
        description=html_to_text(raw.get("description")),
        cover=raw.get("imageUrl"),
        kindle_price=_price(_dig(raw, "links", "primaryAffiliateLink", "ebookPrice")),
    )


def parse_search_page(html: str, query: str, page: int, url: str) -> SearchPage:
    """Parse one page of Goodreads book search results (20 books)."""
    payload = flight_text(html)
    if not payload:
        raise GoodreadsParseError(f"the search page came back without its data: {url}")
    rows = flight_rows(payload)
    merged: dict[int, dict[str, Any]] = {}
    positions: dict[int, int] = {}
    for row in rows.values():
        for position, raw in _find_books(row):
            key = int(raw["legacyId"])
            raw = _resolve(raw, rows)
            if key in merged:
                _merge(merged[key], raw)
            else:
                merged[key] = raw
            if position is not None:
                positions.setdefault(key, position)
    seen = {key: index for index, key in enumerate(merged)}
    order = sorted(merged, key=lambda k: (positions.get(k, 10**6), seen[k]))
    books = []
    for index, key in enumerate(order):
        book = _search_book(merged[key])
        book.position = (page - 1) * SEARCH_PAGE_SIZE + index + 1
        book.page = page
        book.query = query
        books.append(book)
    total = None
    showing = _SHOWING.search(payload)
    if showing:
        total = parse_count(showing.group(4))
    return SearchPage(
        query=query,
        page=page,
        url=url,
        books=books,
        total_results=total,
        has_next=len(books) >= SEARCH_PAGE_SIZE,
    )


# --------------------------------------------------------------------------- #
# Reviews
# --------------------------------------------------------------------------- #

_DISPLAYING = re.compile(r"Displaying\s+([\d,]+)\s*-\s*([\d,]+)\s+of\s+([\d,]+)\s+reviews?", re.I)
_NO_MATCH = re.compile(r"There are\s+([\d,]+)\s+reviews?", re.I)


def parse_review_card(card: Tag) -> Review:
    """One ``article.ReviewCard``."""
    link = card.select_one('a[href*="/review/show/"]')
    href = link.get("href") if link else None
    name_link = card.select_one('[data-testid="name"] a')
    stars = card.select_one('.ShelfStatus [aria-label^="Rating"]')
    review = Review(
        review_id=_id_in(r"/review/show/(\d+)", href),
        url=absolute(href),
        rating=parse_float(stars.get("aria-label")) if stars else None,
        date=parse_date(node_text(link)) if link else None,
        text=node_text(card.select_one(".ReviewText__content .Formatted")),
        has_spoilers=card.select_one(".spoiler, .spoiler__control") is not None,
        shelves=[node_text(tag) for tag in card.select(".ReviewCard__tags a") if node_text(tag)],
        reviewer=node_text(name_link) or None if name_link else None,
        reviewer_url=name_link.get("href") if name_link else None,
        reviewer_id=_id_in(r"/user/show/(\d+)", name_link.get("href") if name_link else None),
    )
    meta = card.select_one(".ReviewerProfile__meta")
    for part in meta.find_all("span", recursive=False) if meta else []:
        text = node_text(part)
        lowered = text.lower()
        if lowered == "author":
            review.reviewer_is_author = True
        elif "follower" in lowered:
            review.reviewer_followers = parse_count(text)
        elif "review" in lowered:
            review.reviewer_reviews = parse_count(text)
        elif "book" in lowered:
            review.reviewer_books = parse_count(text)
    for button in card.select('[data-testid="stats"] button'):
        text = node_text(button).lower()
        if "like" in text:
            review.likes = parse_count(text) or 0
        elif "comment" in text:
            review.comments = parse_count(text) or 0
    return review


def _apollo_state(html: str) -> dict[str, Any]:
    state = _dig(next_data(html), "props", "pageProps", "apolloState")
    return state if isinstance(state, dict) else {}


def enrich_reviews(reviews: list[Review], state: dict[str, Any]) -> None:
    """Fill review fields from the page's Apollo cache.

    A plain page load is captured before the star ratings hydrate, but the first
    reviews are in the cache with exact ratings, counts and timestamps.
    """

    def resolve(value: Any) -> dict[str, Any]:
        if isinstance(value, dict) and "__ref" in value:
            return state.get(value["__ref"]) or {}
        return value if isinstance(value, dict) else {}

    cached: dict[int, dict[str, Any]] = {}
    for key, value in state.items():
        if key.startswith("Review:") and isinstance(value, dict):
            number = _id_in(r"/review/show/(\d+)", resolve(value.get("shelving")).get("webUrl"))
            if number:
                cached[number] = value
    for review in reviews:
        entry = cached.get(review.review_id or 0)
        if not entry:
            continue
        stars = entry.get("preciseRating") or entry.get("rating")
        if review.rating is None and stars:
            review.rating = float(stars)
        review.likes = entry.get("likeCount") or review.likes
        review.comments = entry.get("commentCount") or review.comments
        review.date = review.date or ms_to_date(entry.get("createdAt"))
        review.has_spoilers = review.has_spoilers or bool(entry.get("spoilerStatus"))
        user = resolve(entry.get("creator"))
        if user.get("followersCount") is not None:
            review.reviewer_followers = user["followersCount"]
        if user.get("textReviewsCount") is not None and not review.reviewer_is_author:
            review.reviewer_reviews = user["textReviewsCount"]


def parse_review_cards(soup: BeautifulSoup | Tag, book: int | None, page: int) -> list[Review]:
    reviews = []
    for card in soup.select("article.ReviewCard"):
        review = parse_review_card(card)
        review.book_id = book
        review.page = page
        reviews.append(review)
    return reviews


def parse_reviews_page(html: str, book: int, page: int, url: str) -> ReviewPage:
    """Parse a reviews page (30 review cards) as rendered after the browser steps."""
    soup = _soup(html)
    reviews = parse_review_cards(soup, book, page)
    enrich_reviews(reviews, _apollo_state(html))
    text = " ".join(soup.get_text(" ").split())
    result = ReviewPage(book_id=book, page=page, url=url, reviews=reviews)
    result.applied_filters = [
        node_text(chip.select_one(".Button__labelItem"))
        for chip in soup.select('[data-testid="appliedFilters"] .ReviewFilters__filterButton')
        if chip.select_one(".Button__labelItem")
    ]
    displaying = _DISPLAYING.search(text)
    if displaying:
        result.first, result.last, result.total = (parse_count(g) for g in displaying.groups())
    elif soup.select_one('[data-testid="error-card"]'):
        result.total = _int_from(_NO_MATCH.pattern, text) or 0
    elif not reviews and "ReviewsList" not in html and next_data(html) is None:
        raise GoodreadsParseError(f"the reviews page came back without its reviews: {url}")
    start = result.first or (page - 1) * 30 + 1
    for index, review in enumerate(reviews):
        review.position = start + index
    if result.last is not None and result.total is not None:
        result.has_next = result.last < result.total
    else:
        result.has_next = len(reviews) >= 30
    return result


# --------------------------------------------------------------------------- #
# Book pages
# --------------------------------------------------------------------------- #


def parse_book_page(html: str, url: str) -> BookDetails:
    """Parse a book page: the Apollo cache plus the first page of review cards."""
    data = next_data(html)
    state = _dig(data, "props", "pageProps", "apolloState")
    if not isinstance(state, dict) or not state:
        raise GoodreadsParseError(f"the book page came back without its data: {url}")
    root = state.get("ROOT_QUERY") or {}

    def resolve(value: Any) -> dict[str, Any]:
        if isinstance(value, dict) and "__ref" in value:
            return state.get(value["__ref"]) or {}
        return value if isinstance(value, dict) else {}

    ref = next((v for k, v in root.items() if k.startswith("getBookByLegacyId")), None)
    book = resolve(ref)
    if not book.get("title"):
        raise GoodreadsNotFoundError(f"Goodreads has no book at {url}")

    work = resolve(book.get("work"))
    work_details = work.get("details") or {}
    stats = work.get("stats") or {}
    details = book.get("details") or {}
    edges = [
        book.get("primaryContributorEdge") or {},
        *(book.get("secondaryContributorEdges") or []),
    ]
    description_key = next(
        (k for k in ("description", 'description({"stripped":true})') if book.get(k)), None
    )
    histogram = stats.get("ratingsCountDist") or []

    def total(prefix: str) -> int | None:
        entry = next((v for k, v in work.items() if k.startswith(prefix)), None)
        return _dig(entry, "totalCount")

    signals = next((v for k, v in root.items() if k.startswith("getSocialSignals")), None) or []
    social = {s.get("name"): s.get("count") for s in signals if isinstance(s, dict)}

    number = int(book.get("legacyId") or book_id(url))
    result = BookDetails(
        book_id=number,
        title=book.get("title") or "",
        url=book.get("webUrl") or url,
        title_complete=book.get("titleComplete"),
        original_title=work_details.get("originalTitle"),
        work_id=work.get("legacyId"),
        authors=[c for c in (_contributor(e, resolve) for e in edges if e) if c],
        series=[
            SeriesRef(
                title=resolve(entry.get("series")).get("title") or "",
                position=entry.get("userPosition") or entry.get("seriesPlacement"),
                url=resolve(entry.get("series")).get("webUrl"),
            )
            for entry in book.get("bookSeries") or []
            if resolve(entry.get("series")).get("title")
        ],
        description=html_to_text(book.get(description_key)) if description_key else None,
        genres=[
            _dig(entry, "genre", "name")
            for entry in book.get("bookGenres") or []
            if _dig(entry, "genre", "name")
        ],
        average_rating=stats.get("averageRating"),
        ratings_count=stats.get("ratingsCount"),
        reviews_count=stats.get("textReviewsCount"),
        rating_histogram={str(stars): count for stars, count in enumerate(histogram[:5], start=1)},
        currently_reading=social.get("CURRENTLY_READING"),
        want_to_read=social.get("TO_READ"),
        format=details.get("format") or None,
        pages=details.get("numPages"),
        publisher=details.get("publisher") or None,
        language=_dig(details, "language", "name"),
        isbn=details.get("isbn") or None,
        isbn13=details.get("isbn13") or None,
        asin=details.get("asin") or None,
        publication_date=ms_to_date(details.get("publicationTime")),
        original_publication_date=ms_to_date(work_details.get("publicationTime")),
        awards=[
            Award(
                name=award.get("name") or "",
                category=award.get("category") or None,
                designation=(award.get("designation") or "").lower() or None,
                year=int(ms_to_date(award.get("awardedAt"))[:4])
                if ms_to_date(award.get("awardedAt"))
                else None,
                url=award.get("webUrl"),
            )
            for award in work_details.get("awardsWon") or []
            if award.get("name")
        ],
        characters=[c.get("name") for c in work_details.get("characters") or [] if c.get("name")],
        places=[p.get("name") for p in work_details.get("places") or [] if p.get("name")],
        quotes_count=total("quotes"),
        questions_count=total("questions"),
        discussions_count=total("topics"),
        review_languages={
            entry["isoLanguageCode"]: entry.get("count") or 0
            for entry in sorted(
                stats.get("textReviewsLanguageCounts") or [],
                key=lambda e: -(e.get("count") or 0),
            )
            if entry.get("isoLanguageCode")
        },
        kindle_price=_price(_dig(book, "links", "primaryAffiliateLink", "ebookPrice")),
        cover=book.get("imageUrl"),
        editions_url=_dig(work, "editions", "webUrl"),
    )
    result.reviews = parse_review_cards(_soup(html), number, 1)
    enrich_reviews(result.reviews, state)
    for index, review in enumerate(result.reviews, start=1):
        review.position = index
    return result


# --------------------------------------------------------------------------- #
# Classic HTML pages: Listopia, authors, shelves
# --------------------------------------------------------------------------- #


def _row_contributors(row: Tag) -> list[Contributor]:
    people = []
    for box in row.select(".authorName__container"):
        link = box.select_one("a.authorName")
        if not link:
            continue
        role = node_text(box.select_one(".role")).strip("() ") or "Author"
        people.append(
            Contributor(
                name=node_text(link.select_one('[itemprop="name"]') or link),
                role=role,
                author_id=_id_in(r"/author/show/(\d+)", link.get("href")),
                url=absolute(link.get("href")),
            )
        )
    return people


def parse_book_row(row: Tag, source: str) -> BookRow | None:
    """A book row of a Listopia list, an author book list or a shelf page."""
    link = row.select_one("a.bookTitle")
    if not link or not link.get("href"):
        return None
    number = _id_in(r"/book/show/(\d+)", link.get("href"))
    if number is None:
        return None
    title, series, position = split_series(node_text(link.select_one('[itemprop="name"]') or link))
    people = _row_contributors(row)
    author = next((p for p in people if p.role == "Author"), people[0] if people else None)
    text = " ".join(row.get_text(" ").split())
    image = row.select_one("img.bookCover") or row.select_one("a img")
    rank = row.select_one("td.number")
    return BookRow(
        book_id=number,
        title=title,
        url=absolute(link.get("href")).split("?")[0],
        author=author.name if author else None,
        author_id=author.author_id if author else None,
        author_url=author.url if author else None,
        contributors=people,
        series=series,
        series_position=position,
        average_rating=_avg_rating(text),
        ratings_count=_int_from(r"([\d,]+)\s+ratings?(?![a-z])", text),
        published_year=_published_year(text),
        editions_count=_int_from(r"([\d,]+)\s+editions?(?![a-z])", text),
        rank=parse_count(node_text(rank)) if rank else None,
        score=_int_from(r"score:\s*([\d,]+)", text),
        votes=_int_from(r"([\d,]+)\s+(?:people|person)\s+voted", text),
        shelved_count=_int_from(r"shelved\s+([\d,]+)\s+times?", text),
        cover=full_size(image.get("src")) if image else None,
        source=source,
    )


def _avg_rating(text: str) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s+avg rating", text) or re.search(
        r"avg rating\s+(\d+(?:\.\d+)?)", text
    )
    return float(match.group(1)) if match else None


def _published_year(text: str) -> int | None:
    match = re.search(r"published\s+(-?\d{1,4})(?!\d)", text)
    return int(match.group(1)) if match else None


def _rows(soup: BeautifulSoup | Tag, selector: str, source: str) -> list[BookRow]:
    rows = (parse_book_row(row, source) for row in soup.select(selector))
    return [row for row in rows if row is not None]


def _pagination(soup: BeautifulSoup, current: int) -> tuple[int | None, bool]:
    """(last page, has a next page) from a classic Goodreads pagination block."""
    nxt = soup.select_one("a.next_page")
    pages = [current]
    box = nxt.parent if nxt else soup.select_one(".pagination")
    for link in box.select("a") if box else []:
        label = node_text(link)
        if label.isdigit():
            pages.append(int(label))
    return max(pages), nxt is not None


_BOOK_ROW = 'tr[itemtype="http://schema.org/Book"]'


def parse_list_page(html: str, list_number: int, page: int, url: str) -> ListPage:
    """Parse one page (100 books) of a Listopia list."""
    soup = _soup(html)
    books = _rows(soup, _BOOK_ROW, f"list:{list_number}")
    title_tag = soup.find("title")
    heading = node_text(title_tag) if title_tag else ""
    if not books and "books)" not in heading:
        raise GoodreadsParseError(f"the list page came back without its books: {url}")
    result = ListPage(list_id=list_number, page=page, url=url, books=books)
    result.title = re.sub(r"\s*\([\d,]+\s+books?\)\s*$", "", heading).strip() or None
    counts = soup.find(string=re.compile(r"[\d,]+\s+voters"))
    stats_node = counts.parent if counts is not None else None
    if isinstance(stats_node, Tag):
        stats = " ".join(stats_node.get_text(" ").split())
        result.books_count = _int_from(r"([\d,]+)\s+books", stats)
        result.voters_count = _int_from(r"([\d,]+)\s+voters", stats)
        created = re.search(r"list created\s+(.+?)(?:\s+by\s|$)", stats)
        result.created = parse_date(created.group(1)) if created else None
        creator = stats_node.select_one('a[href*="/user/show/"]')
        result.created_by = node_text(creator) or None if creator else None
    result.tags = [node_text(tag) for tag in soup.select('a[href*="/list/show_tag/"]')]
    if result.books_count is None:
        result.books_count = _int_from(r"\(([\d,]+)\s+books?\)", heading)
    description = soup.select_one(".leftContainer .mediumText") or soup.select_one(".mediumText")
    if description is not None:
        for flag in description.select(".right, a.flag"):
            flag.decompose()
        result.description = node_text(description) or None
    for index, book in enumerate(books):
        if book.rank is None:
            book.rank = (page - 1) * 100 + index + 1
    result.last_page, result.has_next = _pagination(soup, page)
    return result


def _data_fields(container: Tag) -> dict[str, dict[str, Any]]:
    """The ``dataTitle`` / ``dataItem`` pairs of an author profile, in order."""
    fields: dict[str, dict[str, Any]] = {}
    current: str | None = None
    for child in container.children:
        if isinstance(child, Tag):
            classes = child.get("class") or []
            if "dataTitle" in classes:
                current = node_text(child).lower()
                fields[current] = {"text": "", "item": None}
            elif current and "dataItem" in classes:
                fields[current]["item"] = child
            elif child.name == "br" and current:
                current = None
        elif current and type(child) is NavigableString:
            fields[current]["text"] += " " + str(child)
    return fields


def parse_author_page(html: str, author_number: int, url: str) -> Author:
    """Parse an author profile page."""
    soup = _soup(html)
    name = soup.select_one("h1.authorName")
    if name is None:
        raise GoodreadsParseError(f"the author page came back without the profile: {url}")
    canonical = soup.select_one('link[rel="canonical"]')
    href = canonical.get("href") if canonical else None
    author = Author(
        author_id=author_number,
        name=node_text(name),
        url=href if href and f"/author/show/{author_number}" in href else url,
    )
    container = soup.select_one(".rightContainer") or soup
    fields = _data_fields(container)

    def item(label: str) -> Tag | None:
        return (fields.get(label) or {}).get("item")

    if "born" in fields:
        place = " ".join(fields["born"]["text"].split())
        author.birthplace = re.sub(r"^in\s+", "", place) or None
        author.born = parse_date(node_text(item("born"))) if item("born") else None
    if item("died"):
        author.died = parse_date(node_text(item("died")))
    if item("website"):
        link = item("website").select_one("a")
        author.website = (link.get("href") if link else node_text(item("website"))) or None
    if item("twitter"):
        author.twitter = node_text(item("twitter")).lstrip("@") or None
    if item("genre"):
        author.genres = [node_text(a) for a in item("genre").select("a")] or [
            g.strip() for g in node_text(item("genre")).split(",") if g.strip()
        ]
    if item("influences"):
        author.influences = [node_text(a) for a in item("influences").select("a") if node_text(a)]
    if item("member since"):
        author.member_since = parse_date(node_text(item("member since")))
    about = soup.select_one('span[id^="freeTextauthor"]') or soup.select_one(
        'span[id^="freeTextContainerauthor"]'
    )
    author.about = node_text(about) or None
    photo = soup.select_one('.leftContainer img[itemprop="image"]')
    author.image = photo.get("src") if photo else None
    aggregate = soup.select_one(".hreview-aggregate")
    if aggregate is not None:
        average = aggregate.select_one(".average")
        author.average_rating = parse_float(node_text(average)) if average else None
        ratings = aggregate.select_one('[itemprop="ratingCount"]')
        reviews = aggregate.select_one('[itemprop="reviewCount"]')
        author.ratings_count = parse_count(ratings.get("content")) if ratings else None
        author.reviews_count = parse_count(reviews.get("content")) if reviews else None
        author.works_count = _int_from(r"([\d,]+)\s+distinct works", aggregate.get_text(" "))
    author.top_books = _rows(container, _BOOK_ROW, f"author:{author_number}")
    return author


def parse_author_books_page(
    html: str, author_number: int, page: int, url: str, sort: str | None = None
) -> AuthorBooksPage:
    """Parse one page (30 books) of an author's book list."""
    soup = _soup(html)
    books = _rows(soup, _BOOK_ROW, f"author:{author_number}")
    heading = soup.select_one(".leftContainer h1") or soup.select_one("h1")
    name = re.sub(r"^Books by\s+", "", node_text(heading)) if heading else None
    if not books and not (name and heading and "Books by" in node_text(heading)):
        raise GoodreadsParseError(f"the author book list came back without its books: {url}")
    last_page, has_next = _pagination(soup, page)
    return AuthorBooksPage(
        author_id=author_number,
        page=page,
        url=url,
        author=name or None,
        sort=sort,
        books=books,
        last_page=last_page,
        has_next=has_next,
    )


def parse_shelf_page(html: str, shelf: str, url: str) -> ShelfPage:
    """Parse a shelf page: the most-shelved books for a tag."""
    soup = _soup(html)
    books = [
        row
        for row in (parse_book_row(el, f"shelf:{shelf}") for el in soup.select(".elementList"))
        if row is not None
    ]
    heading = soup.select_one(".leftContainer h1") or soup.select_one("h1")
    if not books and heading is None:
        raise GoodreadsParseError(f"the shelf page came back without its books: {url}")
    for index, book in enumerate(books, start=1):
        book.rank = index
    return ShelfPage(
        shelf=shelf, url=url, title=node_text(heading) or None if heading else None, books=books
    )


__all__ = [
    "GoodreadsError",
    "GoodreadsNotFoundError",
    "GoodreadsParseError",
    "flight_text",
    "full_size",
    "html_to_text",
    "ms_to_date",
    "next_data",
    "node_text",
    "parse_author_books_page",
    "parse_author_page",
    "parse_book_page",
    "parse_book_row",
    "parse_count",
    "parse_date",
    "parse_float",
    "parse_list_page",
    "parse_review_card",
    "parse_reviews_page",
    "parse_search_page",
    "parse_shelf_page",
    "split_series",
]
