import { useEffect, useRef } from 'react';
import { Capacitor } from '@capacitor/core';
import { usePlayerStore } from '@/stores/playerStore';
import {
  getPlayer,
  handlePlayerStateChange,
  setOnNaturalEnd,
  setOnPlayingChange,
  setOnActiveVideoId,
  setPlayerInstance,
  setWantPlaying,
  waitForYouTubeApi,
} from '@/lib/youtubePlayerController';
import { updateMediaSession, setupMediaSessionHandlers } from '@/lib/mediaSession';
import { initBackgroundPlayback, onPlaybackStateChange } from '@/lib/backgroundPlayback';

const CONTAINER_ID = 'noverep-yt-player';

let globalPlayerCreated = false;

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
    if (globalPlayerCreated) return;
    globalPlayerCreated = true;

    const init = async () => {
      await waitForYouTubeApi();
      if (!window.YT?.Player || getPlayer()) return;

      const instance = new window.YT.Player(CONTAINER_ID, {
        height: '200',
        width: '200',
        playerVars: {
          autoplay: 0,
          controls: 0,
          playsinline: 1,
          rel: 0,
          modestbranding: 1,
          enablejsapi: 1,
          origin: window.location.origin,
        },
        events: {
          onReady: () => setPlayerInstance(instance as never),
          onStateChange: (e: { data: number; target: YTPlayerInstance }) => {
            handlePlayerStateChange(e.data, e.target as never);
          },
        },
      });
    };

    init();
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
    import('@/lib/youtubePlayerController').then(({ setVolumeLevel }) => {
      setVolumeLevel(volume * 100);
    });
  }, [volume]);

  useEffect(() => {
    const id = window.setInterval(() => {
      const p = getPlayer();
      if (!p?.getCurrentTime) return;
      const t = p.getCurrentTime();
      if (Number.isFinite(t)) setCurrentTime(t);
      const d = p.getDuration();
      if (d && Number.isFinite(d) && d > 0) setDuration(d);
      syncFromPlayer();
    }, 500);
    return () => clearInterval(id);
  }, [setCurrentTime, setDuration, syncFromPlayer]);

  const isNative = Capacitor.isNativePlatform();

  return (
    <div
      aria-hidden
      className="pointer-events-none fixed overflow-hidden"
      style={
        isNative
          ? {
              // iOS/Android WebViews may pause zero-size iframes; keep a real player off-screen.
              width: 320,
              height: 180,
              opacity: 0.01,
              left: -9999,
              top: 0,
              zIndex: 0,
            }
          : {
              width: 1,
              height: 1,
              opacity: 0.01,
              left: 0,
              bottom: 0,
              zIndex: 0,
            }
      }
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
