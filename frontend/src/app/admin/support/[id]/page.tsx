'use client';

import DOMPurify from 'isomorphic-dompurify';

import { useState, useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useRequireAuth } from '@/hooks/useAuth';
import { apiClient } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ArrowLeft, Send, AlertTriangle, CheckCircle, Archive, Ban } from 'lucide-react';
import { toast } from 'sonner';
import Link from 'next/link';

interface TicketMessage {
  id: string;
  sender_type: string;
  sender_name: string | null;
  body_text: string | null;
  body_html: string | null;
  direction: string;
  created_at: string;
}

interface TicketEvent {
  id: string;
  event_type: string;
  payload: Record<string, unknown> | null;
  created_at: string;
}

interface TicketDetail {
  id: string;
  submitter_email: string;
  submitter_name: string | null;
  subject: string;
  body: string | null;
  category: string | null;
  priority: number | null;
  status: string;
  source: string;
  is_spam: boolean;
  llm_attempt_count: number;
  created_at: string;
  resolved_at: string | null;
  messages: TicketMessage[];
  events: TicketEvent[];
}

const STATUS_BADGE: Record<string, string> = {
  new: 'bg-blue-100 text-blue-800',
  escalated: 'bg-red-100 text-red-800',
  awaiting_customer: 'bg-yellow-100 text-yellow-800',
  llm_handling: 'bg-purple-100 text-purple-800',
  auto_resolved: 'bg-green-100 text-green-800',
  resolved: 'bg-green-100 text-green-800',
  archived: 'bg-gray-100 text-gray-600',
  spam: 'bg-red-50 text-red-400',
};

const SENDER_COLORS: Record<string, string> = {
  customer: 'bg-gray-100 border-gray-200',
  admin: 'bg-blue-50 border-blue-200',
  llm: 'bg-purple-50 border-purple-200',
};

function formatDt(iso: string) {
  return new Date(iso).toLocaleString(undefined, {
    month: 'short', day: 'numeric', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}

export default function AdminSupportDetailPage() {
  const { isLoading: authLoading } = useRequireAuth(['admin']);
  const params = useParams();
  const router = useRouter();
  const ticketId = params.id as string;

  const [ticket, setTicket] = useState(null as TicketDetail | null);
  const [isLoading, setIsLoading] = useState(true);
  const [replyHtml, setReplyHtml] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [isActing, setIsActing] = useState(false);

  const fetchTicket = async (silent = false) => {
    if (!silent) setIsLoading(true);
    try {
      const res = await apiClient.get(`/admin/support/tickets/${ticketId}`);
      setTicket(res.data);
    } catch {
      if (!silent) toast.error('Failed to load ticket');
    } finally {
      if (!silent) setIsLoading(false);
    }
  };

  useEffect(() => {
    if (authLoading || !ticketId) return;
    fetchTicket();
    // Live updates: silently refresh the thread every 20s and whenever the admin
    // refocuses the tab, so new customer replies appear without leaving the page.
    const interval = setInterval(() => fetchTicket(true), 20_000);
    const onFocus = () => fetchTicket(true);
    window.addEventListener('focus', onFocus);
    document.addEventListener('visibilitychange', onFocus);
    return () => {
      clearInterval(interval);
      window.removeEventListener('focus', onFocus);
      document.removeEventListener('visibilitychange', onFocus);
    };
  }, [authLoading, ticketId]);

  const handleReply = async () => {
    if (!replyHtml.trim()) {
      toast.error('Reply cannot be empty');
      return;
    }
    setIsSending(true);
    try {
      await apiClient.post(`/admin/support/tickets/${ticketId}/reply`, {
        body_html: '<p>' + replyHtml.trim() + '</p>',
        body_text: replyHtml.trim(),
      });
      toast.success('Reply sent');
      setReplyHtml('');
      await fetchTicket();
    } catch {
      toast.error('Failed to send reply');
    } finally {
      setIsSending(false);
    }
  };

  const doAction = async (action: string, body?: Record<string, unknown>) => {
    setIsActing(true);
    try {
      await apiClient.post(`/admin/support/tickets/${ticketId}/${action}`, body || {});
      toast.success(`Ticket ${action.replace('_', ' ')} successful`);
      await fetchTicket();
    } catch {
      toast.error(`Action failed: ${action}`);
    } finally {
      setIsActing(false);
    }
  };

  if (authLoading || isLoading) {
    return <div className="flex items-center justify-center min-h-screen">Loading...</div>;
  }

  if (!ticket) {
    return (
      <div className="p-6">
        <p className="text-gray-500">Ticket not found.</p>
        <Link href="/admin/support"><Button variant="outline" className="mt-4">Back to Tickets</Button></Link>
      </div>
    );
  }

  const statusColor = STATUS_BADGE[ticket.status] || 'bg-gray-100 text-gray-700';
  const isResolved = ticket.status === 'resolved' || ticket.status === 'archived';

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      <div className="flex items-center gap-3">
        <Link href="/admin/support">
          <Button variant="ghost" size="sm">
            <ArrowLeft className="w-4 h-4 mr-1" /> Back
          </Button>
        </Link>
        <h1 className="text-xl font-bold text-gray-900 flex-1 truncate">{ticket.subject}</h1>
        <span className={`px-2 py-1 rounded text-xs font-medium ${statusColor}`}>
          {ticket.status.replace(/_/g, ' ')}
        </span>
      </div>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium text-gray-500">Ticket Info</CardTitle>
        </CardHeader>
        <CardContent className="text-sm">
          <div className="grid grid-cols-1 gap-3">
            <div className="flex items-start gap-2">
              <span className="text-gray-400 w-20 shrink-0 text-xs pt-0.5">From</span>
              <div>
                <p className="font-medium text-gray-900">{ticket.submitter_email}</p>
                {ticket.submitter_name && ticket.submitter_name !== ticket.submitter_email && (
                  <p className="text-gray-500 text-xs">{ticket.submitter_name}</p>
                )}
              </div>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-gray-400 w-20 shrink-0 text-xs">Category</span>
              <p className="font-medium capitalize text-gray-900">{ticket.category || '—'}</p>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-gray-400 w-20 shrink-0 text-xs">Priority</span>
              <p className="font-medium text-gray-900">P{ticket.priority || '—'}</p>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-gray-400 w-20 shrink-0 text-xs">Source</span>
              <p className="font-medium text-gray-900 capitalize">{ticket.source.replace(/_/g, ' ')}</p>
            </div>
          </div>
        </CardContent>
      </Card>

      <div className="flex flex-wrap gap-2">
        {!isResolved && (
          <Button size="sm" variant="outline" className="text-green-700 border-green-300"
            disabled={isActing} onClick={() => doAction('resolve', { resolution_note: 'Resolved by admin' })}>
            <CheckCircle className="w-4 h-4 mr-1" /> Resolve
          </Button>
        )}
        {!isResolved && (
          <Button size="sm" variant="outline" className="text-red-700 border-red-300"
            disabled={isActing} onClick={() => doAction('escalate', { reason: 'Manually escalated by admin' })}>
            <AlertTriangle className="w-4 h-4 mr-1" /> Escalate
          </Button>
        )}
        <Button size="sm" variant="outline" className="text-gray-600"
          disabled={isActing} onClick={() => doAction('archive')}>
          <Archive className="w-4 h-4 mr-1" /> Archive
        </Button>
        <Button size="sm" variant="outline" className="text-red-400 border-red-200"
          disabled={isActing} onClick={() => doAction('spam')}>
          <Ban className="w-4 h-4 mr-1" /> Mark Spam
        </Button>
      </div>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium text-gray-500">Thread ({ticket.messages.length} messages)</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {ticket.messages.length === 0 && (
            <p className="text-gray-400 text-sm">No messages yet.</p>
          )}
          {ticket.messages.map((m) => {
            const msgColor = SENDER_COLORS[m.sender_type] || 'bg-gray-50 border-gray-100';
            const label = m.sender_type === 'customer' ? (m.sender_name || ticket.submitter_email)
              : m.sender_type === 'llm' ? 'AI Support' : (m.sender_name || 'Admin');
            const bodyHtml = m.body_html || (m.sender_type === 'customer' && !m.body_text ? ticket.body : null);
            const bodyText = m.body_text || (m.sender_type === 'customer' ? ticket.body : null);
            return (
              <div key={m.id} className={`p-3 rounded border ${msgColor}`}>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs font-semibold text-gray-700">{label}</span>
                  <span className="text-xs text-gray-400">{formatDt(m.created_at)}</span>
                </div>
                {bodyHtml ? (
                  <div className="text-sm text-gray-800" dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(bodyHtml) }} />
                ) : bodyText ? (
                  <p className="text-sm text-gray-800 whitespace-pre-wrap">{bodyText}</p>
                ) : (
                  <p className="text-sm text-gray-400 italic">
                    {m.sender_type === 'customer'
                      ? `No email body was captured from Resend. Subject received: "${ticket.subject}"`
                      : '(no content)'}
                  </p>
                )}
              </div>
            );
          })}
        </CardContent>
      </Card>

      {!isResolved && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-gray-500">Admin Reply</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <Textarea
              value={replyHtml}
              onChange={(e) => setReplyHtml(e.target.value)}
              placeholder="Type your reply to the customer..."
              rows={5}
            />
            <Button onClick={handleReply} disabled={isSending}>
              <Send className="w-4 h-4 mr-2" />
              {isSending ? 'Sending...' : 'Send Reply'}
            </Button>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium text-gray-500">Event Log ({ticket.events.length})</CardTitle>
        </CardHeader>
        <CardContent className="space-y-1">
          {ticket.events.map((ev) => (
            <div key={ev.id} className="flex items-start gap-2 text-xs text-gray-500 py-1 border-b border-gray-50">
              <span className="font-mono text-gray-400">{formatDt(ev.created_at)}</span>
              <span className="font-medium text-gray-700">{ev.event_type.replace(/_/g, ' ')}</span>
              {ev.payload && Object.keys(ev.payload).length > 0 && (
                <span className="text-gray-400">{JSON.stringify(ev.payload)}</span>
              )}
            </div>
          ))}
          {ticket.events.length === 0 && <p className="text-gray-400">No events recorded.</p>}
        </CardContent>
      </Card>
    </div>
  );
}
