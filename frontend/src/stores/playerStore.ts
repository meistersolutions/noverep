import { create } from 'zustand';
import { api, QueueItem, Track, UserPreferences, QueueRefreshOptions } from '@/lib/api';
import { isSameSong } from '@/lib/songMatcher';
import { recordPlayProgress, recordPlayStart } from '@/lib/playbackHistory';
import {
  setWantPlaying,
  prepareTrackTransition,
  getActiveVideoId,
  cueVideoForResume,
  loadAndPlay,
  prefetchVideo,
  pausePlayback,
  resumePlayback,
  warmUpPlayback,
} from '@/lib/youtubePlayerController';
import {
  clearCachedPreferences,
  readCachedPreferences,
  writeCachedPreferences,
} from '@/lib/preferencesCache';

const cachedPreferences = readCachedPreferences();
const hasStoredToken = !!localStorage.getItem('noverep_token');

let advancingNext = false;

function ensureSessionId(): string {
  const key = 'noverep_session';
  const existing = localStorage.getItem(key);
  if (existing && /^[0-9a-f-]{36}$/i.test(existing)) return existing;
  const id = crypto.randomUUID();
  localStorage.setItem(key, id);
  return id;
}

function queueWithoutCurrent(queue: QueueItem[], currentTrack?: QueueItem | Track | null): QueueItem[] {
  let currentIdx = queue.findIndex((q) => q.is_current);
  if (currentIdx < 0 && currentTrack) {
    if ('id' in currentTrack && currentTrack.id) {
      currentIdx = queue.findIndex((q) => q.id === currentTrack.id);
    } else {
      currentIdx = queue.findIndex((q) => q.provider_track_id === currentTrack.provider_track_id);
    }
  }
  if (currentIdx < 0) return queue;
  return queue
    .filter((_, i) => i !== currentIdx)
    .map((q, i) => ({ ...q, position: i, is_current: false }));
}

function dedupeQueue(queue: QueueItem[]): QueueItem[] {
  const seenTracks = new Set<string>();
  const seenSongs = new Set<string>();
  const kept: QueueItem[] = [];

  for (const q of queue) {
    if (seenTracks.has(q.provider_track_id)) continue;
    if (q.canonical_song_id && seenSongs.has(q.canonical_song_id)) continue;
    if (
      kept.some((existing) =>
        isSameSong(
          q.title,
          q.artist,
          q.duration_seconds,
          existing.title,
          existing.artist,
          existing.duration_seconds,
        ),
      )
    ) {
      continue;
    }
    seenTracks.add(q.provider_track_id);
    if (q.canonical_song_id) seenSongs.add(q.canonical_song_id);
    kept.push(q);
  }
  return kept;
}

function localNextInQueue(queue: QueueItem[]): QueueItem | null {
  const currentIdx = queue.findIndex((q) => q.is_current);
  if (currentIdx >= 0 && currentIdx + 1 < queue.length) {
    return queue[currentIdx + 1];
  }
  return null;
}

/** Keep queue flags in sync with what the client is actually playing. */
function alignQueueWithCurrentTrack(
  queue: QueueItem[],
  currentTrack: QueueItem | Track | null,
): QueueItem[] {
  if (!currentTrack) return queue;
  if ('id' in currentTrack && currentTrack.id) {
    return queue.map((q) => ({ ...q, is_current: q.id === currentTrack.id }));
  }
  const id = currentTrack.provider_track_id;
  return queue.map((q) => ({ ...q, is_current: q.provider_track_id === id }));
}

/** Resolve what the UI should show as now playing. Player wins when audio is active. */
function resolveCurrentTrack(
  queue: QueueItem[],
  currentTrack: QueueItem | Track | null,
  isPlaying: boolean,
): QueueItem | Track | null {
  const activeId = isPlaying ? getActiveVideoId() : null;

  if (activeId) {
    const inQueue = queue.find((q) => q.provider_track_id === activeId);
    if (inQueue) {
      return {
        ...inQueue,
        thumbnail_url: inQueue.thumbnail_url || currentTrack?.thumbnail_url || null,
      };
    }
    if (currentTrack?.provider_track_id === activeId) {
      return currentTrack;
    }
  }

  if (currentTrack) {
    const inQueue = queue.find((q) => q.provider_track_id === currentTrack.provider_track_id);
    if (inQueue) {
      return {
        ...inQueue,
        thumbnail_url: inQueue.thumbnail_url || currentTrack.thumbnail_url,
      };
    }
    if (isPlaying) {
      return currentTrack;
    }
  }

  const serverCurrent = queue.find((q) => q.is_current);
  return serverCurrent ?? currentTrack ?? queue[0] ?? null;
}

function applyQueueSnapshot(
  queue: QueueItem[],
  currentTrack: QueueItem | Track | null,
  isPlaying: boolean,
): { queue: QueueItem[]; currentTrack: QueueItem | Track | null } {
  const deduped = dedupeQueue(queue);
  const merged = resolveCurrentTrack(deduped, currentTrack, isPlaying);
  const aligned = alignQueueWithCurrentTrack(deduped, merged);
  return {
    queue: aligned,
    currentTrack: merged,
  };
}

function playQueueItemOptimistic(
  queue: QueueItem[],
  item: QueueItem,
  currentTrack: QueueItem | Track | null,
): QueueItem[] {
  const current =
    queue.find((q) => q.is_current) ??
    (currentTrack && 'id' in currentTrack && currentTrack.id
      ? queue.find((q) => q.id === currentTrack.id)
      : currentTrack
        ? queue.find((q) => q.provider_track_id === currentTrack.provider_track_id)
        : undefined);

  if (current?.id === item.id) {
    return queue.map((q, i) => ({
      ...q,
      is_current: q.id === item.id,
      position: i,
    }));
  }

  const rest = queue.filter((q) => q.id !== item.id && q.id !== current?.id);
  return [
    { ...item, is_current: true, position: 0 },
    ...rest.map((q, i) => ({ ...q, is_current: false, position: i + 1 })),
  ];
}

function applyServerQueueAfterSkip(serverQueue: QueueItem[], serverItem: QueueItem) {
  const deduped = dedupeQueue(serverQueue);
  const aligned = alignQueueWithCurrentTrack(deduped, serverItem);
  return {
    queue: aligned,
    currentTrack: serverItem,
    isPlaying: true,
    currentTime: 0,
    duration: serverItem.duration_seconds ?? 0,
  };
}

async function prefetchUpcoming(queue: QueueItem[]) {
  const next = localNextInQueue(queue);
  if (!next) return;
  prefetchVideo(next.provider_track_id);
}

function beginPlayback(item: QueueItem, volume: number) {
  void loadAndPlay(item.provider_track_id, volume * 100);
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
  queueBuilding: boolean;
  isAdmin: boolean;
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
  refreshQueueFromSearch: (query: string, options?: QueueRefreshOptions) => Promise<void>;
  refreshQueueFromPreferences: (options?: QueueRefreshOptions) => Promise<void>;
  clearActiveSearchQuery: () => Promise<void>;
  playNextInsert: (track: Track, explicit?: boolean) => Promise<void>;
  playPlaylist: (playlistId: string) => Promise<void>;
  playQueueItem: (item: QueueItem) => Promise<void>;
  refreshQueueInBackground: () => Promise<void>;
  loadPreferences: () => Promise<void>;
  bumpHistory: () => void;
  recordCurrentPlayback: (skipped?: boolean) => Promise<void>;
  syncToActiveVideo: (videoId: string) => void;
  syncFromPlayer: () => void;
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
  shuffle: cachedPreferences?.shuffle ?? false,
  autoplay: cachedPreferences?.autoplay ?? true,
  currentTime: 0,
  duration: 0,
  preferences: cachedPreferences,
  initialized: hasStoredToken && !!cachedPreferences,
  historyVersion: 0,
  queueBuilding: false,
  isAdmin: false,
  playbackMode: cachedPreferences?.playback_mode || 'discovery',
  activePlaylistId: cachedPreferences?.active_playlist_id ?? null,

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
    clearCachedPreferences();
    set({
      token: null,
      username: null,
      isGuest: false,
      initialized: false,
      preferences: null,
      currentTrack: null,
      queue: [],
      queueBuilding: false,
      isAdmin: false,
      playbackMode: 'discovery',
      activePlaylistId: null,
    });
  },

  init: async () => {
    const { token, sessionId, initialized } = get();
    if (!token) return;
    if (initialized && get().preferences) {
      void get().refreshQueueInBackground();
      return;
    }

    localStorage.setItem('noverep_session', sessionId);

    const cached = readCachedPreferences();
    if (cached) {
      set({
        preferences: cached,
        shuffle: cached.shuffle,
        autoplay: cached.autoplay,
        playbackMode: cached.playback_mode || 'discovery',
        activePlaylistId: cached.active_playlist_id,
      });
    }

    set({ initialized: true });

    warmUpPlayback();

    void api.getMe().then((me) => {
      set({ isAdmin: me.is_admin });
      localStorage.setItem('noverep_display_name', me.display_name);
    }).catch(() => {});

    void get().loadPreferences().catch(() => {});
    void get().refreshQueueInBackground();
  },

  refreshQueueInBackground: async () => {
    if (get().queueBuilding) return;
    set({ queueBuilding: true });
    try {
      const playing = get().isPlaying && get().currentTrack;
      if (get().playbackMode === 'playlist') {
        if (!playing) await get().refreshQueue();
        return;
      }

      // Fast path: show server queue immediately, then reconcile with cross-device history.
      try {
        const existing = await api.getQueue();
        if (existing?.length) {
          const snapshot = applyQueueSnapshot(existing, get().currentTrack, playing);
          set(snapshot);
          void prefetchUpcoming(snapshot.queue);
        }
      } catch {
        /* continue to reconcile */
      }

      let queue = await api.syncQueue().catch(() => null);
      if (!queue?.length) {
        queue = await api.refreshQueueFromPreferences().catch(() => null);
      }
      if (queue?.length) {
        const snapshot = applyQueueSnapshot(queue, get().currentTrack, playing);
        set(snapshot);
        void prefetchUpcoming(snapshot.queue);
      }
    } catch {
      try {
        const queue = await api.getQueue();
        if (queue?.length) {
          const snapshot = applyQueueSnapshot(queue, get().currentTrack, false);
          set(snapshot);
          void prefetchUpcoming(snapshot.queue);
        }
      } catch {
        /* best-effort */
      }
    } finally {
      set({ queueBuilding: false });
    }
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
      set(applyQueueSnapshot(queue, currentTrack, isPlaying));
      void prefetchUpcoming(get().queue);
    } catch {
      /* best-effort */
    }
  },

  refreshQueueFromSearch: async (query: string, options?) => {
    if (get().playbackMode === 'playlist') return;
    const queue = await api.refreshQueue(query, options);
    const { currentTrack, isPlaying } = get();
    set({
      ...applyQueueSnapshot(queue, currentTrack, isPlaying),
      preferences: get().preferences
        ? { ...get().preferences!, active_search_query: query.trim() }
        : get().preferences,
    });
  },

  refreshQueueFromPreferences: async (options?) => {
    if (get().playbackMode === 'playlist') return;
    const queue = await api.refreshQueueFromPreferences(options);
    const { currentTrack, isPlaying } = get();
    set({
      ...applyQueueSnapshot(queue, currentTrack, isPlaying),
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
    const audioOnly = track.content_kind === 'video';
    await api.playNextInQueue(
      track.provider,
      track.provider_track_id,
      explicit,
      audioOnly,
    );
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

  syncToActiveVideo: (videoId: string) => {
    if (!videoId) return;
    const { queue, currentTrack, isPlaying } = get();
    if (!isPlaying) return;
    if (currentTrack?.provider_track_id === videoId) return;
    const match = queue.find((q) => q.provider_track_id === videoId);
    if (match) {
      set({
        currentTrack: match,
        queue: alignQueueWithCurrentTrack(queue, match),
      });
    }
  },

  syncFromPlayer: () => {
    const videoId = getActiveVideoId();
    if (!videoId) return;
    get().syncToActiveVideo(videoId);
  },

  setPlaying: (playing) => {
    if (get().isPlaying === playing) return;
    setWantPlaying(playing);
    set({ isPlaying: playing });
    if (playing) {
      const track = get().currentTrack;
      const activeId = getActiveVideoId();
      if (track?.provider_track_id && track.provider_track_id !== activeId) {
        void loadAndPlay(track.provider_track_id, get().volume * 100);
      } else {
        resumePlayback();
      }
    } else {
      pausePlayback();
    }
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
    prepareTrackTransition();
    set({
      currentTrack: { ...track },
      isPlaying: true,
      currentTime: 0,
      duration: track.duration_seconds ?? 0,
      playbackMode: 'discovery',
      activePlaylistId: null,
    });

    void loadAndPlay(track.provider_track_id, get().volume * 100).catch(() => {
      set({ isPlaying: false });
    });

    try {
      await recordPlayStart(track, get().sessionId, explicit);
      get().bumpHistory();
    } catch {
      /* best-effort */
    }

    const audioOnly = track.content_kind === 'video';
    try {
      const item = await api.addToQueue(
        track.provider,
        track.provider_track_id,
        explicit,
        true,
        audioOnly,
      );
      const queue = await api.syncQueue();
      const playing = { ...track, ...item, thumbnail_url: item.thumbnail_url || track.thumbnail_url };
      set({
        ...applyQueueSnapshot(queue, playing, true),
        isPlaying: true,
      });
      void prefetchUpcoming(get().queue);
    } catch (err) {
      // Keep playing even if queue rejects (e.g. heard song in discover mode)
      const allowReplay = get().preferences?.repeat_disabled;
      if (!allowReplay && !explicit) throw err;
      set({ isPlaying: true, currentTrack: { ...track } });
    }
  },

  queueTrack: async (track, explicit = false) => {
    const audioOnly = track.content_kind === 'video';
    await api.addToQueue(
      track.provider,
      track.provider_track_id,
      explicit,
      false,
      audioOnly,
    );
    await get().syncQueue();
  },

  next: async (manualSkip = true) => {
    if (advancingNext) return;
    advancingNext = true;

    try {
      const { queue, volume, sessionId, currentTrack, duration } = get();

      if (manualSkip) {
        await get().recordCurrentPlayback(true);
      } else if (currentTrack) {
        void recordPlayProgress(currentTrack, sessionId, duration, duration, false).then(() =>
          get().bumpHistory(),
        );
      }

      const trimmed = queueWithoutCurrent(queue, currentTrack);
      const optimistic = localNextInQueue(queue);

      const playItem = (item: QueueItem, optimisticQueue: QueueItem[]) => {
        prepareTrackTransition();
        const updatedQueue = optimisticQueue.map((q) => ({
          ...q,
          is_current: q.id === item.id,
        }));
        set({
          currentTrack: item,
          isPlaying: true,
          currentTime: 0,
          duration: item.duration_seconds ?? 0,
          queue: updatedQueue,
        });
        void beginPlayback(item, volume);
        void recordPlayStart(item, sessionId, false).then(() => get().bumpHistory());
        void prefetchUpcoming(updatedQueue);
      };

      if (optimistic) {
        playItem(optimistic, trimmed);
        try {
          const serverItem = await api.nextTrack();
          const serverQueue = await api.getQueue();
          if (serverItem) {
            set(applyServerQueueAfterSkip(serverQueue, serverItem));
          } else {
            await get().refreshQueue();
          }
          void prefetchUpcoming(get().queue);
          void get().refreshQueueInBackground();
        } catch {
          await get().refreshQueue();
        }
        return;
      }

      const item = await api.nextTrack();
      if (!item) return;
      const serverQueue = await api.getQueue();
      prepareTrackTransition();
      set(applyServerQueueAfterSkip(serverQueue, item));
      void beginPlayback(item, volume);
      void recordPlayStart(item, sessionId, false).then(() => get().bumpHistory());
      void prefetchUpcoming(get().queue);
      void get().refreshQueueInBackground();
    } finally {
      advancingNext = false;
    }
  },

  previous: async () => {
    if (advancingNext) return;
    advancingNext = true;
    try {
      prepareTrackTransition();
      const item = await api.previousTrack();
      if (!item) return;

      const aligned = alignQueueWithCurrentTrack(get().queue, item);
      set({
        currentTrack: item,
        queue: aligned,
        isPlaying: true,
        currentTime: 0,
        duration: item.duration_seconds ?? 0,
      });

      await loadAndPlay(item.provider_track_id, get().volume * 100);

      try {
        await recordPlayStart(item, get().sessionId, get().playbackMode === 'playlist');
        get().bumpHistory();
      } catch {
        /* best-effort */
      }

      await get().refreshQueue();
    } finally {
      advancingNext = false;
    }
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

    await loadAndPlay(current.provider_track_id, get().volume * 100);

    try {
      await recordPlayStart(current, get().sessionId, true);
      get().bumpHistory();
    } catch {
      /* best-effort */
    }
  },

  playQueueItem: async (item) => {
    if (advancingNext) return;
    advancingNext = true;
    try {
      const { queue, currentTrack, volume } = get();
      const current =
        queue.find((q) => q.is_current) ??
        (currentTrack && 'id' in currentTrack && currentTrack.id
          ? queue.find((q) => q.id === currentTrack.id)
          : undefined);

      if (current && current.id !== item.id) {
        await get().recordCurrentPlayback(false);
      }

      setWantPlaying(true);
      prepareTrackTransition();
      const optimistic = playQueueItemOptimistic(queue, item, currentTrack);
      set({
        currentTrack: item,
        queue: optimistic,
        isPlaying: true,
        currentTime: 0,
        duration: item.duration_seconds ?? 0,
      });
      void beginPlayback(item, volume);

      const updated = await api.playQueueItem(item.id);
      const serverQueue = await api.getQueue();
      set({
        ...applyServerQueueAfterSkip(serverQueue, updated),
      });
      void prefetchUpcoming(get().queue);

      try {
        await recordPlayStart(updated, get().sessionId, false);
        get().bumpHistory();
      } catch {
        /* best-effort */
      }
    } finally {
      advancingNext = false;
    }
  },

  refreshQueue: async () => {
    const { currentTrack, isPlaying, volume } = get();
    const activeId = isPlaying ? getActiveVideoId() : null;
    const queue = await api.getQueue();
    const snapshot = applyQueueSnapshot(queue, currentTrack, isPlaying);

    if (activeId && snapshot.currentTrack?.provider_track_id !== activeId) {
      const fromPlayer = snapshot.queue.find((q) => q.provider_track_id === activeId);
      if (fromPlayer) {
        set({
          queue: alignQueueWithCurrentTrack(snapshot.queue, fromPlayer),
          currentTrack: fromPlayer,
        });
      } else if (currentTrack?.provider_track_id === activeId) {
        set({ queue: snapshot.queue, currentTrack });
      } else {
        set(snapshot);
      }
    } else {
      set(snapshot);
    }

    void prefetchUpcoming(get().queue);

    if (get().currentTrack && !isPlaying) {
      void cueVideoForResume(get().currentTrack!.provider_track_id, volume * 100);
    }
  },

  loadPreferences: async () => {
    const preferences = await api.getPreferences();
    writeCachedPreferences(preferences);
    set({
      preferences,
      shuffle: preferences.shuffle,
      autoplay: preferences.autoplay,
      playbackMode: preferences.playback_mode || 'discovery',
      activePlaylistId: preferences.active_playlist_id,
    });
  },
}));
