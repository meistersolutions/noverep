import { useEffect, useState } from 'react';
import { Plus, X } from 'lucide-react';
import toast from 'react-hot-toast';
import { api, Track } from '@/lib/api';

interface AddToPlaylistModalProps {
  track: Track;
  open: boolean;
  onClose: () => void;
}

export function AddToPlaylistModal({ track, open, onClose }: AddToPlaylistModalProps) {
  const [playlists, setPlaylists] = useState<
    { id: string; name: string; description: string | null }[]
  >([]);
  const [newName, setNewName] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open) return;
    api.getPlaylists().then(setPlaylists).catch(() => {});
  }, [open]);

  if (!open) return null;

  const addTo = async (playlistId: string) => {
    setLoading(true);
    try {
      await api.addToPlaylist(playlistId, track.provider, track.provider_track_id, track);
      toast.success(`Added to playlist`);
      onClose();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not add');
    } finally {
      setLoading(false);
    }
  };

  const createAndAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newName.trim()) return;
    setLoading(true);
    try {
      const created = await api.createPlaylist(newName.trim());
      await api.addToPlaylist(created.id, track.provider, track.provider_track_id, track);
      toast.success(`Created "${newName}" and added song`);
      setNewName('');
      onClose();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not create playlist');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-4 bg-black/60">
      <div className="glass w-full max-w-md rounded-2xl p-5 space-y-4 max-h-[80vh] overflow-y-auto">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h3 className="font-semibold text-lg">Add to Playlist</h3>
            <p className="text-sm text-white/50 truncate">{track.title}</p>
          </div>
          <button type="button" className="btn-ghost p-2 shrink-0" onClick={onClose} aria-label="Close">
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={createAndAdd} className="flex gap-2">
          <input
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder="New playlist name"
            className="flex-1 glass px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-accent/50"
          />
          <button type="submit" className="btn-primary px-3 py-2" disabled={loading}>
            <Plus className="w-4 h-4" />
          </button>
        </form>

        <ul className="space-y-1">
          {playlists.length === 0 && (
            <p className="text-sm text-white/40 py-2">No playlists yet — create one above.</p>
          )}
          {playlists.map((p) => (
            <li key={p.id}>
              <button
                type="button"
                className="w-full text-left px-3 py-2.5 rounded-lg hover:bg-white/10 active:bg-white/15 text-sm"
                onClick={() => addTo(p.id)}
                disabled={loading}
              >
                {p.name}
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
