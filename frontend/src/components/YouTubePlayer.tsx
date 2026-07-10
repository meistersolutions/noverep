import { useEffect, useRef } from 'react';
import { usePlayerStore } from '@/stores/playerStore';
import {
  getPlayer,
  handlePlayerStateChange,
  setOnNaturalEnd,
  setOnPlayingChange,
  setOnActiveVideoId,
  setPlayerInstance,
  setVolumeLevel,
  setWantPlaying,
  warmUpPlayback,
  waitForYouTubeApi,
  syncNativePlaybackClock,
  isUsingNativePlayer,
} from '@/lib/youtubePlayerController';
import { updateMediaSession, setupMediaSessionHandlers } from '@/lib/mediaSession';
import { initBackgroundPlayback, onPlaybackStateChange } from '@/lib/backgroundPlayback';
import { isAndroidNative } from '@/lib/nativePlatform';

const CONTAINER_ID = 'noverep-yt-player';

/** Real iframe dimensions off-screen — required for reliable playback on mobile and desktop Chrome. */
const PLAYER_CONTAINER_STYLE: React.CSSProperties = {
  width: 320,
  height: 180,
  opacity: 0.01,
  left: -9999,
  top: 0,
  zIndex: 0,
};

export function YouTubePlayer() {
  const {
    currentTrack,
    isPlaying,
    volume,
    autoplay,
    setPlaying,
    setCurrentTime,
    setDuration,
    next,
    previous,
    syncFromPlayer,
  } = usePlayerStore();

  const currentTrackRef = useRef(currentTrack);
  const autoplayRef = useRef(autoplay);

  currentTrackRef.current = currentTrack;
  autoplayRef.current = autoplay;

  useEffect(() => {
    warmUpPlayback();
  }, []);

  useEffect(() => {
    let cancelled = false;

    const init = async () => {
      await waitForYouTubeApi();
      if (cancelled || !window.YT?.Player || getPlayer()) return;

      const instance = new window.YT.Player(CONTAINER_ID, {
        height: '180',
        width: '320',
        playerVars: {
          autoplay: 0,
          controls: 0,
          playsinline: 1,
          rel: 0,
          modestbranding: 1,
          enablejsapi: 1,
          fs: 0,
          origin: window.location.origin,
        },
        events: {
          onReady: () => {
            if (!cancelled) setPlayerInstance(instance as never);
          },
          onStateChange: (e: { data: number; target: YTPlayerInstance }) => {
            handlePlayerStateChange(e.data, e.target as never);
          },
        },
      });
    };

    void init();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    setupMediaSessionHandlers({
      play: () => {
        const { currentTrack, setPlaying } = usePlayerStore.getState();
        if (currentTrack) setPlaying(true);
      },
      pause: () => usePlayerStore.getState().setPlaying(false),
      next: () => void usePlayerStore.getState().next(),
      previous: () => void usePlayerStore.getState().previous(),
    });

    return initBackgroundPlayback(() => usePlayerStore.getState().isPlaying);
  }, []);

  useEffect(() => {
    updateMediaSession(currentTrack, isPlaying);
    onPlaybackStateChange(isPlaying, () => usePlayerStore.getState().isPlaying);
  }, [currentTrack, isPlaying]);

  useEffect(() => {
    setOnPlayingChange((playing) => setPlaying(playing));

    setOnActiveVideoId((videoId) => {
      usePlayerStore.getState().syncToActiveVideo(videoId);
    });

    setOnNaturalEnd(() => {
      const track = currentTrackRef.current;
      if (!track || !autoplayRef.current) return;

      setWantPlaying(true);
      next(false);
    });

    return () => {
      setOnNaturalEnd(null);
      setOnPlayingChange(null);
      setOnActiveVideoId(null);
    };
  }, [setPlaying, next]);

  useEffect(() => {
    const p = getPlayer();
    if (!p || !currentTrack) return;
    if (!isPlaying && p.getPlayerState?.() === 1) p.pauseVideo();
  }, [isPlaying, currentTrack?.provider_track_id]);

  useEffect(() => {
    setVolumeLevel(volume * 100);
  }, [volume]);

  useEffect(() => {
    const id = window.setInterval(() => {
      // Native ExoPlayer clock
      if (isAndroidNative() && isUsingNativePlayer()) {
        void syncNativePlaybackClock(setCurrentTime, setDuration);
        return;
      }
      // YouTube iframe clock (web + Android fallback)
      const p = getPlayer();
      if (!p?.getCurrentTime) return;
      const t = p.getCurrentTime();
      if (Number.isFinite(t)) setCurrentTime(t);
      const d = p.getDuration();
      if (d && Number.isFinite(d) && d > 0) setDuration(d);
      syncFromPlayer();
    }, 250);
    return () => clearInterval(id);
  }, [setCurrentTime, setDuration, syncFromPlayer]);

  return (
    <div
      aria-hidden
      className="pointer-events-none fixed overflow-hidden"
      style={PLAYER_CONTAINER_STYLE}
    >
      <div id={CONTAINER_ID} />
    </div>
  );
}

interface YTPlayerInstance {
  getPlayerState: () => number;
  getCurrentTime: () => number;
  getDuration: () => number;
  playVideo: () => void;
  pauseVideo: () => void;
}
