'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { useRequireAuth } from '@/hooks/useAuth';
import { api } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Search, Ban, Download, RefreshCw, RotateCcw, Trash2 } from 'lucide-react';
import { toast } from 'sonner';

interface AdminUser {
  id: string;
  email: string;
  full_name: string | null;
  business_name: string | null;
  roles: string[];
  is_super_admin: boolean;
  monthly_search_count: number;
  search_count_reset_at: string | null;
  last_login_at: string | null;
  failed_login_count: number;
  locked_until: string | null;
  membership_type: string;
  subscription_status: string | null;
}

const MEMBERSHIP_QUOTA: Record<string, number> = {
  free: 10,
  search_tier_1: 100,
};

function formatDate(iso: string | null) {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

function formatTime(date: Date | null) {
  if (!date) return '';
  return date.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

export default function AdminUsersPage() {
  const { isLoading: authLoading } = useRequireAuth(['admin']);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [resetingId, setResetingId] = useState<string | null>(null);
  const [suspendingId, setSuspendingId] = useState<string | null>(null);
  const [removingId, setRemovingId] = useState<string | null>(null);
  const [lastRefreshed, setLastRefreshed] = useState<Date | null>(null);
  const searchQueryRef = useRef(searchQuery);

  useEffect(() => {
    searchQueryRef.current = searchQuery;
  }, [searchQuery]);

  const fetchUsers = useCallback(async (q?: string) => {
    setIsLoading(true);
    try {
      const params = new URLSearchParams();
      if (q) params.set('search', q);
      params.set('size', '200');
      const res = await api.admin.listUsers(params.toString());
      const data = res.data;
      setUsers(data.items ?? []);
      setTotal(data.total ?? 0);
      setLastRefreshed(new Date());
    } catch {
      toast.error('Failed to load users');
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Initial load
  useEffect(() => {
    fetchUsers();
  }, [fetchUsers]);

  // Auto-refresh when tab becomes visible (picks up search counts done in other tabs)
  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        fetchUsers(searchQueryRef.current || undefined);
      }
    };
    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange);
  }, [fetchUsers]);

  // Auto-refresh every 30 seconds while page is open and visible
  useEffect(() => {
    const interval = setInterval(() => {
      if (document.visibilityState === 'visible') {
        fetchUsers(searchQueryRef.current || undefined);
      }
    }, 30000);
    return () => clearInterval(interval);
  }, [fetchUsers]);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    fetchUsers(searchQuery);
  };

  const handleResetQuota = async (userId: string, email: string) => {
    setResetingId(userId);
    try {
      await api.admin.resetUserSearchQuota(userId);
      toast.success(`Search quota reset for ${email}`);
      setUsers(prev => prev.map(u => u.id === userId ? { ...u, monthly_search_count: 0 } : u));
      // Re-fetch after short delay to confirm backend state
      setTimeout(() => fetchUsers(searchQueryRef.current || undefined), 800);
    } catch {
      toast.error('Failed to reset search quota');
    } finally {
      setResetingId(null);
    }
  };

  const handleSuspend = async (userId: string, email: string) => {
    if (!confirm(`Suspend ${email}? They will be logged out immediately.`)) return;
    setSuspendingId(userId);
    try {
      await api.admin.suspendUser(userId);
      toast.success(`${email} suspended`);
      fetchUsers(searchQuery || undefined);
    } catch {
      toast.error('Failed to suspend user');
    } finally {
      setSuspendingId(null);
    }
  };

  const handleRemove = async (userId: string, email: string) => {
    const msg = [
      `This will scramble the credentials for ${email} and free their email address.`,
      'They can re-register with the same email as a fresh account.',
      'Historical data (RFQs, quotes, memberships) will be preserved but unlinked from their login.',
      '',
      'Continue?'
    ].join('\n');
    if (!confirm(msg)) return;
    setRemovingId(userId);
    try {
      await api.admin.removeUser(userId);
      toast.success(`${email} has been removed. Their email is now free for re-registration.`);
      fetchUsers(searchQuery || undefined);
    } catch {
      toast.error('Failed to remove user');
    } finally {
      setRemovingId(null);
    }
  };

  const handleExportCSV = () => {
    const apiBase = (process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000') + '/api/v1';
    window.open(`${apiBase}/admin/users/export.csv`, '_blank');
  };

  if (authLoading) {
    return (
      <div className="container py-8">
        <div className="flex items-center justify-center h-64">
          <p className="text-muted-foreground">Loading...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="container py-8">
      <div className="flex justify-between items-center mb-8">
        <div>
          <h1 className="text-3xl font-bold">User Management</h1>
          <p className="text-muted-foreground">
            {total} total users
            {lastRefreshed && (
              <span className="ml-3 text-xs text-green-600">
                &bull; Updated {formatTime(lastRefreshed)}
              </span>
            )}
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => fetchUsers(searchQuery || undefined)} disabled={isLoading}>
            <RefreshCw className={`h-4 w-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
          <Button variant="outline" size="sm" onClick={handleExportCSV}>
            <Download className="h-4 w-4 mr-2" />
            Export CSV
          </Button>
        </div>
      </div>

      {/* Search bar */}
      <Card className="mb-6">
        <CardContent className="pt-6">
          <form onSubmit={handleSearch} className="flex gap-3">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Search by email, name, or business..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-10"
              />
            </div>
            <Button type="submit" disabled={isLoading}>Search</Button>
          </form>
        </CardContent>
      </Card>

      {/* Quota Legend */}
      <div className="mb-4 flex flex-wrap gap-4 text-sm text-muted-foreground">
        <span className="font-medium text-foreground">Monthly search quotas:</span>
        <span>&#128275; Unregistered: <strong>3</strong></span>
        <span>&#128100; Free account: <strong>10</strong></span>
        <span>&#11088; Search Plan ($50/mo): <strong>100</strong></span>
        <span className="ml-auto text-xs italic">Auto-refreshes every 30s &bull; Updates on tab focus</span>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>All Users ({isLoading ? '...' : users.length})</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="flex items-center justify-center h-32">
              <p className="text-muted-foreground">Loading users...</p>
            </div>
          ) : users.length === 0 ? (
            <div className="flex items-center justify-center h-32">
              <p className="text-muted-foreground">No users found</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Email / Name</TableHead>
                    <TableHead>Roles</TableHead>
                    <TableHead>Membership</TableHead>
                    <TableHead>Searches Used</TableHead>
                    <TableHead>Reset At</TableHead>
                    <TableHead>Last Login</TableHead>
                    <TableHead>Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {users.map((user) => {
                    const quota = MEMBERSHIP_QUOTA[user.membership_type] ?? 10;
                    const pct = Math.min(100, Math.round((user.monthly_search_count / quota) * 100));
                    const overLimit = user.monthly_search_count >= quota;
                    return (
                      <TableRow key={user.id}>
                        <TableCell>
                          <div>
                            <div className="font-medium">{user.email}</div>
                            {(user.full_name || user.business_name) && (
                              <div className="text-xs text-muted-foreground">
                                {[user.full_name, user.business_name].filter(Boolean).join(' · ')}
                              </div>
                            )}
                          </div>
                        </TableCell>
                        <TableCell>
                          <div className="flex gap-1 flex-wrap">
                            {(user.roles ?? []).map((role) => (
                              <Badge key={role} variant="secondary" className="text-xs">
                                {role}
                              </Badge>
                            ))}
                            {user.is_super_admin && (
                              <Badge variant="destructive" className="text-xs">super</Badge>
                            )}
                          </div>
                        </TableCell>
                        <TableCell>
                          <Badge variant={user.membership_type === 'free' ? 'outline' : 'default'} className="text-xs">
                            {user.membership_type}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          <div className="flex flex-col gap-1">
                            <span className={`text-sm font-medium ${overLimit ? 'text-red-600' : ''}`}>
                              {user.monthly_search_count} / {quota}
                            </span>
                            <div className="h-1.5 w-20 rounded-full bg-gray-200">
                              <div
                                className={`h-1.5 rounded-full ${
                                  overLimit ? 'bg-red-500' : pct > 70 ? 'bg-yellow-500' : 'bg-green-500'
                                }`}
                                style={{ width: `${pct}%` }}
                              />
                            </div>
                          </div>
                        </TableCell>
                        <TableCell className="text-xs text-muted-foreground">
                          {formatDate(user.search_count_reset_at)}
                        </TableCell>
                        <TableCell className="text-sm text-muted-foreground">
                          {formatDate(user.last_login_at)}
                        </TableCell>
                        <TableCell>
                          <div className="flex gap-1">
                            <Button
                              variant="outline"
                              size="sm"
                              title="Reset search quota to 0"
                              onClick={() => handleResetQuota(user.id, user.email)}
                              disabled={resetingId === user.id}
                            >
                              <RotateCcw className={`h-3.5 w-3.5 ${resetingId === user.id ? 'animate-spin' : ''}`} />
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              title="Suspend user"
                              onClick={() => handleSuspend(user.id, user.email)}
                              disabled={suspendingId === user.id}
                              className="text-red-600 hover:text-red-700 hover:bg-red-50"
                            >
                              <Ban className="h-3.5 w-3.5" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              title="Remove user (scrambles credentials, frees email for re-registration)"
                              onClick={() => handleRemove(user.id, user.email)}
                              disabled={removingId === user.id || user.email.startsWith('removed_')}
                              className="text-red-800 hover:text-red-900 hover:bg-red-100"
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </Button>
                          </div>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
