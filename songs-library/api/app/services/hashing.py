import hashlib
import re
import unicodedata


def _norm(value: str | None) -> str:
    if not value:
        return ""
    text = unicodedata.normalize("NFKD", value)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.casefold().strip()
    text = re.sub(r"[^a-z0-9\s]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def content_hash(
    song_name: str,
    movie_name: str | None = None,
    composer_name: str | None = None,
    release_year: int | None = None,
) -> str:
    """Dedupe fingerprint from title + movie only.

    ``composer_name`` and ``release_year`` are accepted for call-site
    compatibility but ignored.
    """
    del composer_name, release_year
    payload = "|".join([_norm(song_name), _norm(movie_name)])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
