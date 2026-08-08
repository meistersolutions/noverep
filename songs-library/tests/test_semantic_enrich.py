"""Unit tests for semantic tags, embed text, and cosine search."""

from __future__ import annotations

from types import SimpleNamespace

from app.services.tags import (
    filter_allowed_tags,
    moods_from_tags,
    normalize_energy,
    normalize_vocal,
)
from app.services.vector_search import build_embed_text, cosine_similarity, search_songs


def test_filter_allowed_tags_drops_unknown():
    assert filter_allowed_tags(["sad", "UNKNOWN", "Duet", "rain", "bogus"]) == [
        "sad",
        "duet",
        "rain",
    ]


def test_moods_from_tags_subset():
    assert moods_from_tags(["sad", "duet", "romantic", "party"]) == ["sad", "romantic"]


def test_normalize_vocal_energy():
    assert normalize_vocal("DUET") == "duet"
    assert normalize_vocal("choir") == "unknown"
    assert normalize_energy("HIGH") == "high"
    assert normalize_energy("loud") == "medium"


def test_build_embed_text_includes_core_fields():
    song = SimpleNamespace(
        song_name="Enna Solla",
        movie_name="Thangamagan",
        release_year=2015,
        language="Tamil",
        composer_name="Anirudh",
        singers=["Anirudh", "Shashaa"],
        lyricists=["Vignesh"],
    )
    text = build_embed_text(
        song,
        summary="A playful romantic duet.",
        tags=["romantic", "playful", "duet"],
        vocal="duet",
        energy="high",
        lyrics="enna solla pogirai " * 20,
    )
    assert "title: Enna Solla" in text
    assert "Thangamagan" in text
    assert "vocal: duet" in text
    assert "romantic" in text
    assert "summary: A playful romantic duet." in text
    assert "lyrics:" in text


def test_cosine_similarity_identical_and_orthogonal():
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert abs(cosine_similarity([1.0, 0.0], [0.0, 1.0])) < 1e-9
    assert cosine_similarity([], [1.0]) == 0.0


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def join(self, *args, **kwargs):
        return self

    def outerjoin(self, *args, **kwargs):
        return self

    def all(self):
        return self._rows


class _FakeDb:
    def __init__(self, rows):
        self._rows = rows

    def query(self, *args):
        return _FakeQuery(self._rows)


def test_search_songs_ranks_by_cosine():
    song_a = SimpleNamespace(
        id="a",
        language="Tamil",
        release_year=1995,
        moods=["sad"],
        song_name="A",
    )
    song_b = SimpleNamespace(
        id="b",
        language="Tamil",
        release_year=1995,
        moods=["happy"],
        song_name="B",
    )
    emb_a = SimpleNamespace(embedding=[1.0, 0.0])
    emb_b = SimpleNamespace(embedding=[0.0, 1.0])
    enr_a = SimpleNamespace(tags=["sad"], summary="tearjerker", vocal="solo", energy="low", status="ready")
    enr_b = SimpleNamespace(tags=["happy"], summary="party", vocal="group", energy="high", status="ready")
    db = _FakeDb([(song_a, emb_a, enr_a), (song_b, emb_b, enr_b)])
    hits = search_songs(db, query_embedding=[1.0, 0.0], limit=5)
    assert len(hits) == 2
    assert hits[0][0].id == "a"
    assert hits[0][2] > hits[1][2]

    tagged = search_songs(db, query_embedding=[1.0, 0.0], limit=5, tags=["happy"])
    assert len(tagged) == 1
    assert tagged[0][0].id == "b"
