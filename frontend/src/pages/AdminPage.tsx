import { useEffect, useState } from 'react';
import { Bug, Lightbulb, MessageSquare, Shield, Users } from 'lucide-react';
import toast from 'react-hot-toast';
import { Navigate } from 'react-router-dom';
import { api, AdminFeedback, AdminUser, formatAdminDateTime } from '@/lib/api';
import { usePlayerStore } from '@/stores/playerStore';

type AdminTab = 'users' | 'feedback';

const FEEDBACK_STATUSES = ['open', 'in_progress', 'resolved', 'closed'] as const;

export default function AdminPage() {
  const isAdmin = usePlayerStore((s) => s.isAdmin);
  const [tab, setTab] = useState<AdminTab>('users');
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [feedback, setFeedback] = useState<AdminFeedback[]>([]);
  const [stats, setStats] = useState<{ total_users: number; guest_users: number; admin_users: number } | null>(
    null,
  );
  const [loading, setLoading] = useState(true);
  const [passwords, setPasswords] = useState<Record<string, string>>({});
  const [feedbackFilter, setFeedbackFilter] = useState<{ status: string; type: string }>({
    status: '',
    type: '',
  });
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [responseDraft, setResponseDraft] = useState('');
  const [statusDraft, setStatusDraft] = useState('open');
  const [savingResponse, setSavingResponse] = useState(false);

  const loadUsers = async () => {
    const [userList, adminStats] = await Promise.all([api.adminListUsers(), api.adminStats()]);
    setUsers(userList);
    setStats(adminStats);
  };

  const loadFeedback = async () => {
    const list = await api.adminListFeedback({
      status: feedbackFilter.status || undefined,
      type: feedbackFilter.type || undefined,
    });
    setFeedback(list);
    if (selectedId && !list.some((f) => f.id === selectedId)) {
      setSelectedId(null);
    }
  };

  const load = async () => {
    setLoading(true);
    try {
      await Promise.all([loadUsers(), loadFeedback()]);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Admin access denied');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isAdmin) load();
  }, [isAdmin]);

  useEffect(() => {
    if (!isAdmin) return;
    void loadFeedback().catch(() => {});
  }, [feedbackFilter.status, feedbackFilter.type, isAdmin]);

  const selected = feedback.find((f) => f.id === selectedId) ?? null;

  useEffect(() => {
    if (selected) {
      setResponseDraft(selected.admin_response ?? '');
      setStatusDraft(selected.status);
    }
  }, [selected?.id, selected?.admin_response, selected?.status]);

  if (!isAdmin) {
    return <Navigate to="/" replace />;
  }

  const saveUser = async (userId: string, updates: { is_admin?: boolean; password?: string }) => {
    try {
      const updated = await api.adminUpdateUser(userId, updates);
      setUsers((prev) => prev.map((u) => (u.id === userId ? updated : u)));
      setPasswords((prev) => ({ ...prev, [userId]: '' }));
      toast.success('User updated');
      void loadUsers();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Update failed');
    }
  };

  const saveFeedbackResponse = async () => {
    if (!selected) return;
    const text = responseDraft.trim();
    if (!text && statusDraft === selected.status) {
      toast.error('Write a response or change the status');
      return;
    }
    setSavingResponse(true);
    try {
      const updated = await api.adminRespondFeedback(selected.id, {
        status: statusDraft,
        admin_response: text || undefined,
      });
      setFeedback((prev) => prev.map((f) => (f.id === updated.id ? updated : f)));
      toast.success('Response saved');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not save response');
    } finally {
      setSavingResponse(false);
    }
  };

  if (loading) {
    return <div className="glass h-64 animate-pulse max-w-4xl" />;
  }

  const openCount = feedback.filter((f) => f.status === 'open').length;

  return (
    <div className="space-y-6 max-w-4xl">
      <div className="flex items-center gap-3">
        <Shield className="w-8 h-8 text-accent" />
        <div>
          <h2 className="text-2xl font-bold">Admin</h2>
          <p className="text-sm text-white/50">Manage users, roles, and feedback</p>
        </div>
      </div>

      <div className="flex gap-2">
        <button
          type="button"
          onClick={() => setTab('users')}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm transition-colors ${
            tab === 'users' ? 'bg-accent/20 text-accent ring-1 ring-accent/40' : 'glass hover:bg-white/5'
          }`}
        >
          <Users className="w-4 h-4" />
          Users
        </button>
        <button
          type="button"
          onClick={() => setTab('feedback')}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm transition-colors ${
            tab === 'feedback' ? 'bg-accent/20 text-accent ring-1 ring-accent/40' : 'glass hover:bg-white/5'
          }`}
        >
          <MessageSquare className="w-4 h-4" />
          Feedback
          {openCount > 0 && (
            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-accent/30">{openCount}</span>
          )}
        </button>
      </div>

      {tab === 'users' && (
        <>
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

          <div className="glass overflow-x-auto">
            <table className="w-full text-sm min-w-[640px]">
              <thead className="border-b border-white/10 text-white/50">
                <tr>
                  <th className="text-left p-3">User</th>
                  <th className="text-left p-3 hidden md:table-cell">Type</th>
                  <th className="text-left p-3 hidden lg:table-cell">First use</th>
                  <th className="text-left p-3 hidden lg:table-cell">Last used</th>
                  <th className="text-right p-3">Songs</th>
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
                    <td className="p-3 hidden md:table-cell text-white/60">
                      {u.is_guest ? 'Guest' : 'Registered'}
                    </td>
                    <td className="p-3 hidden lg:table-cell text-white/60 text-xs whitespace-nowrap">
                      {formatAdminDateTime(u.first_used_at)}
                    </td>
                    <td className="p-3 hidden lg:table-cell text-white/60 text-xs whitespace-nowrap">
                      {formatAdminDateTime(u.last_used_at)}
                    </td>
                    <td className="p-3 text-right font-medium tabular-nums">{u.songs_played_count}</td>
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
        </>
      )}

      {tab === 'feedback' && (
        <div className="grid lg:grid-cols-2 gap-4">
          <section className="space-y-3">
            <div className="flex flex-wrap gap-2">
              <select
                value={feedbackFilter.type}
                onChange={(e) => setFeedbackFilter((f) => ({ ...f, type: e.target.value }))}
                className="bg-surface-raised border border-white/10 rounded-lg px-3 py-1.5 text-xs"
              >
                <option value="">All types</option>
                <option value="bug">Issues</option>
                <option value="feature">Features</option>
              </select>
              <select
                value={feedbackFilter.status}
                onChange={(e) => setFeedbackFilter((f) => ({ ...f, status: e.target.value }))}
                className="bg-surface-raised border border-white/10 rounded-lg px-3 py-1.5 text-xs"
              >
                <option value="">All statuses</option>
                {FEEDBACK_STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {s.replace('_', ' ')}
                  </option>
                ))}
              </select>
            </div>

            <div className="space-y-2 max-h-[70vh] overflow-y-auto pr-1">
              {feedback.length === 0 && (
                <p className="text-sm text-white/50 glass p-4">No feedback submissions yet.</p>
              )}
              {feedback.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setSelectedId(item.id)}
                  className={`w-full text-left glass p-4 transition-colors hover:bg-white/5 ${
                    selectedId === item.id ? 'ring-2 ring-accent/50' : ''
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-2 min-w-0">
                      {item.feedback_type === 'bug' ? (
                        <Bug className="w-4 h-4 text-red-400 shrink-0" />
                      ) : (
                        <Lightbulb className="w-4 h-4 text-accent shrink-0" />
                      )}
                      <p className="font-medium truncate">{item.title}</p>
                    </div>
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-white/10 capitalize shrink-0">
                      {item.status.replace('_', ' ')}
                    </span>
                  </div>
                  <p className="text-xs text-white/40 mt-1">
                    {item.username || 'Unknown user'} · {formatAdminDateTime(item.created_at)}
                  </p>
                </button>
              ))}
            </div>
          </section>

          <section className="glass p-5 space-y-4 lg:sticky lg:top-4 h-fit">
            {!selected ? (
              <p className="text-sm text-white/50">Select a submission to view details and respond.</p>
            ) : (
              <>
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    {selected.feedback_type === 'bug' ? (
                      <Bug className="w-4 h-4 text-red-400" />
                    ) : (
                      <Lightbulb className="w-4 h-4 text-accent" />
                    )}
                    <h3 className="font-semibold">{selected.title}</h3>
                  </div>
                  <p className="text-xs text-white/40">
                    {selected.feedback_type === 'bug' ? 'Issue' : 'Feature'} ·{' '}
                    {formatAdminDateTime(selected.created_at)}
                  </p>
                </div>

                <div className="text-sm space-y-1">
                  <p className="text-white/50 text-xs">From</p>
                  <p>{selected.username || '—'}</p>
                  <p className="text-white/60 text-xs">
                    {selected.contact_email || selected.user_email || 'No email provided'}
                  </p>
                </div>

                <div>
                  <p className="text-white/50 text-xs mb-1">Description</p>
                  <p className="text-sm whitespace-pre-wrap text-white/80">{selected.description}</p>
                </div>

                {selected.admin_response && (
                  <div className="bg-accent/10 border border-accent/20 rounded-lg p-3">
                    <p className="text-xs text-accent mb-1">Previous response</p>
                    <p className="text-sm whitespace-pre-wrap">{selected.admin_response}</p>
                    {selected.responded_at && (
                      <p className="text-[10px] text-white/40 mt-2">
                        {formatAdminDateTime(selected.responded_at)}
                      </p>
                    )}
                  </div>
                )}

                <div className="space-y-2">
                  <label className="text-xs text-white/50">Status</label>
                  <select
                    value={statusDraft}
                    onChange={(e) => setStatusDraft(e.target.value)}
                    className="w-full bg-surface-raised border border-white/10 rounded-lg px-3 py-2 text-sm"
                  >
                    {FEEDBACK_STATUSES.map((s) => (
                      <option key={s} value={s}>
                        {s.replace('_', ' ')}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="space-y-2">
                  <label className="text-xs text-white/50">Your response</label>
                  <textarea
                    rows={5}
                    value={responseDraft}
                    onChange={(e) => setResponseDraft(e.target.value)}
                    placeholder="Reply to the user — they will see this on their Feedback page."
                    className="w-full bg-surface-raised border border-white/10 rounded-lg px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-accent/50"
                  />
                </div>

                <button
                  type="button"
                  className="btn-primary w-full py-2.5 text-sm"
                  disabled={savingResponse}
                  onClick={saveFeedbackResponse}
                >
                  {savingResponse ? 'Saving…' : 'Save response'}
                </button>
              </>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
