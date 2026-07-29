from app.schemas import PlaylistExportRequest
from app.services.hashing import content_hash
from app.services.playlist_export import export_playlist


class _FakeQuery:
    def __init__(self, songs):
        self._songs = songs

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args):
        return self

    def limit(self, n):
        self._songs = self._songs[:n]
        return self

    def all(self):
        return self._songs


class _FakeDb:
    def __init__(self, songs):
        self._songs = songs

    def query(self, model):
        return _FakeQuery(self._songs)


class _Song:
    def __init__(self, **kwargs):
        self.id = kwargs["id"]
        self.song_name = kwargs["song_name"]
        self.movie_name = kwargs.get("movie_name")
        self.composer_name = kwargs.get("composer_name")
        self.youtube_video_id = kwargs.get("youtube_video_id")
        self.popularity = kwargs.get("popularity", 50)
        self.release_year = kwargs.get("release_year")


def test_export_playlist_mapped_only():
    songs = [
        _Song(
            id="1",
            song_name="Song A",
            movie_name="Film",
            composer_name="Composer",
            youtube_video_id="abc12345678",
        ),
        _Song(id="2", song_name="Song B", youtube_video_id=None),
    ]
    result = export_playlist(
        _FakeDb(songs),
        PlaylistExportRequest(composer="Composer", only_mapped=True, limit=10),
    )
    assert result.item_count == 1
    assert result.items[0].youtube_video_id == "abc12345678"
    assert "abc12345678" in (result.youtube_watch_url or "")


def test_content_hash_matches_library():
    assert content_hash("Test", "Movie", "Composer", 2000) == content_hash(
        "test", "movie", "composer", 2000
    )
