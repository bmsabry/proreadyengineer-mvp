'use client';

import { useState } from 'react';
import { createPortal } from 'react-dom';
import { LifeBuoy, X, CheckCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';

/**
 * Persistent "Contact Support" control used in BOTH the customer and provider
 * portal navigation bars (placed first, before "Main Page"). The trigger button
 * styling adapts to the nav via `variant` ('light' = customer header, 'dark' =
 * provider navy bar); the modal is identical for both.
 */
export default function ContactSupport({ variant = 'light' }: { variant?: 'light' | 'dark' }) {
  const [showContact, setShowContact] = useState(false);
  const [form, setForm] = useState({ category: 'general', subject: '', message: '' });
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);

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
    <>
      {variant === 'dark' ? (
        <button
          onClick={() => setShowContact(true)}
          title="Contact our support team"
          className="flex items-center gap-1.5 px-3 py-2 rounded-md text-sm font-medium whitespace-nowrap text-blue-100 hover:bg-primary/90 hover:text-white transition-colors duration-150"
        >
          <LifeBuoy size={14} />
          <span>Contact Support</span>
        </button>
      ) : (
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setShowContact(true)}
          title="Contact our support team"
          className="flex items-center gap-1 text-xs px-2"
        >
          <LifeBuoy className="h-3.5 w-3.5" />
          <span className="hidden lg:inline">Contact Support</span>
        </Button>
      )}

      {showContact && typeof document !== 'undefined' && createPortal(
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/40 px-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md p-6">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <LifeBuoy className="h-5 w-5 text-primary" />
                <h2 className="text-lg font-bold text-slate-900">Contact Support</h2>
              </div>
              <button onClick={() => setShowContact(false)} className="text-gray-600 hover:text-gray-600">
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
                    onChange={(e) => setForm((f) => ({ ...f, category: e.target.value }))}
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
                    onChange={(e) => setForm((f) => ({ ...f, subject: e.target.value }))}
                    placeholder="Brief summary of your issue"
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Description</label>
                  <textarea
                    value={form.message}
                    onChange={(e) => setForm((f) => ({ ...f, message: e.target.value }))}
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
                    className="flex-1 py-2 bg-primary text-white rounded-lg text-sm font-medium hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {submitting ? 'Sending...' : 'Send Message'}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>,
        document.body
      )}
    </>
  );
}
