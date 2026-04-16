'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRequireAuth } from '@/hooks/useAuth';
import { apiClient } from '@/lib/api';
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Card, CardContent } from '@/components/ui/card';
import { RefreshCw, ExternalLink, Archive, Inbox } from 'lucide-react';
import { toast } from 'sonner';

interface SupportTicket {
  id: string;
  submitter_email: string;
  submitter_name: string | null;
  subject: string;
  category: string | null;
  priority: number | null;
  status: string;
  source: string;
  is_spam: boolean;
  llm_attempt_count: number;
  created_at: string;
  last_customer_message_at: string | null;
}

const STATUS_COLORS: Record<string, string> = {
  new: 'bg-blue-100 text-blue-800',
  llm_handling: 'bg-purple-100 text-purple-800',
  awaiting_customer: 'bg-yellow-100 text-yellow-800',
  escalated: 'bg-red-100 text-red-800',
  auto_resolved: 'bg-green-100 text-green-800',
  resolved: 'bg-green-100 text-green-800',
  archived: 'bg-gray-100 text-gray-600',
  spam: 'bg-red-50 text-red-400',
};

const PRIORITY_LABELS: Record<number, string> = {
  1: 'P1 Payment', 2: 'P2 Bug', 3: 'P3 Add Firm',
  4: 'P4 RFQ/NDA', 5: 'P5 General', 6: 'P6 Collab',
};

const PRIORITY_COLORS: Record<number, string> = {
  1: 'bg-red-100 text-red-800', 2: 'bg-orange-100 text-orange-800',
  3: 'bg-yellow-100 text-yellow-800', 4: 'bg-blue-100 text-blue-800',
  5: 'bg-gray-100 text-gray-700', 6: 'bg-gray-50 text-gray-500',
};

function formatDate(iso: string | null) {
  if (!iso) return '\u2014';
  return new Date(iso).toLocaleDateString(undefined, {
    month: 'short', day: 'numeric', year: 'numeric',
  });
}

type TabType = 'active' | 'archived';

export default function AdminSupportPage() {
  const { isLoading: authLoading } = useRequireAuth(['admin']);
  const [activeTab, setActiveTab] = useState<TabType>('active');
  const [tickets, setTickets] = useState<SupportTicket[]>([]);
  const [archivedTickets, setArchivedTickets] = useState<SupportTicket[]>([]);
  const [total, setTotal] = useState(0);
  const [archivedTotal, setArchivedTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [isArchivingAll, setIsArchivingAll] = useState(false);
  const [statusFilter, setStatusFilter] = useState('all');
  const [search, setSearch] = useState('');

  const fetchActive = useCallback(async (status: string) => {
    setIsLoading(true);
    try {
      const params = new URLSearchParams();
      params.set('size', '100');
      if (status !== 'all') params.set('status_filter', status);
      const res = await apiClient.get(`/admin/support/tickets?${params.toString()}`);
      const data = res.data;
      const items = (data.items ?? []).filter((t: SupportTicket) => t.status !== 'archived');
      setTickets(items);
      setTotal(data.total ?? 0);
    } catch {
      toast.error('Failed to load tickets');
    } finally {
      setIsLoading(false);
    }
  }, []);

  const fetchArchived = useCallback(async () => {
    setIsLoading(true);
    try {
      const params = new URLSearchParams();
      params.set('size', '100');
      params.set('status_filter', 'archived');
      const res = await apiClient.get(`/admin/support/tickets?${params.toString()}`);
      const data = res.data;
      setArchivedTickets(data.items ?? []);
      setArchivedTotal(data.total ?? 0);
    } catch {
      toast.error('Failed to load archived tickets');
    } finally {
      setIsLoading(false);
    }
  }, []);

  const archiveAll = useCallback(async () => {
    if (!confirm(`Archive ALL ${total} active tickets? They will move to the Archived tab.`)) return;
    setIsArchivingAll(true);
    try {
      const res = await apiClient.post('/admin/support/tickets/archive-all', {});
      toast.success(`Archived ${res.data.archived_count} tickets`);
      setTickets([]);
      setTotal(0);
      fetchArchived();
    } catch {
      toast.error('Failed to archive all tickets');
    } finally {
      setIsArchivingAll(false);
    }
  }, [total, fetchArchived]);

  useEffect(() => {
    if (authLoading) return;
    if (activeTab === 'active') fetchActive(statusFilter);
    else fetchArchived();
  }, [authLoading, activeTab, statusFilter, fetchActive, fetchArchived]);

  const currentTickets = activeTab === 'active' ? tickets : archivedTickets;

  const filtered = search.trim()
    ? currentTickets.filter(
        (t) =>
          t.submitter_email.toLowerCase().includes(search.toLowerCase()) ||
          t.subject.toLowerCase().includes(search.toLowerCase()) ||
          (t.submitter_name || '').toLowerCase().includes(search.toLowerCase())
      )
    : currentTickets;

  if (authLoading) {
    return <div className="flex items-center justify-center min-h-screen">Loading...</div>;
  }

  return (
    <div className="p-6 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Support Tickets</h1>
          <p className="text-gray-500 text-sm">
            {activeTab === 'active' ? `${total} total active tickets` : `${archivedTotal} archived tickets`}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {activeTab === 'active' && total > 0 && (
            <Button
              variant="outline"
              size="sm"
              onClick={archiveAll}
              disabled={isArchivingAll}
              className="border-orange-300 text-orange-700 hover:bg-orange-50"
            >
              <Archive className="w-4 h-4 mr-2" />
              {isArchivingAll ? 'Archiving...' : `Archive All (${total})`}
            </Button>
          )}
          <Button
            variant="outline"
            size="sm"
            onClick={() => activeTab === 'active' ? fetchActive(statusFilter) : fetchArchived()}
          >
            <RefreshCw className="w-4 h-4 mr-2" />
            Refresh
          </Button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-gray-200">
        <button
          onClick={() => { setActiveTab('active'); setSearch(''); }}
          className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
            activeTab === 'active'
              ? 'border-blue-600 text-blue-600'
              : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
          }`}
        >
          <Inbox className="w-4 h-4" />
          Active Tickets
          <span className={`ml-1 px-1.5 py-0.5 rounded-full text-xs font-medium ${
            activeTab === 'active' ? 'bg-blue-100 text-blue-700' : 'bg-gray-100 text-gray-600'
          }`}>
            {total}
          </span>
        </button>
        <button
          onClick={() => { setActiveTab('archived'); setSearch(''); }}
          className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
            activeTab === 'archived'
              ? 'border-gray-600 text-gray-700'
              : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
          }`}
        >
          <Archive className="w-4 h-4" />
          Archived
          <span className={`ml-1 px-1.5 py-0.5 rounded-full text-xs font-medium ${
            activeTab === 'archived' ? 'bg-gray-200 text-gray-700' : 'bg-gray-100 text-gray-600'
          }`}>
            {archivedTotal}
          </span>
        </button>
      </div>

      {/* Filters + Table */}
      <Card>
        <CardContent className="pt-4 pb-3">
          <div className="flex flex-col sm:flex-row gap-3">
            <Input
              placeholder="Search email, name or subject..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="flex-1"
            />
            {activeTab === 'active' && (
              <Select value={statusFilter} onValueChange={setStatusFilter}>
                <SelectTrigger className="w-48">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Active</SelectItem>
                  <SelectItem value="new">New</SelectItem>
                  <SelectItem value="escalated">Escalated</SelectItem>
                  <SelectItem value="llm_handling">LLM Handling</SelectItem>
                  <SelectItem value="awaiting_customer">Awaiting Customer</SelectItem>
                  <SelectItem value="auto_resolved">Auto Resolved</SelectItem>
                  <SelectItem value="resolved">Resolved</SelectItem>
                  <SelectItem value="spam">Spam</SelectItem>
                </SelectContent>
              </Select>
            )}
          </div>
        </CardContent>

        <CardContent className="p-0">
          {isLoading ? (
            <div className="py-12 text-center text-gray-500">Loading tickets...</div>
          ) : filtered.length === 0 ? (
            <div className="py-12 text-center text-gray-500">
              {activeTab === 'archived' ? 'No archived tickets.' : 'No tickets found.'}
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Submitter</TableHead>
                  <TableHead>Subject</TableHead>
                  <TableHead>Priority</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Created</TableHead>
                  <TableHead></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.map((t) => {
                  const priorityLabel = t.priority ? (PRIORITY_LABELS[t.priority] || String(t.priority)) : '\u2014';
                  const priorityColor = t.priority ? (PRIORITY_COLORS[t.priority] || 'bg-gray-100 text-gray-700') : 'bg-gray-100 text-gray-700';
                  const statusColor = STATUS_COLORS[t.status] || 'bg-gray-100 text-gray-700';
                  return (
                    <TableRow key={t.id} className={activeTab === 'archived' ? 'opacity-75' : ''}>
                      <TableCell>
                        <div className="font-medium text-sm">{t.submitter_name || '\u2014'}</div>
                        <div className="text-xs text-gray-500">{t.submitter_email}</div>
                      </TableCell>
                      <TableCell className="max-w-xs truncate text-sm">{t.subject}</TableCell>
                      <TableCell>
                        <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${priorityColor}`}>
                          {priorityLabel}
                        </span>
                      </TableCell>
                      <TableCell>
                        <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${statusColor}`}>
                          {t.status.replace(/_/g, ' ')}
                        </span>
                      </TableCell>
                      <TableCell className="text-sm text-gray-500">{formatDate(t.created_at)}</TableCell>
                      <TableCell>
                        <Link href={`/admin/support/${t.id}`}>
                          <Button variant="ghost" size="sm">
                            <ExternalLink className="w-4 h-4" />
                          </Button>
                        </Link>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
