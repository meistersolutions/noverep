from app.application.services.song_enrichment_service import _pick_best_recording


class TestPickBestRecording:
    def test_rejects_kanne_kalaimane_for_kalaimane(self):
        candidates = [
            {
                "id": "wrong-mbid",
                "title": "Kanne Kalaimane",
                "length": 300000,
                "artist-credit": [
                    {"name": "K. J. Yesudas", "artist": {"name": "K. J. Yesudas"}},
                ],
                "releases": [
                    {
                        "title": "Moondram Pirai",
                        "release-group": {
                            "title": "Moondram Pirai",
                            "primary-type": "Soundtrack",
                        },
                    }
                ],
            },
            {
                "id": "right-mbid",
                "title": "Kalaimane",
                "length": 298000,
                "artist-credit": [
                    {"name": "Hariharan", "artist": {"name": "Hariharan"}},
                ],
                "releases": [
                    {
                        "title": "Thalam",
                        "release-group": {
                            "title": "Thalam",
                            "primary-type": "Soundtrack",
                        },
                    }
                ],
            },
        ]

        picked = _pick_best_recording(
            candidates,
            "Kalaimane",
            "Hariharan",
            298,
            "Thalam",
        )
        assert picked is not None
        assert picked["id"] == "right-mbid"

    def test_returns_none_when_only_wrong_match(self):
        candidates = [
            {
                "id": "wrong-mbid",
                "title": "Kanne Kalaimane",
                "length": 300000,
                "artist-credit": [
                    {"name": "K. J. Yesudas", "artist": {"name": "K. J. Yesudas"}},
                ],
                "releases": [
                    {
                        "title": "Moondram Pirai",
                        "release-group": {
                            "title": "Moondram Pirai",
                            "primary-type": "Soundtrack",
                        },
                    }
                ],
            },
        ]

        picked = _pick_best_recording(
            candidates,
            "Kalaimane",
            "Hariharan",
            298,
            "Thalam",
        )
        assert picked is None
