"""Smoke tests for Wikipedia table → song extraction."""

from app.services.wikipedia import _WikiPageParser, _tables_to_works


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
