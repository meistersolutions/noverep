const API_URL = import.meta.env.VITE_API_URL || '/api/v1';

export interface Track {
  provider: string;
  provider_track_id: string;
  title: string;
  artist: string;
  album: string | null;
  duration_seconds: number | null;
  thumbnail_url: string | null;
  canonical_song_id?: string | null;
  score?: number | null;
  content_kind?: 'song' | 'video';
}

export interface QueueItem extends Track {
  id: string;
  position: number;
  is_current: boolean;
}

export interface SongDetails {
  title: string;
  artist: string;
  album: string | null;
  song_name: string | null;
  composed_by: string[];
  lyricist_by: string[];
  performed_by: string[];
  movie_name: string | null;
  release_year: number | null;
  musicbrainz_id: string | null;
  canonical_song_id: string | null;
}

export interface LyricsLine {
  time_ms: number;
  text: string;
}

export interface TrackLyrics {
  synced: boolean;
  plain: string | null;
  lines: LyricsLine[];
  instrumental: boolean;
  source: string;
}

export interface UserPreferences {
  memory_window: string;
  repeat_disabled: boolean;
  autoplay: boolean;
  shuffle: boolean;
  theme: string;
  language_preference: string | null;
  preferred_languages: string[];
  active_search_query: string | null;
  favorite_artists: string[];
  onboarding_completed: boolean;
  preferred_genres: string[];
  blocked_artists: string[];
  blocked_songs: string[];
  blocked_albums: string[];
  recommendation_weights: Record<string, number>;
  crossfade_enabled: boolean;
  gapless_enabled: boolean;
  discovery_year_from: number | null;
  discovery_year_to: number | null;
  playback_mode: 'discovery' | 'playlist';
  active_playlist_id: string | null;
}

export interface QueueRefreshOptions {
  languages?: string[];
  yearFrom?: number | null;
  yearTo?: number | null;
  includeHeard?: boolean;
}

export interface Statistics {
  songs_played: number;
  artists_explored: number;
  genres_explored: number;
  albums_explored: number;
  listening_streak_days: number;
  repeat_avoidance_count: number;
  discovery_score: number;
  most_explored_genres: { name: string; count: number }[];
  top_artists: { name: string; count: number }[];
  listening_by_hour: number[];
  listening_heatmap: Record<string, number>;
}

function getToken(): string | null {
  return localStorage.getItem('noverep_token');
}

function formatApiError(detail: unknown): string {
  if (!detail) return 'Request failed';
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item === 'string') return item;
        if (item && typeof item === 'object' && 'msg' in item) {
          const loc = 'loc' in item && Array.isArray(item.loc) ? item.loc.join('.') : '';
          return loc ? `${loc}: ${String(item.msg)}` : String(item.msg);
        }
        return JSON.stringify(item);
      })
      .join('; ');
  }
  if (typeof detail === 'object' && detail !== null && 'msg' in detail) {
    return String((detail as { msg: string }).msg);
  }
  return 'Request failed';
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  timeoutMs = 120_000,
): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  };
  if (token) headers.Authorization = `Bearer ${token}`;

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const res = await fetch(`${API_URL}${path}`, {
      ...options,
      headers,
      signal: controller.signal,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(formatApiError(err.detail) || res.statusText);
    }
    if (res.status === 204) return undefined as T;
    const text = await res.text();
    if (!text) return undefined as T;
    return JSON.parse(text) as T;
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') {
      throw new Error('Request timed out — try again');
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

export const api = {
  guestLogin: () =>
    request<{ access_token: string; username: string; is_guest: boolean }>(
      '/auth/guest',
      { method: 'POST' },
    ),
  login: (username: string, password: string) =>
    request<{ access_token: string; username: string; is_guest: boolean }>(
      '/auth/login',
      { method: 'POST', body: JSON.stringify({ username, password }) },
    ),
  register: (username: string, password: string, email?: string) =>
    request<{ access_token: string; username: string; is_guest: boolean }>(
      '/auth/register',
      { method: 'POST', body: JSON.stringify({ username, password, email }) },
    ),
  search: async (
    q: string,
    provider = 'youtube',
    includeHeard = false,
    quick = true,
    raw = true,
    anyVideo = false,
  ) => {
    const buildPath = (useQuick: boolean) => {
      const params = new URLSearchParams({
        q,
        provider,
        include_heard: String(includeHeard),
        quick: String(useQuick),
        raw: String(raw),
        any_video: String(anyVideo),
      });
      return `/search?${params}`;
    };
    try {
      return await request<{ results: Track[]; total: number }>(buildPath(quick));
    } catch (err) {
      if (quick) {
        return request<{ results: Track[]; total: number }>(buildPath(false));
      }
      throw err;
    }
  },
  getQueue: () => request<QueueItem[]>('/queue', {}, 15_000),
  getTrackDetails: (
    provider: string,
    providerTrackId: string,
    refresh = false,
    title?: string,
    artist?: string,
  ) => {
    const params = new URLSearchParams({
      provider,
      provider_track_id: providerTrackId,
      refresh: String(refresh),
    });
    if (title) params.set('title', title);
    if (artist) params.set('artist', artist);
    return request<SongDetails>(`/tracks/details?${params}`);
  },
  getTrackLyrics: (args: {
    provider: string;
    provider_track_id: string;
    title?: string;
    artist?: string;
    album?: string | null;
    duration_seconds?: number | null;
  }) => {
    const params = new URLSearchParams({
      provider: args.provider,
      provider_track_id: args.provider_track_id,
    });
    if (args.title) params.set('title', args.title);
    if (args.artist) params.set('artist', args.artist);
    if (args.album) params.set('album', args.album);
    if (args.duration_seconds != null) params.set('duration_seconds', String(args.duration_seconds));
    return request<TrackLyrics | null>(`/tracks/lyrics?${params}`);
  },
  addToQueue: (
    provider: string,
    provider_track_id: string,
    explicitly_requested = false,
    play_now = false,
    audio_only = false,
  ) =>
    request<QueueItem>('/queue', {
      method: 'POST',
      body: JSON.stringify({
        provider,
        provider_track_id,
        explicitly_requested,
        play_now,
        audio_only,
      }),
    }),
  nextTrack: (seed?: string) =>
    request<QueueItem | null>(`/queue/next${seed ? `?seed=${encodeURIComponent(seed)}` : ''}`, {
      method: 'POST',
    }),
  previousTrack: () => request<QueueItem | null>('/queue/previous', { method: 'POST' }),
  clearQueue: () => request('/queue', { method: 'DELETE' }),
  fillQueue: (minimum = 20) =>
    request<QueueItem[]>(`/queue/fill?minimum=${minimum}`, { method: 'POST' }),
  syncQueue: () =>
    request<QueueItem[]>('/queue/sync', { method: 'POST' }, 90_000),
  refreshQueue: (seed: string, options?: QueueRefreshOptions) => {
    const params = new URLSearchParams({ seed });
    if (options?.languages?.length) params.set('languages', options.languages.join(','));
    if (options?.yearFrom != null) params.set('year_from', String(options.yearFrom));
    if (options?.yearTo != null) params.set('year_to', String(options.yearTo));
    if (options?.includeHeard) params.set('include_heard', 'true');
    return request<QueueItem[]>(`/queue/refresh?${params}`, { method: 'POST' }, 90_000);
  },
  refreshQueueFromPreferences: (options?: QueueRefreshOptions) => {
    const params = new URLSearchParams({ from_preferences: 'true' });
    if (options?.languages?.length) params.set('languages', options.languages.join(','));
    if (options?.yearFrom != null) params.set('year_from', String(options.yearFrom));
    if (options?.yearTo != null) params.set('year_to', String(options.yearTo));
    if (options?.includeHeard) params.set('include_heard', 'true');
    return request<QueueItem[]>(`/queue/refresh?${params}`, { method: 'POST' }, 90_000);
  },
  clearActiveSearch: () =>
    request<UserPreferences>('/preferences', {
      method: 'PATCH',
      body: JSON.stringify({ active_search_query: null }),
    }),
  playNextInQueue: (
    provider: string,
    provider_track_id: string,
    explicitly_requested = false,
    audio_only = false,
  ) =>
    request<QueueItem>('/queue/play-next', {
      method: 'POST',
      body: JSON.stringify({
        provider,
        provider_track_id,
        explicitly_requested,
        audio_only,
      }),
    }),
  playQueueItem: (itemId: string) =>
    request<QueueItem>(`/queue/play/${itemId}`, { method: 'POST' }),
  getHistory: () =>
    request<
      {
        id: string;
        title: string;
        artist: string;
        album: string | null;
        genre: string | null;
        provider: string;
        played_at: string;
        duration_listened: number;
        completion_pct: number;
        skipped: boolean;
      }[]
    >('/history'),
  exportHistoryCsv: async () => {
    const token = getToken();
    const headers: Record<string, string> = {};
    if (token) headers.Authorization = `Bearer ${token}`;
    const res = await fetch(`${API_URL}/history/export.csv`, { headers });
    if (!res.ok) {
      const err = await res.text().catch(() => 'Failed to export history');
      throw new Error(err || 'Failed to export history');
    }
    return res.blob();
  },
  getPreferences: () => request<UserPreferences>('/preferences'),
  updatePreferences: (data: Partial<UserPreferences>) =>
    request<UserPreferences>('/preferences', {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
  getStatistics: () => request<Statistics>('/statistics'),
  getPlaylists: () =>
    request<
      {
        id: string;
        name: string;
        description: string | null;
        is_public: boolean;
        is_system: boolean;
        system_key: string | null;
      }[]
    >('/playlists'),
  createPlaylist: (name: string, description?: string) =>
    request<{ id: string; name: string; description: string | null; is_public: boolean }>(
      '/playlists',
      { method: 'POST', body: JSON.stringify({ name, description }) },
    ),
  getPlaylist: (id: string) =>
    request<{
      id: string;
      name: string;
      description: string | null;
      is_public: boolean;
      track_count: number;
      tracks: {
        id: string;
        provider: string;
        provider_track_id: string;
        title: string;
        artist: string;
        album: string | null;
        thumbnail_url: string | null;
        duration_seconds: number | null;
        position: number;
      }[];
    }>(`/playlists/${id}`),
  addToPlaylist: (
    playlistId: string,
    provider: string,
    provider_track_id: string,
    meta?: Pick<Track, 'title' | 'artist' | 'album' | 'thumbnail_url' | 'duration_seconds'>,
  ) =>
    request(`/playlists/${playlistId}/tracks`, {
      method: 'POST',
      body: JSON.stringify({
        provider,
        provider_track_id,
        title: meta?.title,
        artist: meta?.artist,
        album: meta?.album,
        thumbnail_url: meta?.thumbnail_url,
        duration_seconds: meta?.duration_seconds,
      }),
    }),
  playPlaylist: (playlistId: string) =>
    request<QueueItem[]>(`/playlists/${playlistId}/play`, { method: 'POST' }),
  getLikedStatus: (provider: string, providerTrackId: string) =>
    request<{ liked: boolean; playlist_id: string }>(
      `/playlists/liked/status?provider=${encodeURIComponent(provider)}&provider_track_id=${encodeURIComponent(providerTrackId)}`,
    ),
  likeTrack: (
    provider: string,
    providerTrackId: string,
    track?: Partial<Track>,
  ) =>
    request<{ ok: boolean; already_liked: boolean }>('/playlists/liked/tracks', {
      method: 'POST',
      body: JSON.stringify({
        provider,
        provider_track_id: providerTrackId,
        title: track?.title,
        artist: track?.artist,
        album: track?.album,
        thumbnail_url: track?.thumbnail_url,
        duration_seconds: track?.duration_seconds,
      }),
    }),
  recordPlayback: (data: Record<string, unknown>) =>
    request('/playback/event', { method: 'POST', body: JSON.stringify(data) }),
  getMe: () =>
    request<{
      id: string;
      username: string;
      display_name: string;
      email: string | null;
      is_guest: boolean;
      is_admin: boolean;
    }>('/me'),
  completeOnboarding: (data: {
    display_name: string;
    favorite_artists: string[];
    preferred_languages: string[];
  }) =>
    request('/onboarding', { method: 'POST', body: JSON.stringify(data) }),
  getHomeRecommendations: () =>
    request<{ sections: { title: string; tracks: Track[] }[] }>(
      '/recommendations/home',
      {},
      75_000,
    ),
  submitFeedback: (data: {
    feedback_type: 'bug' | 'feature';
    title: string;
    description: string;
    contact_email?: string;
  }) => request('/feedback', { method: 'POST', body: JSON.stringify(data) }),
  getMyFeedback: () =>
    request<
      {
        id: string;
        feedback_type: string;
        title: string;
        status: string;
        created_at: string;
        admin_response: string | null;
        responded_at: string | null;
      }[]
    >('/feedback/mine'),
  adminListFeedback: (params?: { status?: string; type?: string }) => {
    const q = new URLSearchParams();
    if (params?.status) q.set('status', params.status);
    if (params?.type) q.set('feedback_type', params.type);
    const qs = q.toString();
    return request<AdminFeedback[]>(`/admin/feedback${qs ? `?${qs}` : ''}`);
  },
  adminRespondFeedback: (
    feedbackId: string,
    data: { status?: string; admin_response?: string },
  ) =>
    request<AdminFeedback>(`/admin/feedback/${feedbackId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
  adminListUsers: () => request<AdminUser[]>('/admin/users'),
  adminStats: () =>
    request<{ total_users: number; guest_users: number; admin_users: number }>('/admin/stats'),
  adminUpdateUser: (userId: string, data: { is_admin?: boolean; password?: string }) =>
    request<AdminUser>(`/admin/users/${userId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
};

export interface AdminUser {
  id: string;
  username: string;
  email: string | null;
  display_name: string | null;
  is_guest: boolean;
  is_admin: boolean;
  created_at: string;
  first_used_at: string;
  last_used_at: string | null;
  songs_played_count: number;
}

export interface AdminFeedback {
  id: string;
  feedback_type: 'bug' | 'feature';
  title: string;
  description: string;
  contact_email: string | null;
  status: string;
  created_at: string;
  username: string | null;
  user_email: string | null;
  admin_response: string | null;
  responded_at: string | null;
}

export function formatAdminDateTime(iso: string | null): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleString(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  });
}

export function formatDuration(seconds: number | null): string {
  if (!seconds) return '--:--';
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toString().padStart(2, '0')}`;
}
