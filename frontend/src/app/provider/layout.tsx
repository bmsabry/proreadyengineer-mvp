'use client';

import { useState } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import Link from 'next/link';
import {
  LayoutDashboard, FileText, CheckCircle, Clock,
  MessageSquare, Archive, User, LogOut, Home, LifeBuoy, X
} from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';

const navItems = [
  { href: '/',                        label: 'Main Page',     icon: Home,            tooltip: 'Return to the ProReadyEngineer landing page' },
  { href: '/provider/dashboard',      label: 'Dashboard',     icon: LayoutDashboard, tooltip: 'Account overview, analytics, tasks, and activity' },
  { href: '/provider/active-rfqs',    label: 'Active RFQs',   icon: FileText,        tooltip: 'Unlocked RFQs open for your quote submission' },
  { href: '/provider/accepted-rfqs',  label: 'Accepted RFQs', icon: CheckCircle,     tooltip: 'RFQs where the customer selected your firm' },
  { href: '/provider/pending-rfqs',   label: 'Pending RFQs',  icon: Clock,           tooltip: 'RFQ invitations awaiting your unlock decision' },
  { href: '/provider/quoted-rfqs',    label: 'Quoted RFQs',   icon: MessageSquare,   tooltip: 'RFQs where you have already submitted a quote' },
  { href: '/provider/all-rfqs',       label: 'All RFQs',      icon: Archive,         tooltip: 'Full history of all RFQs you have accessed' },
  { href: '/provider/profile',        label: 'Profile',       icon: User,            tooltip: 'Firm profile, subscription plan, and account settings' },
];

export default function ProviderLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { logout } = useAuth();
  const [showContact, setShowContact] = useState(false);
  const [form, setForm] = useState({ category: 'general', subject: '', message: '' });
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);

  const handleSignOut = async () => {
    try { await logout(); } catch { /* ignore */ }
    router.push('/login');
  };

  const handleContactSubmit = async () => {
    if (!form.subject.trim() || !form.message.trim()) return;
    setSubmitting(true);
    try {
      const { apiClient } = await import('@/lib/api');
      await apiClient.post('/support/contact-authenticated', form);
      setSuccess(true);
      setTimeout(() => {
        setShowContact(false);
        setSuccess(false);
        setForm({ category: 'general', subject: '', message: '' });
      }, 2500);
    } catch (err: any) {
      const detail = err?.response?.data?.detail || err?.response?.status || err?.message || String(err);
      alert('Failed to submit (' + detail + '). Please email info@mail.promechdirectory.com directly.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <nav className="bg-[#1e3a5f] text-white shadow-lg sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center h-14 overflow-x-auto scrollbar-hide">
            <div className="flex items-center gap-1 flex-nowrap">
              {navItems.map(({ href, label, icon: Icon, tooltip }) => {
                const isActive = href === '/'
                  ? pathname === '/'
                  : pathname === href || pathname.startsWith(href + '/');
                return (
                  <Link
                    key={href}
                    href={href}
                    title={tooltip}
                    className={`flex items-center gap-1.5 px-3 py-2 rounded-md text-sm font-medium whitespace-nowrap transition-colors duration-150 ${
                      isActive
                        ? 'bg-blue-600 text-white shadow-sm'
                        : 'text-blue-100 hover:bg-[#2a4d7a] hover:text-white'
                    }`}
                  >
                    <Icon size={14} />
                    <span>{label}</span>
                  </Link>
                );
              })}
              <div className="w-px h-5 bg-blue-500 mx-1 flex-shrink-0" />
              <button
                onClick={() => setShowContact(true)}
                className="flex items-center gap-1.5 px-3 py-2 rounded-md text-sm font-medium whitespace-nowrap text-blue-100 hover:bg-[#2a4d7a] hover:text-white transition-colors duration-150"
              >
                <LifeBuoy size={14} />
                <span>Contact Support</span>
              </button>
              <div className="w-px h-5 bg-blue-500 mx-1 flex-shrink-0" />
              <button
                onClick={handleSignOut}
                className="flex items-center gap-1.5 px-3 py-2 rounded-md text-sm font-medium whitespace-nowrap text-blue-100 hover:bg-red-700 hover:text-white transition-colors duration-150"
              >
                <LogOut size={14} />
                <span>Sign Out</span>
              </button>
            </div>
          </div>
        </div>
      </nav>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {children}
      </main>

      {/* Contact Support Modal */}
      {showContact && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md p-6">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <LifeBuoy className="h-5 w-5 text-[#1e3a5f]" />
                <h2 className="text-lg font-bold text-slate-900">Contact Support</h2>
              </div>
              <button onClick={() => setShowContact(false)} className="text-gray-400 hover:text-gray-600">
                <X className="h-5 w-5" />
              </button>
            </div>

            {success ? (
              <div className="text-center py-8">
                <CheckCircle className="h-12 w-12 text-green-500 mx-auto mb-3" />
                <p className="font-semibold text-slate-800">Message sent!</p>
                <p className="text-sm text-slate-500 mt-1">We will get back to you shortly.</p>
              </div>
            ) : (
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Issue Category</label>
                  <select
                    value={form.category}
                    onChange={e => setForm(f => ({ ...f, category: e.target.value }))}
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    <option value="general">General Question</option>
                    <option value="payment">Payment or billing issue</option>
                    <option value="bug">Bug or technical issue</option>
                    <option value="rfq_nda">RFQ / NDA issue</option>
                    <option value="add_firm">Add or update my firm</option>
                    <option value="collaboration">Partnership / collaboration</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Subject</label>
                  <input
                    type="text"
                    value={form.subject}
                    onChange={e => setForm(f => ({ ...f, subject: e.target.value }))}
                    placeholder="Brief summary of your issue"
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Description</label>
                  <textarea
                    value={form.message}
                    onChange={e => setForm(f => ({ ...f, message: e.target.value }))}
                    placeholder="Describe your issue in detail..."
                    rows={4}
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
                  />
                </div>
                <div className="flex gap-3 pt-1">
                  <button
                    onClick={() => setShowContact(false)}
                    className="flex-1 py-2 border border-gray-300 rounded-lg text-sm font-medium text-slate-700 hover:bg-gray-50"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleContactSubmit}
                    disabled={submitting || !form.subject.trim() || !form.message.trim()}
                    className="flex-1 py-2 bg-[#1e3a5f] text-white rounded-lg text-sm font-medium hover:bg-[#2a4d7a] disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {submitting ? 'Sending...' : 'Send Message'}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
