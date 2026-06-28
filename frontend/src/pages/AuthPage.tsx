import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Disc3, LogIn, UserPlus, User } from 'lucide-react';
import { api } from '@/lib/api';
import { usePlayerStore } from '@/stores/playerStore';
import toast from 'react-hot-toast';

type Tab = 'login' | 'register' | 'guest';

export default function AuthPage() {
  const navigate = useNavigate();
  const setAuth = usePlayerStore((s) => s.setAuth);
  const init = usePlayerStore((s) => s.init);
  const [tab, setTab] = useState<Tab>('login');
  const [loading, setLoading] = useState(false);

  const [loginForm, setLoginForm] = useState({ username: '', password: '' });
  const [registerForm, setRegisterForm] = useState({
    username: '',
    password: '',
    email: '',
    confirm: '',
  });

  const finishAuth = async (
    res: { access_token: string; username: string; is_guest: boolean },
    displayName?: string,
  ) => {
    setAuth(res.access_token, res.username, res.is_guest);
    if (displayName) localStorage.setItem('noverep_display_name', displayName);
    await init();
    navigate('/', { replace: true });
  };

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      const res = await api.login(loginForm.username, loginForm.password);
      await finishAuth(res);
      toast.success('Welcome back!');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Login failed');
    } finally {
      setLoading(false);
    }
  };

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    if (registerForm.password !== registerForm.confirm) {
      toast.error('Passwords do not match');
      return;
    }
    setLoading(true);
    try {
      const res = await api.register(
        registerForm.username,
        registerForm.password,
        registerForm.email || undefined,
      );
      await finishAuth(res, registerForm.username);
      toast.success('Account created!');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Registration failed');
    } finally {
      setLoading(false);
    }
  };

  const handleGuest = async () => {
    setLoading(true);
    try {
      const res = await api.guestLogin();
      await finishAuth(res);
      toast.success('Continuing as guest');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not start guest session');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4 bg-gradient-to-br from-surface via-[#12121a] to-[#0a0a10]">
      <div className="w-full max-w-md space-y-6">
        <div className="text-center space-y-2">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-gradient-to-br from-accent to-purple-400 mb-2">
            <Disc3 className="w-9 h-9" />
          </div>
          <h1 className="text-3xl font-bold">NoRepeat</h1>
          <p className="text-white/50 text-sm">Never hear the same song twice</p>
        </div>

        <div className="glass p-6 space-y-6">
          <div className="flex gap-1 p-1 bg-white/5 rounded-lg">
            {(
              [
                { id: 'login' as Tab, label: 'Login', icon: LogIn },
                { id: 'register' as Tab, label: 'Register', icon: UserPlus },
              ]
            ).map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                onClick={() => setTab(id)}
                className={`flex-1 flex items-center justify-center gap-2 py-2.5 rounded-md text-sm font-medium transition-colors ${
                  tab === id ? 'bg-accent text-white' : 'text-white/60 hover:text-white'
                }`}
              >
                <Icon className="w-4 h-4" />
                {label}
              </button>
            ))}
          </div>

          {tab === 'login' && (
            <form onSubmit={handleLogin} className="space-y-4">
              <input
                required
                placeholder="Username"
                value={loginForm.username}
                onChange={(e) => setLoginForm({ ...loginForm, username: e.target.value })}
                className="w-full glass px-4 py-3 focus:outline-none focus:ring-2 focus:ring-accent/50"
              />
              <input
                required
                type="password"
                placeholder="Password"
                value={loginForm.password}
                onChange={(e) => setLoginForm({ ...loginForm, password: e.target.value })}
                className="w-full glass px-4 py-3 focus:outline-none focus:ring-2 focus:ring-accent/50"
              />
              <button type="submit" disabled={loading} className="btn-primary w-full py-3">
                {loading ? 'Signing in...' : 'Sign in'}
              </button>
            </form>
          )}

          {tab === 'register' && (
            <form onSubmit={handleRegister} className="space-y-4">
              <input
                required
                placeholder="Username"
                value={registerForm.username}
                onChange={(e) => setRegisterForm({ ...registerForm, username: e.target.value })}
                className="w-full glass px-4 py-3 focus:outline-none focus:ring-2 focus:ring-accent/50"
              />
              <input
                type="email"
                placeholder="Email (optional)"
                value={registerForm.email}
                onChange={(e) => setRegisterForm({ ...registerForm, email: e.target.value })}
                className="w-full glass px-4 py-3 focus:outline-none focus:ring-2 focus:ring-accent/50"
              />
              <input
                required
                type="password"
                placeholder="Password (min 6 characters)"
                minLength={6}
                value={registerForm.password}
                onChange={(e) => setRegisterForm({ ...registerForm, password: e.target.value })}
                className="w-full glass px-4 py-3 focus:outline-none focus:ring-2 focus:ring-accent/50"
              />
              <input
                required
                type="password"
                placeholder="Confirm password"
                value={registerForm.confirm}
                onChange={(e) => setRegisterForm({ ...registerForm, confirm: e.target.value })}
                className="w-full glass px-4 py-3 focus:outline-none focus:ring-2 focus:ring-accent/50"
              />
              <button type="submit" disabled={loading} className="btn-primary w-full py-3">
                {loading ? 'Creating account...' : 'Create account'}
              </button>
            </form>
          )}

          <div className="relative">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-white/10" />
            </div>
            <div className="relative flex justify-center text-xs">
              <span className="bg-surface-raised px-2 text-white/40">or</span>
            </div>
          </div>

          <button
            onClick={handleGuest}
            disabled={loading}
            className="w-full glass-hover py-3 flex items-center justify-center gap-2 text-sm"
          >
            <User className="w-4 h-4" />
            Continue as guest
          </button>
        </div>
      </div>
    </div>
  );
}
