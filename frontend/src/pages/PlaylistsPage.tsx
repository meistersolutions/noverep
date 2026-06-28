import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, Play, ChevronRight, Heart } from 'lucide-react';
import { api } from '@/lib/api';
import toast from 'react-hot-toast';
import { usePlayerStore } from '@/stores/playerStore';
import { formatDuration } from '@/lib/api';

export default function PlaylistsPage() {
  const navigate = useNavigate();
  const playPlaylist = usePlayerStore((s) => s.playPlaylist);
  const [playlists, setPlaylists] = useState<
    {
      id: string;
      name: string;
      description: string | null;
      is_public: boolean;
      is_system: boolean;
      system_key: string | null;
    }[]
  >([]);
  const [name, setName] = useState('');
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<Awaited<ReturnType<typeof api.getPlaylist>> | null>(null);
  const [loadingPlay, setLoadingPlay] = useState(false);

  const load = () => api.getPlaylists().then(setPlaylists);
  useEffect(() => {
    load();
  }, []);

  const create = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    await api.createPlaylist(name);
    setName('');
    await load();
    toast.success('Playlist created');
  };

  const openPlaylist = async (id: string) => {
    if (expandedId === id) {
      setExpandedId(null);
      setDetail(null);
      return;
    }
    setExpandedId(id);
    const d = await api.getPlaylist(id);
    setDetail(d);
  };

  const handlePlay = async (playlistId: string) => {
    setLoadingPlay(true);
    try {
      await playPlaylist(playlistId);
      navigate('/now-playing');
      toast.success('Playing playlist');
    } catch {
      toast.error('Could not play playlist');
    } finally {
      setLoadingPlay(false);
    }
  };

  return (
    <div className="space-y-6 max-w-2xl pb-4">
      <h2 className="text-2xl font-bold">Playlists</h2>
      <form onSubmit={create} className="flex gap-2">
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="New playlist name"
          className="flex-1 glass px-4 py-2 focus:outline-none focus:ring-2 focus:ring-accent/50"
        />
        <button type="submit" className="btn-primary flex items-center gap-2">
          <Plus className="w-4 h-4" /> Create
        </button>
      </form>

      <div className="grid gap-3">
        {playlists.map((p) => (
          <div key={p.id} className="glass overflow-hidden">
            <div className="p-4 flex items-center gap-3">
              <button
                type="button"
                className="flex-1 text-left min-w-0"
                onClick={() => openPlaylist(p.id)}
              >
                <div className="flex items-center gap-2">
                  {p.system_key === 'liked' && <Heart className="w-4 h-4 text-accent shrink-0" />}
                  <h3 className="font-semibold truncate">{p.name}</h3>
                </div>
                {p.description && <p className="text-sm text-white/50 truncate">{p.description}</p>}
              </button>
              <button
                type="button"
                className="btn-primary flex items-center gap-1.5 text-sm py-2 px-3 shrink-0"
                onClick={() => handlePlay(p.id)}
                disabled={loadingPlay}
              >
                <Play className="w-4 h-4" />
                Play
              </button>
              <button
                type="button"
                className="btn-ghost p-2 shrink-0"
                onClick={() => openPlaylist(p.id)}
                aria-label="Expand"
              >
                <ChevronRight
                  className={`w-5 h-5 transition-transform ${expandedId === p.id ? 'rotate-90' : ''}`}
                />
              </button>
            </div>

            {expandedId === p.id && detail?.id === p.id && (
              <div className="border-t border-white/10 px-4 py-3 space-y-2">
                {detail.tracks.length === 0 ? (
                  <p className="text-sm text-white/40">No songs yet. Add from Now Playing or Queue.</p>
                ) : (
                  detail.tracks.map((t, i) => (
                    <div key={t.id} className="flex items-center gap-3 py-1.5">
                      <span className="text-white/30 text-sm w-5">{i + 1}</span>
                      {t.thumbnail_url ? (
                        <img src={t.thumbnail_url} alt="" className="w-10 h-10 rounded object-cover" />
                      ) : (
                        <div className="w-10 h-10 rounded bg-white/10" />
                      )}
                      <div className="flex-1 min-w-0">
                        <p className="text-sm truncate">{t.title}</p>
                        <p className="text-xs text-white/50 truncate">{t.artist}</p>
                      </div>
                      <span className="text-xs text-white/40">{formatDuration(t.duration_seconds)}</span>
                    </div>
                  ))
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
