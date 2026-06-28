from enum import Enum


class ProviderType(str, Enum):
    YOUTUBE = "youtube"
    SPOTIFY = "spotify"
    APPLE_MUSIC = "apple_music"
    LOCAL = "local"


class MemoryWindow(str, Enum):
    ONE_DAY = "1d"
    SEVEN_DAYS = "7d"
    FIFTEEN_DAYS = "15d"
    THIRTY_DAYS = "30d"
    SIXTY_DAYS = "60d"
    NINETY_DAYS = "90d"
    ONE_YEAR = "365d"
    FOREVER = "forever"


MEMORY_WINDOW_DAYS: dict[MemoryWindow, int | None] = {
    MemoryWindow.ONE_DAY: 1,
    MemoryWindow.SEVEN_DAYS: 7,
    MemoryWindow.FIFTEEN_DAYS: 15,
    MemoryWindow.THIRTY_DAYS: 30,
    MemoryWindow.SIXTY_DAYS: 60,
    MemoryWindow.NINETY_DAYS: 90,
    MemoryWindow.ONE_YEAR: 365,
    MemoryWindow.FOREVER: None,
}


class PlaybackState(str, Enum):
    PLAYING = "playing"
    PAUSED = "paused"
    STOPPED = "stopped"
    BUFFERING = "buffering"
