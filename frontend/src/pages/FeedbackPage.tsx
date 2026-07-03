import { useEffect, useState } from 'react';
import { Bug, Lightbulb, Send } from 'lucide-react';
import { api } from '@/lib/api';
import toast from 'react-hot-toast';

type FeedbackType = 'bug' | 'feature';

interface FeedbackItem {
  id: string;
  feedback_type: string;
  title: string;
  status: string;
  created_at: string;
  admin_response: string | null;
  responded_at: string | null;
}

export default function FeedbackPage() {
  const [type, setType] = useState<FeedbackType>('bug');
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [email, setEmail] = useState('');
  const [sending, setSending] = useState(false);
  const [history, setHistory] = useState<FeedbackItem[]>([]);

  const loadHistory = () => api.getMyFeedback().then(setHistory).catch(() => {});

  useEffect(() => {
    loadHistory();
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (title.trim().length < 3) {
      toast.error('Title must be at least 3 characters');
      return;
    }
    if (description.trim().length < 10) {
      toast.error('Description must be at least 10 characters');
      return;
    }
    setSending(true);
    try {
      await api.submitFeedback({
        feedback_type: type,
        title: title.trim(),
        description: description.trim(),
        contact_email: email.trim() || undefined,
      });
      toast.success('Thank you! Your feedback was submitted.');
      setTitle('');
      setDescription('');
      loadHistory();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to submit');
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="space-y-8 max-w-2xl">
      <div>
        <h2 className="text-2xl font-bold">Feedback</h2>
        <p className="text-white/50 text-sm mt-1">
          Report a bug or suggest a new feature. We read every submission.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="glass p-6 space-y-5">
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => setType('bug')}
            className={`flex-1 flex items-center justify-center gap-2 py-3 rounded-lg transition-colors ${
              type === 'bug' ? 'bg-red-500/20 ring-2 ring-red-400' : 'bg-white/5 hover:bg-white/10'
            }`}
          >
            <Bug className="w-4 h-4" />
            Report issue
          </button>
          <button
            type="button"
            onClick={() => setType('feature')}
            className={`flex-1 flex items-center justify-center gap-2 py-3 rounded-lg transition-colors ${
              type === 'feature'
                ? 'bg-accent/20 ring-2 ring-accent'
                : 'bg-white/5 hover:bg-white/10'
            }`}
          >
            <Lightbulb className="w-4 h-4" />
            Request feature
          </button>
        </div>

        <input
          required
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder={type === 'bug' ? 'Brief issue title' : 'Feature idea title'}
          className="w-full glass px-4 py-3 focus:outline-none focus:ring-2 focus:ring-accent/50"
        />

        <textarea
          required
          minLength={10}
          rows={5}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder={
            type === 'bug'
              ? 'What happened? What did you expect? Steps to reproduce...'
              : 'Describe the feature and how it would help you...'
          }
          className="w-full glass px-4 py-3 focus:outline-none focus:ring-2 focus:ring-accent/50 resize-none"
        />

        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="Email (optional, for follow-up)"
          className="w-full glass px-4 py-3 focus:outline-none focus:ring-2 focus:ring-accent/50"
        />

        <button
          type="submit"
          disabled={sending}
          className="btn-primary w-full py-3 flex items-center justify-center gap-2"
        >
          <Send className="w-4 h-4" />
          {sending ? 'Submitting...' : 'Submit feedback'}
        </button>
      </form>

      {history.length > 0 && (
        <section className="space-y-3">
          <h3 className="font-semibold">Your recent submissions</h3>
          {history.map((item) => (
            <div key={item.id} className="glass p-4 space-y-3">
              <div className="flex justify-between items-start gap-4">
                <div>
                  <p className="font-medium">{item.title}</p>
                  <p className="text-xs text-white/40 mt-1">
                    {item.feedback_type === 'bug' ? 'Issue' : 'Feature'} ·{' '}
                    {new Date(item.created_at).toLocaleDateString()}
                  </p>
                </div>
                <span className="text-xs px-2 py-1 rounded-full bg-white/10 capitalize shrink-0">
                  {item.status.replace('_', ' ')}
                </span>
              </div>
              {item.admin_response && (
                <div className="bg-accent/10 border border-accent/20 rounded-lg p-3">
                  <p className="text-xs text-accent font-medium mb-1">Team response</p>
                  <p className="text-sm text-white/80 whitespace-pre-wrap">{item.admin_response}</p>
                  {item.responded_at && (
                    <p className="text-[10px] text-white/40 mt-2">
                      {new Date(item.responded_at).toLocaleString()}
                    </p>
                  )}
                </div>
              )}
            </div>
          ))}
        </section>
      )}
    </div>
  );
}
