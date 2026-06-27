import { create } from 'zustand';
import { api, QueueItem, Track, UserPreferences } from '@/lib/api';
import { recordPlayProgress, recordPlayStart } from '@/lib/playbackHistory';
import { setWantPlaying } from '@/lib/youtubePlayerController';

function ensureSessionId(): string {
  const key = 'noverep_session';
  const existing = localStorage.getItem(key);
  if (existing && /^[0-9a-f-]{36}$/i.test(existing)) return existing;
  const id = crypto.randomUUID();
  localStorage.setItem(key, id);
  return id;
}

interface PlayerState {
  token: string | null;
  username: string | null;
  isGuest: boolean;
  sessionId: string;
  currentTrack: QueueItem | Track | null;
  queue: QueueItem[];
  isPlaying: boolean;
  volume: number;
  shuffle: boolean;
  autoplay: boolean;
  currentTime: number;
  duration: number;
  preferences: UserPreferences | null;
  initialized: boolean;
  historyVersion: number;
  playbackMode: 'discovery' | 'playlist';
  activePlaylistId: string | null;

  init: () => Promise<void>;
  setAuth: (token: string, username: string, isGuest: boolean) => void;
  logout: () => void;
  setPlaying: (playing: boolean) => void;
  setVolume: (v: number) => void;
  setCurrentTime: (t: number) => void;
  setDuration: (d: number) => void;
  playTrack: (track: Track, explicit?: boolean) => Promise<void>;
  queueTrack: (track: Track, explicit?: boolean) => Promise<void>;
  next: (manualSkip?: boolean) => Promise<void>;
  previous: () => Promise<void>;
  refreshQueue: () => Promise<void>;
  fillQueue: () => Promise<void>;
  syncQueue: () => Promise<void>;
  refreshQueueFromSearch: (query: string) => Promise<void>;
  refreshQueueFromPreferences: () => Promise<void>;
  clearActiveSearchQuery: () => Promise<void>;
  playNextInsert: (track: Track, explicit?: boolean) => Promise<void>;
  playPlaylist: (playlistId: string) => Promise<void>;
  playQueueItem: (item: QueueItem) => Promise<void>;
  loadPreferences: () => Promise<void>;
  bumpHistory: () => void;
  recordCurrentPlayback: (skipped?: boolean) => Promise<void>;
}

export const usePlayerStore = create<PlayerState>((set, get) => ({
  token: localStorage.getItem('noverep_token'),
  username: localStorage.getItem('noverep_username'),
  isGuest: localStorage.getItem('noverep_guest') === 'true',
  sessionId: ensureSessionId(),
  currentTrack: null,
  queue: [],
  isPlaying: false,
  volume: 0.8,
  shuffle: false,
  autoplay: true,
  currentTime: 0,
  duration: 0,
  preferences: null,
  initialized: false,
  historyVersion: 0,
  playbackMode: 'discovery',
  activePlaylistId: null,

  setAuth: (token, username, isGuest) => {
    localStorage.setItem('noverep_token', token);
    localStorage.setItem('noverep_username', username);
    localStorage.setItem('noverep_guest', String(isGuest));
    set({ token, username, isGuest });
  },

  logout: () => {
    localStorage.removeItem('noverep_token');
    localStorage.removeItem('noverep_username');
    localStorage.removeItem('noverep_guest');
    localStorage.removeItem('noverep_display_name');
    set({
      token: null,
      username: null,
      isGuest: false,
      initialized: false,
      preferences: null,
      currentTrack: null,
      queue: [],
      playbackMode: 'discovery',
      activePlaylistId: null,
    });
  },

  init: async () => {
    const { token, sessionId } = get();
    if (!token) return;

    localStorage.setItem('noverep_session', sessionId);
    await get().loadPreferences();
    if (get().playbackMode === 'playlist') {
      await get().refreshQueue();
    } else {
      await get().fillQueue();
      await get().refreshQueue();
    }
    set({ initialized: true });
  },

  bumpHistory: () => set((s) => ({ historyVersion: s.historyVersion + 1 })),

  fillQueue: async () => {
    try {
      await api.syncQueue();
    } catch {
      /* best-effort */
    }
  },

  syncQueue: async () => {
    if (get().playbackMode === 'playlist') {
      await get().refreshQueue();
      return;
    }
    try {
      const queue = await api.syncQueue();
      const { currentTrack, isPlaying } = get();
      const fromQueue = queue.find((q) => q.is_current);
      set({
        queue,
        currentTrack: isPlaying ? currentTrack ?? fromQueue ?? queue[0] : fromQueue ?? currentTrack,
      });
    } catch {
      /* best-effort */
    }
  },

  refreshQueueFromSearch: async (query: string) => {
    if (get().playbackMode === 'playlist') return;
    const queue = await api.refreshQueue(query);
    const { currentTrack, isPlaying } = get();
    const fromQueue = queue.find((q) => q.is_current);
    set({
      queue,
      currentTrack: isPlaying ? currentTrack ?? fromQueue ?? queue[0] : fromQueue ?? currentTrack,
      preferences: get().preferences
        ? { ...get().preferences!, active_search_query: query.trim() }
        : get().preferences,
    });
  },

  refreshQueueFromPreferences: async () => {
    if (get().playbackMode === 'playlist') return;
    const queue = await api.refreshQueueFromPreferences();
    const { currentTrack, isPlaying } = get();
    const fromQueue = queue.find((q) => q.is_current);
    set({
      queue,
      currentTrack: isPlaying ? currentTrack ?? fromQueue ?? queue[0] : fromQueue ?? currentTrack,
      preferences: get().preferences
        ? { ...get().preferences!, active_search_query: null }
        : get().preferences,
    });
  },

  clearActiveSearchQuery: async () => {
    const preferences = await api.clearActiveSearch();
    set({ preferences });
  },

  playNextInsert: async (track, explicit = false) => {
    await api.playNextInQueue(track.provider, track.provider_track_id, explicit);
    await get().syncQueue();
  },

  recordCurrentPlayback: async (skipped = false) => {
    const { currentTrack, sessionId, currentTime, duration } = get();
    if (!currentTrack) return;
    try {
      await recordPlayProgress(currentTrack, sessionId, currentTime, duration, skipped);
      get().bumpHistory();
    } catch {
      /* non-blocking */
    }
  },

  setPlaying: (playing) => {
    if (get().isPlaying === playing) return;
    setWantPlaying(playing);
    set({ isPlaying: playing });
    import('@/lib/youtubePlayerController').then(({ resumePlayback, pausePlayback }) => {
      if (playing) resumePlayback();
      else pausePlayback();
    });
    if (!playing) {
      const { currentTime, duration } = get();
      if (currentTime >= 30 || (duration > 0 && currentTime / duration >= 0.5)) {
        get().recordCurrentPlayback(false);
      }
    }
  },

  setVolume: (v) => set({ volume: v }),
  setCurrentTime: (t) => set({ currentTime: t }),
  setDuration: (d) => set({ duration: d }),

  playTrack: async (track, explicit = false) => {
    setWantPlaying(true);
    set({
      currentTrack: { ...track },
      isPlaying: true,
      currentTime: 0,
      duration: track.duration_seconds ?? 0,
      playbackMode: 'discovery',
      activePlaylistId: null,
    });

    const { loadAndPlay } = await import('@/lib/youtubePlayerController');
    await loadAndPlay(track.provider_track_id, get().volume * 100);

    try {
      await recordPlayStart(track, get().sessionId);
      get().bumpHistory();
    } catch {
      /* best-effort */
    }

    try {
      const item = await api.addToQueue(track.provider, track.provider_track_id, explicit, true);
      const queue = await api.syncQueue();
      const currentItem = queue.find((q) => q.is_current) ?? item;
      set({
        queue,
        currentTrack: {
          ...currentItem,
          thumbnail_url: currentItem.thumbnail_url || track.thumbnail_url,
        },
        isPlaying: true,
      });
    } catch (err) {
      // Keep playing even if queue rejects (e.g. heard song in discover mode)
      const allowReplay = get().preferences?.repeat_disabled;
      if (!allowReplay && !explicit) throw err;
      set({ isPlaying: true, currentTrack: { ...track } });
    }
  },

  queueTrack: async (track, explicit = false) => {
    await api.addToQueue(track.provider, track.provider_track_id, explicit, false);
    await get().syncQueue();
  },

  next: async (manualSkip = true) => {
    if (manualSkip) {
      await get().recordCurrentPlayback(true);
    } else {
      const { currentTrack, sessionId, duration } = get();
      if (currentTrack) {
        try {
          await recordPlayProgress(currentTrack, sessionId, duration, duration, false);
          get().bumpHistory();
        } catch {
          /* best-effort */
        }
      }
    }
    const item = await api.nextTrack();
    if (!item) return;

    setWantPlaying(true);
    set({ currentTrack: item, isPlaying: true, currentTime: 0, duration: item.duration_seconds ?? 0 });

    const { loadAndPlay, resumePlayback } = await import('@/lib/youtubePlayerController');
    await loadAndPlay(item.provider_track_id, get().volume * 100);
    if (document.hidden) {
      setTimeout(() => resumePlayback(), 300);
      setTimeout(() => resumePlayback(), 1200);
    }

    try {
      await recordPlayStart(item, get().sessionId);
      get().bumpHistory();
    } catch {
      /* best-effort */
    }

    await get().syncQueue();
  },

  previous: async () => {
    const item = await api.previousTrack();
    if (!item) return;

    set({ currentTrack: item, isPlaying: true, currentTime: 0, duration: item.duration_seconds ?? 0 });

    const { loadAndPlay } = await import('@/lib/youtubePlayerController');
    await loadAndPlay(item.provider_track_id, get().volume * 100);

    try {
      await recordPlayStart(item, get().sessionId);
      get().bumpHistory();
    } catch {
      /* best-effort */
    }

    await get().syncQueue();
  },

  playPlaylist: async (playlistId) => {
    const queue = await api.playPlaylist(playlistId);
    const current = queue.find((q) => q.is_current) ?? queue[0];
    if (!current) return;

    set({
      queue,
      currentTrack: current,
      isPlaying: true,
      currentTime: 0,
      duration: current.duration_seconds ?? 0,
      playbackMode: 'playlist',
      activePlaylistId: playlistId,
    });

    const { loadAndPlay } = await import('@/lib/youtubePlayerController');
    await loadAndPlay(current.provider_track_id, get().volume * 100);

    try {
      await recordPlayStart(current, get().sessionId);
      get().bumpHistory();
    } catch {
      /* best-effort */
    }
  },

  playQueueItem: async (item) => {
    const updated = await api.playQueueItem(item.id);
    set({
      currentTrack: updated,
      isPlaying: true,
      currentTime: 0,
      duration: updated.duration_seconds ?? 0,
    });

    const { loadAndPlay } = await import('@/lib/youtubePlayerController');
    await loadAndPlay(updated.provider_track_id, get().volume * 100);

    try {
      await recordPlayStart(updated, get().sessionId);
      get().bumpHistory();
    } catch {
      /* best-effort */
    }

    await get().refreshQueue();
  },

  refreshQueue: async () => {
    const queue = await api.getQueue();
    const { currentTrack, isPlaying } = get();
    const fromQueue = queue.find((q) => q.is_current);
    let current = currentTrack;
    if (fromQueue) {
      current = fromQueue;
    } else if (!currentTrack && queue.length > 0) {
      current = queue[0];
    }
    set({ queue, currentTrack: isPlaying ? currentTrack ?? current : current });
  },

  loadPreferences: async () => {
    const preferences = await api.getPreferences();
    set({
      preferences,
      shuffle: preferences.shuffle,
      autoplay: preferences.autoplay,
      playbackMode: preferences.playback_mode || 'discovery',
      activePlaylistId: preferences.active_playlist_id,
    });
  },
}));
