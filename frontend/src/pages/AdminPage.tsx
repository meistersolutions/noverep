import { useEffect, useState } from 'react';
import { Shield } from 'lucide-react';
import toast from 'react-hot-toast';
import { Navigate } from 'react-router-dom';
import { api, AdminUser } from '@/lib/api';
import { usePlayerStore } from '@/stores/playerStore';

export default function AdminPage() {
  const isAdmin = usePlayerStore((s) => s.isAdmin);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [stats, setStats] = useState<{ total_users: number; guest_users: number; admin_users: number } | null>(
    null,
  );
  const [loading, setLoading] = useState(true);
  const [passwords, setPasswords] = useState<Record<string, string>>({});

  const load = async () => {
    setLoading(true);
    try {
      const [userList, adminStats] = await Promise.all([api.adminListUsers(), api.adminStats()]);
      setUsers(userList);
      setStats(adminStats);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Admin access denied');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isAdmin) load();
  }, [isAdmin]);

  if (!isAdmin) {
    return <Navigate to="/" replace />;
  }

  const saveUser = async (userId: string, updates: { is_admin?: boolean; password?: string }) => {
    try {
      const updated = await api.adminUpdateUser(userId, updates);
      setUsers((prev) => prev.map((u) => (u.id === userId ? updated : u)));
      setPasswords((prev) => ({ ...prev, [userId]: '' }));
      toast.success('User updated');
      void load();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Update failed');
    }
  };

  if (loading) {
    return <div className="glass h-64 animate-pulse max-w-3xl" />;
  }

  return (
    <div className="space-y-6 max-w-3xl">
      <div className="flex items-center gap-3">
        <Shield className="w-8 h-8 text-accent" />
        <div>
          <h2 className="text-2xl font-bold">Admin</h2>
          <p className="text-sm text-white/50">Manage users and roles</p>
        </div>
      </div>

      {stats && (
        <div className="grid grid-cols-3 gap-3">
          <div className="glass p-4 text-center">
            <p className="text-2xl font-bold">{stats.total_users}</p>
            <p className="text-xs text-white/50">Total users</p>
          </div>
          <div className="glass p-4 text-center">
            <p className="text-2xl font-bold">{stats.guest_users}</p>
            <p className="text-xs text-white/50">Guests</p>
          </div>
          <div className="glass p-4 text-center">
            <p className="text-2xl font-bold">{stats.admin_users}</p>
            <p className="text-xs text-white/50">Admins</p>
          </div>
        </div>
      )}

      <p className="text-xs text-white/40">
        Default admin username is <span className="text-white/60">admin</span>. Set{' '}
        <code className="text-accent/80">ADMIN_PASSWORD</code> in your API environment to enable login.
      </p>

      <div className="glass overflow-hidden">
        <table className="w-full text-sm">
          <thead className="border-b border-white/10 text-white/50">
            <tr>
              <th className="text-left p-3">User</th>
              <th className="text-left p-3 hidden sm:table-cell">Type</th>
              <th className="text-left p-3">Admin</th>
              <th className="text-left p-3">Password</th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id} className="border-b border-white/5">
                <td className="p-3">
                  <p className="font-medium">{u.username}</p>
                  <p className="text-xs text-white/40">{u.email || '—'}</p>
                </td>
                <td className="p-3 hidden sm:table-cell text-white/60">
                  {u.is_guest ? 'Guest' : 'Registered'}
                </td>
                <td className="p-3">
                  <input
                    type="checkbox"
                    checked={u.is_admin}
                    onChange={(e) => saveUser(u.id, { is_admin: e.target.checked })}
                    className="accent-accent"
                  />
                </td>
                <td className="p-3">
                  <div className="flex gap-2">
                    <input
                      type="password"
                      placeholder="New password"
                      value={passwords[u.id] || ''}
                      onChange={(e) =>
                        setPasswords((prev) => ({ ...prev, [u.id]: e.target.value }))
                      }
                      className="flex-1 min-w-0 bg-surface-raised border border-white/10 rounded px-2 py-1 text-xs"
                    />
                    <button
                      type="button"
                      className="btn-primary text-xs px-2 py-1 shrink-0"
                      disabled={!(passwords[u.id]?.length >= 6)}
                      onClick={() => saveUser(u.id, { password: passwords[u.id] })}
                    >
                      Set
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
