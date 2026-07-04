"""Language preferences, search augmentation, and title-based filtering."""

import random
import re
from typing import NamedTuple

from app.domain.entities import ProviderTrack

SUPPORTED_LANGUAGES: dict[str, dict] = {
    "tamil": {
        "label": "Tamil",
        "search_term": "Tamil",
        "include": [r"\btamil\b", r"\btamizh\b", r"தமிழ்"],
        "exclude": [r"\btelugu\b", r"\bhindi\b", r"\bmalayalam\b", r"\bkannada\b", r"\bpunjabi\b", r"తెలుగు", r"हिंदी", r"മലയാളം"],
    },
    "english": {
        "label": "English",
        "search_term": "English",
        "include": [r"\benglish\b"],
        "exclude": [r"\btamil\b", r"\btelugu\b", r"\bhindi\b", r"\bmalayalam\b", r"\bkannada\b", r"\bpunjabi\b"],
    },
    "hindi": {
        "label": "Hindi",
        "search_term": "Hindi",
        "include": [r"\bhindi\b", r"\bbollywood\b", r"हिंदी"],
        "exclude": [r"\btamil\b", r"\btelugu\b", r"\bmalayalam\b", r"\bkannada\b", r"\bpunjabi\b", r"தமிழ்", r"తెలుగు"],
    },
    "telugu": {
        "label": "Telugu",
        "search_term": "Telugu",
        "include": [r"\btelugu\b", r"తెలుగు"],
        "exclude": [r"\btamil\b", r"\bhindi\b", r"\bmalayalam\b", r"\bkannada\b", r"\bpunjabi\b", r"தமிழ்"],
    },
    "malayalam": {
        "label": "Malayalam",
        "search_term": "Malayalam",
        "include": [r"\bmalayalam\b", r"മലയാളം"],
        "exclude": [r"\btamil\b", r"\btelugu\b", r"\bhindi\b", r"\bkannada\b", r"\bpunjabi\b"],
    },
    "kannada": {
        "label": "Kannada",
        "search_term": "Kannada",
        "include": [r"\bkannada\b", r"ಕನ್ನಡ"],
        "exclude": [r"\btamil\b", r"\btelugu\b", r"\bhindi\b", r"\bmalayalam\b", r"\bpunjabi\b"],
    },
    "punjabi": {
        "label": "Punjabi",
        "search_term": "Punjabi",
        "include": [r"\bpunjabi\b", r"ਪੰਜਾਬੀ"],
        "exclude": [r"\btamil\b", r"\btelugu\b", r"\bhindi\b", r"\bmalayalam\b", r"\bkannada\b"],
    },
}

LEGACY_LANGUAGE_MAP = {
    "ta": "tamil",
    "en": "english",
    "both": "all",
}

RANDOM_ARTISTS: dict[str, list[str]] = {
    "tamil": [
        "AR Rahman", "Anirudh", "Ilaiyaraaja", "Yuvan Shankar Raja", "Sid Sriram",
        "GV Prakash", "Hip Hop Tamizha", "Santhosh Narayanan",
    ],
    "english": [
        "Taylor Swift", "The Weeknd", "Drake", "Ed Sheeran", "Billie Eilish",
        "Coldplay", "Ariana Grande", "Post Malone",
    ],
    "hindi": [
        "Arijit Singh", "Pritam", "Vishal-Shekhar", "A.R. Rahman", "Badshah",
        "Shreya Ghoshal", "Atif Aslam",
    ],
    "telugu": [
        "Devi Sri Prasad", "Thaman S", "Anirudh", "Sid Sriram", "Mani Sharma",
        "Anup Rubens", "Mickey J Meyer",
    ],
    "malayalam": [
        "Gopi Sundar", "Shaan Rahman", "Vidyasagar", "Rahul Rajesh", "Deepak Dev",
    ],
    "kannada": [
        "Arjun Janya", "V Harikrishna", "Rakshit Shetty", "Sanjith Hegde", "Vijay Prakash",
    ],
    "punjabi": [
        "Diljit Dosanjh", "AP Dhillon", "Karan Aujla", "Shubh", "Sidhu Moose Wala",
    ],
}

RANDOM_SECTION_TITLES = [
    "Surprise Mix",
    "Fresh Picks",
    "Random Discovery",
    "Something New",
    "Unexpected Gems",
    "Wild Card",
]


class HomeQuery(NamedTuple):
    title: str
    query: str


def normalize_language_code(code: str | None) -> str:
    if not code:
        return "all"
    key = code.strip().lower()
    return LEGACY_LANGUAGE_MAP.get(key, key)


def resolve_languages(preference: str | list[str] | None) -> list[str]:
    """Active language keys for filtering. 'all' expands to every supported language."""
    if isinstance(preference, list):
        codes = [normalize_language_code(c) for c in preference]
        valid = [c for c in codes if c in SUPPORTED_LANGUAGES]
        if valid:
            return valid
        return list(SUPPORTED_LANGUAGES.keys())

    code = normalize_language_code(preference)
    if code == "all":
        return list(SUPPORTED_LANGUAGES.keys())
    if code in SUPPORTED_LANGUAGES:
        return [code]
    return list(SUPPORTED_LANGUAGES.keys())


def resolve_languages_from_prefs(pref) -> list[str]:
    """Read preferred_languages list first, then legacy language_preference string."""
    if pref is None:
        return list(SUPPORTED_LANGUAGES.keys())
    langs = getattr(pref, "preferred_languages", None) or []
    if langs:
        return resolve_languages(langs)
    return resolve_languages(getattr(pref, "language_preference", None))


def normalize_language_list(languages: list[str]) -> list[str]:
    codes = [normalize_language_code(c) for c in languages]
    valid = [c for c in codes if c in SUPPORTED_LANGUAGES]
    return valid


def augment_search_query(query: str, languages: list[str]) -> str:
    """Bias YouTube search toward the user's preferred language(s)."""
    q = query.strip()
    if not q:
        q = "official audio song"
    lower = q.lower()

    if len(languages) == 1:
        lang = languages[0]
        cfg = SUPPORTED_LANGUAGES.get(lang)
        if cfg:
            term = cfg["search_term"]
            if term.lower() not in lower:
                q = f"{q} {term}"

    for lang in languages:
        cfg = SUPPORTED_LANGUAGES.get(lang)
        if not cfg:
            continue
        term = cfg["search_term"].lower()
        if term in lower:
            break
    else:
        if "official" not in lower and "audio" not in lower and "song" not in lower:
            q = f"{q} official audio song"
        return q

    if "official" not in lower and "audio" not in lower and "song" not in lower:
        q = f"{q} official audio song"
    return q


def _title_has_pattern(title: str, patterns: list[str]) -> bool:
    for pat in patterns:
        if re.search(pat, title, re.IGNORECASE):
            return True
    return False


def detect_title_languages(title: str) -> set[str]:
    found: set[str] = set()
    for code, cfg in SUPPORTED_LANGUAGES.items():
        if _title_has_pattern(title, cfg["include"]):
            found.add(code)
    return found


def detect_artist_languages(artist: str) -> set[str]:
    if not artist:
        return set()
    lower = artist.lower()
    found: set[str] = set()
    for code, names in RANDOM_ARTISTS.items():
        for name in names:
            n = name.lower()
            if n in lower or lower in n:
                found.add(code)
                break
    return found


def track_matches_languages(track: ProviderTrack, languages: list[str]) -> bool:
    """Keep tracks aligned with preferred language; drop other-language variants."""
    if not languages or len(languages) >= len(SUPPORTED_LANGUAGES):
        return True

    title = f"{track.title} {track.artist or ''}"
    detected = detect_title_languages(title)
    allowed = set(languages)

    artist_langs = detect_artist_languages(track.artist or "")
    if artist_langs and not (artist_langs & allowed):
        return False

    if len(languages) == 1:
        only = languages[0]
        if detected:
            return only in detected
        cfg = SUPPORTED_LANGUAGES[only]
        if _title_has_pattern(title, cfg["exclude"]):
            return False
        return False

    if detected:
        return bool(detected & allowed)

    for lang in languages:
        cfg = SUPPORTED_LANGUAGES[lang]
        if _title_has_pattern(title, cfg["exclude"]):
            return False
    return True


def filter_tracks_by_language(tracks: list[ProviderTrack], languages: list[str]) -> list[ProviderTrack]:
    if not languages or len(languages) >= len(SUPPORTED_LANGUAGES):
        return tracks
    return [t for t in tracks if track_matches_languages(t, languages)]


def random_lang_discovery_query(lang: str) -> str:
    cfg = SUPPORTED_LANGUAGES.get(lang, SUPPORTED_LANGUAGES["english"])
    templates = [
        f"random {cfg['search_term']} songs official audio",
        f"underrated {cfg['search_term']} songs official audio",
        f"hidden gems {cfg['search_term']} official audio song",
        f"{cfg['search_term']} indie songs official audio",
    ]
    return random.choice(templates)


def build_random_home_queries(languages: list[str], section_count: int = 4) -> list[HomeQuery]:
    """Random home sections mixing artists across preferred languages — not user favorites."""
    pool: list[tuple[str, str]] = []
    for lang in languages:
        for artist in RANDOM_ARTISTS.get(lang, []):
            pool.append((artist, lang))
    random.shuffle(pool)

    titles = RANDOM_SECTION_TITLES.copy()
    random.shuffle(titles)

    queries: list[HomeQuery] = []
    used_artists: set[str] = set()

    for i in range(section_count):
        title = titles[i % len(titles)]
        artist_entry = None
        for artist, lang in pool:
            if artist.lower() not in used_artists:
                artist_entry = (artist, lang)
                used_artists.add(artist.lower())
                break

        if artist_entry:
            artist, lang = artist_entry
            q = augment_search_query(artist, [lang])
        else:
            lang = random.choice(languages)
            q = random_lang_discovery_query(lang)

        queries.append(HomeQuery(title=title, query=q))

    return queries
