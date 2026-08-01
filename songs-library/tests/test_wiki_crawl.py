"""Unit tests for classified Wikipedia BFS helpers."""

from app.services.wiki_crawl import (
    classify_page,
    extract_infobox_credits,
    film_page_candidates,
    is_enqueue_worthy,
    is_skippable_title,
)
from app.services.wikipedia import _WikiPageParser, _tables_to_films, _tables_to_works


INFOBOX = """
<table class="infobox vevent">
<tr><th>Directed by</th><td>Mani Ratnam</td></tr>
<tr><th>Music by</th><td>Ilaiyaraaja</td></tr>
<tr><th>Starring</th><td>Akkineni Nagarjuna, Girija</td></tr>
<tr><th>Release date</th><td>10 May 1989</td></tr>
</table>
<p>Some body text</p>
"""


def test_classify_film_by_title():
    assert classify_page("Geethanjali (1989 film)") == "film"
    assert classify_page("Geethanjali (soundtrack)") == "soundtrack"
    assert classify_page("Ilaiyaraaja discography") == "hub"
    assert classify_page("Mani Ratnam filmography") == "hub"
    assert classify_page("Geetanjali (disambiguation)") == "other"


def test_classify_film_by_infobox():
    assert classify_page("Geethanjali", INFOBOX) == "film"


def test_extract_infobox_credits():
    credits = extract_infobox_credits(INFOBOX)
    assert credits["directors"] == ["Mani Ratnam"]
    assert credits["composer_name"] == "Ilaiyaraaja"
    assert "Akkineni Nagarjuna" in credits["actors"]
    assert credits["release_year"] == 1989


def test_enqueue_filters():
    assert is_enqueue_worthy("Geethanjali (1989 film)")
    assert is_enqueue_worthy("Roja (soundtrack)")
    assert is_enqueue_worthy("Ilaiyaraaja discography")
    assert not is_enqueue_worthy("Category:Tamil films")
    assert not is_enqueue_worthy("File:Poster.jpg")
    assert is_skippable_title("Template:Infobox")


def test_film_page_candidates_prefer_year():
    assert film_page_candidates("Geethanjali", 1989)[0] == "Geethanjali (1989 film)"


def test_tables_to_works_reads_composer_column():
    html = """
    <table class="wikitable">
    <tr><th>Film</th><th>Song</th><th>Composer</th><th>Singer(s)</th></tr>
    <tr><td>Geethanjali</td><td>O Priya Priya</td><td>Ilaiyaraaja</td><td>S. P. Balasubrahmanyam</td></tr>
    </table>
    """
    parser = _WikiPageParser()
    parser.feed(html)
    works = _tables_to_works(parser.tables, page_title="Test")
    assert len(works) == 1
    assert works[0]["composer_name"] == "Ilaiyaraaja"
    assert works[0]["singers"] == ["S. P. Balasubrahmanyam"]


def test_film_dedupe_keeps_same_title_different_years():
    html = """
    <table class="wikitable">
    <tr><th>Year</th><th>Film</th><th>Language</th></tr>
    <tr><td>1981</td><td>Geethanjali</td><td>Tamil</td></tr>
    <tr><td>1989</td><td>Geethanjali</td><td>Telugu</td></tr>
    </table>
    """
    parser = _WikiPageParser()
    parser.feed(html)
    films = _tables_to_films(parser.tables)
    assert films == [
        {"film": "Geethanjali", "year": 1981, "language": "Tamil"},
        {"film": "Geethanjali", "year": 1989, "language": "Telugu"},
    ]


def test_film_dedupe_keeps_same_title_year_different_language():
    html = """
    <table class="wikitable">
    <tr><th>Year</th><th>Film</th><th>Language</th></tr>
    <tr><td>1989</td><td>Geethanjali</td><td>Tamil</td></tr>
    <tr><td>1989</td><td>Geethanjali</td><td>Telugu</td></tr>
    </table>
    """
    parser = _WikiPageParser()
    parser.feed(html)
    films = _tables_to_films(parser.tables)
    assert len(films) == 2
    assert films[0]["language"] == "Tamil"
    assert films[1]["language"] == "Telugu"
