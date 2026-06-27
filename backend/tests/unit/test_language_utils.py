"""Unit tests for language preference utilities."""

from app.application.services.language_utils import (
    augment_search_query,
    build_random_home_queries,
    filter_tracks_by_language,
    normalize_language_code,
    resolve_languages,
    track_matches_languages,
)
from app.domain.entities import ProviderTrack


def _track(title: str, artist: str = "") -> ProviderTrack:
    return ProviderTrack(
        provider="youtube",
        provider_track_id="x",
        title=title,
        artist=artist,
        album=None,
        duration_seconds=180,
        thumbnail_url=None,
    )


def test_normalize_legacy_codes():
    assert normalize_language_code("ta") == "tamil"
    assert normalize_language_code("both") == "all"
    assert normalize_language_code("hindi") == "hindi"


def test_resolve_languages_all():
    langs = resolve_languages("all")
    assert "tamil" in langs
    assert "punjabi" in langs
    assert len(langs) == 7


def test_augment_single_language():
    q = augment_search_query("Ilaiyaraaja", ["tamil"])
    assert "tamil" in q.lower()
    assert "ilaiyaraaja" in q.lower()


def test_filter_excludes_other_language_titles():
    tracks = [
        _track("Best Telugu Songs Ilaiyaraaja"),
        _track("Ilaiyaraaja Tamil Hits"),
        _track("Enna Solla — Tamil Song"),
    ]
    filtered = filter_tracks_by_language(tracks, ["tamil"])
    titles = [t.title for t in filtered]
    assert "Best Telugu Songs Ilaiyaraaja" not in titles
    assert any("Tamil" in t or "Enna" in t for t in titles)


def test_track_matches_tamil_excludes_telugu_marker():
    assert not track_matches_languages(_track("Ilaiyaraaja Telugu Hits"), ["tamil"])
    assert track_matches_languages(_track("Ilaiyaraaja Tamil melody"), ["tamil"])


def test_resolve_languages_from_prefs_list():
    class Pref:
        preferred_languages = ["tamil", "hindi"]
        language_preference = "all"

    from app.application.services.language_utils import resolve_languages_from_prefs

    langs = resolve_languages_from_prefs(Pref())
    assert langs == ["tamil", "hindi"]


def test_resolve_languages_list_input():
    langs = resolve_languages(["tamil", "english"])
    assert langs == ["tamil", "english"]


def test_random_home_queries_no_favorite_titles():
    queries = build_random_home_queries(["tamil", "hindi"], section_count=3)
    assert len(queries) == 3
    for hq in queries:
        assert "Because you like" not in hq.title
        assert hq.title in (
            "Surprise Mix",
            "Fresh Picks",
            "Random Discovery",
            "Something New",
            "Unexpected Gems",
            "Wild Card",
        )
