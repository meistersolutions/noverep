"""Smoke tests for Wikipedia table → song extraction."""

from app.services.wikipedia import _WikiPageParser, _tables_to_films, _tables_to_works


SAMPLE = """
<h3>1977</h3>
<table class="wikitable sortable">
<tr><th>Film</th><th>Song</th><th>Language</th><th>Composer</th></tr>
<tr>
  <td rowspan="2"><i>16 Vayadhinile</i></td>
  <td>"Solam Vidhaikkaiyile"</td>
  <td rowspan="2">Tamil</td>
  <td rowspan="2">Ilaiyaraaja</td>
</tr>
<tr>
  <td>"Chinnakiliye"</td>
</tr>
</table>
"""

TRACKLIST = """
<table class="tracklist">
<caption><i>Dragon</i> (Tamil)</caption>
<tbody>
<tr>
  <th scope="col">No.</th>
  <th scope="col">Title</th>
  <th scope="col">Lyrics</th>
  <th scope="col">Singer(s)</th>
  <th scope="col">Length</th>
</tr>
<tr>
  <th scope="row">1.</th>
  <td>"Yendi Vittu Pona"</td>
  <td>Ko Sesha</td>
  <td>Silambarasan</td>
  <td>04:18</td>
</tr>
<tr>
  <th scope="row">2.</th>
  <td>"Rise of Dragon"</td>
  <td>Vignesh Shivan</td>
  <td>Anirudh Ravichander</td>
  <td>03:32</td>
</tr>
<tr>
  <th scope="row">3.</th>
  <td>"Iraivaa"</td>
  <td>Ko Sesha</td>
  <td>Yuvan Shankar Raja</td>
  <td>03:20</td>
</tr>
<tr class="tracklist-total-length">
  <th colspan="4" scope="row"><span>Total length:</span></th>
  <td>22:24</td>
</tr>
</tbody>
</table>
"""

FILM_NAME_DISCOGRAPHY = """
<table class="wikitable sortable">
<tr><th>Year</th><th>Film name</th><th>Notes</th></tr>
<tr><td>1952</td><td><i>Panam</i></td><td>Composed along with T. K. Ramamoorthy</td></tr>
<tr><td>1960</td><td><i>Rathinapuri Ilavarasi</i></td><td></td></tr>
<tr><td>1970</td><td>Ethirkalam</td><td></td></tr>
</table>
"""


def test_rowspan_film_applies_to_second_song():
    parser = _WikiPageParser()
    parser.feed(SAMPLE)
    works = _tables_to_works(parser.tables, page_title="Test")
    assert len(works) == 2
    assert works[0]["song_name"] == "Solam Vidhaikkaiyile"
    assert works[0]["movie_name"] == "16 Vayadhinile"
    assert works[0]["release_year"] == 1977
    assert works[1]["song_name"] == "Chinnakiliye"
    assert works[1]["movie_name"] == "16 Vayadhinile"
    assert works[1]["release_year"] == 1977


def test_tracklist_table_parses_all_titles():
    parser = _WikiPageParser()
    parser.feed(TRACKLIST)
    works = _tables_to_works(parser.tables, page_title="Dragon (soundtrack)")
    names = [w["song_name"] for w in works]
    assert names == ["Yendi Vittu Pona", "Rise of Dragon", "Iraivaa"]


def test_film_name_column_extracts_filmography_rows():
    """M. S. Viswanathan discography uses 'Film name', not 'Film'."""
    parser = _WikiPageParser()
    parser.feed(FILM_NAME_DISCOGRAPHY)
    films = _tables_to_films(parser.tables)
    assert len(films) == 3
    assert films[0] == {"film": "Panam", "year": 1952}
    assert films[1]["film"] == "Rathinapuri Ilavarasi"
    assert films[2]["year"] == 1970
