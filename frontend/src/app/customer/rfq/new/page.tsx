'use client';

import { useState, useEffect, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { useRequireAuth } from '@/hooks/useAuth';
import { api } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Checkbox } from '@/components/ui/checkbox';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import HelpTip from '@/components/ui/HelpTip';
import { toast } from 'sonner';
import { ChevronLeft, ArrowRight, Lock, CheckCircle2 } from 'lucide-react';

const RFQ_DRAFT_KEY = 'rfq_draft';

const tollgateOptions = [
  { value: 'TG0', label: 'TG0: Idea Generation' },
  { value: 'TG1', label: 'TG1: Basic Engineering' },
  { value: 'TG2', label: 'TG2: Concept Validation' },
  { value: 'TG3', label: 'TG3: Intermediate Analysis' },
  { value: 'TG4', label: 'TG4: Full Scale Modeling' },
  { value: 'TG5', label: 'TG5: Pre-Production Testing' },
  { value: 'TG6', label: 'TG6: Full System Testing' },
  { value: 'All', label: 'All Phases' },
  { value: 'DontKnow', label: "Don't Know" },
];

function CreateRFQForm() {
  const { user, isLoading: authLoading } = useRequireAuth(['customer', 'admin']);
  const router = useRouter();
  const searchParams = useSearchParams();
  const prefilledQuery = searchParams.get('q') || '';

  const [docS3Key] = useState<string | null>(() => {
    if (typeof window !== 'undefined') {
      return sessionStorage.getItem('docSearchS3Key');
    }
    return null;
  });
  const [docS3Files] = useState<Array<{filename: string; s3_key: string; is_cad: boolean}>>(() => {
    if (typeof window !== 'undefined') {
      try {
        const raw = sessionStorage.getItem('docSearchFiles');
        return raw ? JSON.parse(raw) : [];
      } catch { return []; }
    }
    return [];
  });
  const [docExtractedText] = useState<string | null>(() => {
    if (typeof window !== 'undefined') {
      return sessionStorage.getItem('docSearchExtractedText');
    }
    return null;
  });

  const [formData, setFormData] = useState({
    customer_email: '',
    business_name: '',
    contact_name: '',
    project_description: prefilledQuery,
    urgency: 'Intermediate' as 'High' | 'Intermediate' | 'Low',
    tollgate_phases: [] as string[],
    nda_required: false,
  });

  const [isSubmitting, setIsSubmitting] = useState(false);

  // NDA fee coverage: subscribed customers get free NDA credits/month, so we show
  // "covered by your subscription" instead of the $10 handling fee on the NDA toggle.
  const [ndaCoverage, setNdaCoverage] = useState<{ has_active: boolean; nda_credits_remaining: number } | null>(null);

  // Restore draft from localStorage on mount - ONLY project fields, NOT contact info
  // Contact info (email, name, company) always comes from user profile
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const saved = localStorage.getItem(RFQ_DRAFT_KEY);
    if (saved) {
      try {
        const draft = JSON.parse(saved);
        if (draft.formData) {
          setFormData(prev => ({
            ...prev,
            // Only restore project content - not contact info
            project_description: prefilledQuery || draft.formData.project_description || prev.project_description,
            urgency: draft.formData.urgency || prev.urgency,
            tollgate_phases: draft.formData.tollgate_phases || prev.tollgate_phases,
            nda_required: draft.formData.nda_required ?? prev.nda_required,
          }));
        }
      } catch { /* ignore corrupt draft */ }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Save draft to localStorage on every change
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const draft = { query: prefilledQuery, formData, savedAt: new Date().toISOString() };
    localStorage.setItem(RFQ_DRAFT_KEY, JSON.stringify(draft));
  }, [formData, prefilledQuery]);

  // Load NDA fee coverage from the user's subscription (free NDA credits).
  useEffect(() => {
    if (authLoading || !user) return;
    api.billing.getSubscriptionStatus()
      .then((res: any) => setNdaCoverage({
        has_active: !!res.data?.has_active,
        nda_credits_remaining: res.data?.nda_credits_remaining ?? 0,
      }))
      .catch(() => setNdaCoverage({ has_active: false, nda_credits_remaining: 0 }));
  }, [authLoading, user]);

  useEffect(() => {
    if (user) {
      setFormData(prev => ({
        ...prev,
        // Always pre-fill contact info from user profile
        customer_email: user.email || '',
        contact_name: (user as any).full_name || (user as any).first_name ? 
          (((user as any).first_name || '') + ' ' + ((user as any).last_name || '')).trim() || (user as any).full_name || '' 
          : '',
        business_name: (user as any).business_name || '',
        project_description: prev.project_description || prefilledQuery,
      }));
    }
  }, [user, prefilledQuery]);

  const handleTollgateToggle = (value: string) => {
    setFormData(prev => ({
      ...prev,
      tollgate_phases: prev.tollgate_phases.includes(value)
        ? prev.tollgate_phases.filter(p => p !== value)
        : [...prev.tollgate_phases, value],
    }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    let rfqId: string | null = null;
    try {
      const response = await api.rfqs.create({
        ...formData,
        ...(docS3Files.length > 0 ? { document_s3_keys: docS3Files } : {}),
        ...(docS3Key && docS3Files.length === 0 ? { document_s3_key: docS3Key } : {}),
        ...(docExtractedText ? { document_extracted_text: docExtractedText } : {}),
      });
      rfqId = response.data.id;
      if (docS3Key) sessionStorage.removeItem('docSearchS3Key');
      sessionStorage.removeItem('docSearchFiles');
      sessionStorage.removeItem('docSearchExtractedText');
    } catch (error: any) {
      const msg = error.response?.data?.detail || 'Failed to create RFQ. Please check your details and try again.';
      toast.error(msg);
      setIsSubmitting(false);
      return;
    }
    if (formData.nda_required) {
      // NDA required: do NOT submit yet — payment + signing must happen first
      // api.rfqs.submit() will be called on the NDA sign page after payment confirmed
      toast.success('RFQ created! Please complete payment to proceed with NDA.');
      localStorage.removeItem(RFQ_DRAFT_KEY);
      router.push(`/nda/${rfqId}/sign`);
    } else {
      // No NDA: submit immediately to trigger AI search pipeline
      try {
        await api.rfqs.submit(rfqId!);
        toast.success('RFQ submitted! AI is matching providers and dispatch is in progress...');
      } catch (error: any) {
        const detail = error.response?.data?.detail || '';
        if (detail.includes('already submitted')) {
          toast.success('RFQ already submitted! Redirecting to tracking...');
        } else {
          toast.warning('RFQ saved. Redirecting to tracking page...');
        }
      }
      localStorage.removeItem(RFQ_DRAFT_KEY);
      router.push(`/customer/rfq/${rfqId}/tracking`);
    }
    setIsSubmitting(false);
  };

  if (authLoading) {
    return (
      <div className="min-h-screen bg-slate-50">
        <div className="max-w-2xl mx-auto px-4 py-10">
          <div className="flex items-center gap-3 mb-8">
            <div className="h-8 w-32 bg-slate-200 rounded-lg animate-pulse" />
          </div>
          <div className="mb-8 space-y-2">
            <div className="h-9 w-64 bg-slate-200 rounded-lg animate-pulse" />
            <div className="h-4 w-80 bg-slate-200 rounded animate-pulse" />
          </div>
          <div className="bg-white border border-slate-200 rounded-2xl shadow-sm p-6 mb-6 space-y-4">
            <div className="h-6 w-44 bg-slate-200 rounded animate-pulse" />
            <div className="h-11 w-full bg-slate-100 rounded-lg animate-pulse" />
            <div className="grid grid-cols-2 gap-4">
              <div className="h-11 bg-slate-100 rounded-lg animate-pulse" />
              <div className="h-11 bg-slate-100 rounded-lg animate-pulse" />
            </div>
          </div>
          <div className="bg-white border border-slate-200 rounded-2xl shadow-sm p-6 space-y-4">
            <div className="h-6 w-36 bg-slate-200 rounded animate-pulse" />
            <div className="h-32 w-full bg-slate-100 rounded-lg animate-pulse" />
            <div className="h-11 w-full bg-slate-100 rounded-lg animate-pulse" />
            <div className="grid grid-cols-2 gap-2">
              {[1,2,3,4,5,6].map(i => (
                <div key={i} className="h-10 bg-slate-100 rounded-lg animate-pulse" />
              ))}
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <div className="max-w-2xl mx-auto px-4 py-10">
        <div className="flex items-center gap-3 mb-8">
          <Link href="/">
            <Button
              variant="ghost"
              size="sm"
              className="flex items-center gap-1.5 text-slate-600 hover:text-slate-900 hover:bg-slate-100 -ml-2 rounded-lg"
            >
              <ChevronLeft className="h-4 w-4" />
              Back to Search
            </Button>
          </Link>
        </div>
        <div className="mb-8">
          <h1 className="text-3xl font-bold tracking-tight text-slate-900">Request for Quote</h1>
          <p className="text-slate-500 mt-1.5 text-sm">
            Complete the form below &mdash; we will match and contact qualified providers on your behalf.
          </p>
        </div>
        {prefilledQuery && (
          <div className="mb-6 flex items-start gap-3 bg-blue-50 border border-blue-200 rounded-xl px-4 py-3">
            <CheckCircle2 className="w-4 h-4 text-blue-500 mt-0.5 flex-shrink-0" />
            <p className="text-sm text-blue-800">
              Your search query has been pre-filled below. Review and complete the form.
            </p>
          </div>
        )}
        <form onSubmit={handleSubmit} className="space-y-6">
          <div className="bg-white border border-slate-200 rounded-2xl shadow-sm p-6">
            <h2 className="text-lg font-semibold text-slate-900 mb-5 flex items-center gap-2">
              <span className="w-6 h-6 rounded-lg bg-blue-100 text-blue-600 flex items-center justify-center text-xs font-bold flex-shrink-0">1</span>
              Contact Information
            </h2>
            <div className="space-y-4">
              <div>
                <Label htmlFor="email" className="text-sm font-medium text-slate-700 mb-1.5 block">
                  Email Address *
                </Label>
                <Input
                  id="email"
                  type="email"
                  required
                  value={formData.customer_email}
                  onChange={e => setFormData(prev => ({ ...prev, customer_email: e.target.value }))}
                  className="h-11 border-slate-200 rounded-lg px-4 bg-white focus:border-blue-500 focus:ring-2 focus:ring-blue-500/10 text-sm transition-all duration-150"
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label htmlFor="business_name" className="text-sm font-medium text-slate-700 mb-1.5 block">
                    Business Name *
                  </Label>
                  <Input
                    id="business_name"
                    required
                    value={formData.business_name}
                    onChange={e => setFormData(prev => ({ ...prev, business_name: e.target.value }))}
                    className="h-11 border-slate-200 rounded-lg px-4 bg-white focus:border-blue-500 focus:ring-2 focus:ring-blue-500/10 text-sm transition-all duration-150"
                  />
                </div>
                <div>
                  <Label htmlFor="contact_name" className="text-sm font-medium text-slate-700 mb-1.5 block">
                    Contact Name *
                  </Label>
                  <Input
                    id="contact_name"
                    required
                    value={formData.contact_name}
                    onChange={e => setFormData(prev => ({ ...prev, contact_name: e.target.value }))}
                    className="h-11 border-slate-200 rounded-lg px-4 bg-white focus:border-blue-500 focus:ring-2 focus:ring-blue-500/10 text-sm transition-all duration-150"
                  />
                </div>
              </div>
            </div>
          </div>
          <div className="bg-white border border-slate-200 rounded-2xl shadow-sm p-6">
            <h2 className="text-lg font-semibold text-slate-900 mb-5 flex items-center gap-2">
              <span className="w-6 h-6 rounded-lg bg-purple-100 text-purple-600 flex items-center justify-center text-xs font-bold flex-shrink-0">2</span>
              Project Details
            </h2>
            <div className="space-y-5">
              <div>
                <Label htmlFor="description" className="text-sm font-medium text-slate-700 mb-1.5 flex items-center gap-2">
                  Project Description *
                  <HelpTip id="rfq.description" />
                </Label>
                <Textarea
                  id="description"
                  required
                  rows={5}
                  placeholder="Describe your engineering project, requirements, specifications, and goals in as much detail as possible..."
                  value={formData.project_description}
                  onChange={e => setFormData(prev => ({ ...prev, project_description: e.target.value }))}
                  className="border-slate-200 rounded-lg px-4 py-3 bg-white focus:border-blue-500 focus:ring-2 focus:ring-blue-500/10 text-sm transition-all duration-150 resize-none"
                />
              </div>
              <div>
                <Label className="text-sm font-medium text-slate-700 mb-1.5 block">
                  Urgency Level *
                </Label>
                <Select
                  value={formData.urgency}
                  onValueChange={(val: 'High' | 'Intermediate' | 'Low') =>
                    setFormData(prev => ({ ...prev, urgency: val }))
                  }
                >
                  <SelectTrigger className="h-11 border-slate-200 rounded-lg bg-white focus:border-blue-500 focus:ring-2 focus:ring-blue-500/10 text-sm">
                    <SelectValue placeholder="Select urgency" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="High">High &mdash; Need quotes within 48 hours</SelectItem>
                    <SelectItem value="Intermediate">Intermediate &mdash; Within 1&ndash;2 weeks</SelectItem>
                    <SelectItem value="Low">Low &mdash; No rush, within a month</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-sm font-medium text-slate-700 mb-2 flex items-center gap-2">
                  Tollgate Phases
                  <HelpTip id="rfq.tollgate" />
                </Label>
                <p className="text-xs text-slate-500 mb-3">Select all phases relevant to your project. You don&apos;t need to complete every phase.</p>
                <div className="grid grid-cols-2 gap-2">
                  {tollgateOptions.map(option => (
                    <button
                      key={option.value}
                      type="button"
                      onClick={() => handleTollgateToggle(option.value)}
                      className={`flex items-center gap-2 px-3 py-2.5 rounded-lg border text-sm font-medium transition-all duration-150 text-left ${
                        formData.tollgate_phases.includes(option.value)
                          ? 'bg-blue-50 border-blue-400 text-blue-700'
                          : 'bg-white border-slate-200 text-slate-600 hover:border-slate-300 hover:bg-slate-50'
                      }`}
                    >
                      <div className={`w-4 h-4 rounded border flex items-center justify-center flex-shrink-0 transition-colors ${
                        formData.tollgate_phases.includes(option.value)
                          ? 'bg-blue-500 border-blue-500'
                          : 'border-slate-300'
                      }`}>
                        {formData.tollgate_phases.includes(option.value) && (
                          <svg className="w-2.5 h-2.5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                          </svg>
                        )}
                      </div>
                      {option.label}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </div>
          <div className="bg-white border border-slate-200 rounded-2xl shadow-sm p-6">
            <h2 className="text-lg font-semibold text-slate-900 mb-5 flex items-center gap-2">
              <span className="w-6 h-6 rounded-lg bg-green-100 text-green-600 flex items-center justify-center text-xs font-bold flex-shrink-0">3</span>
              Confidentiality
            </h2>
            <div
              className="flex items-start gap-4 p-4 rounded-xl border border-slate-200 bg-slate-50 cursor-pointer hover:bg-slate-100 transition-colors"
              onClick={() => setFormData(prev => ({ ...prev, nda_required: !prev.nda_required }))}
            >
              <div className={`mt-0.5 w-5 h-5 rounded border-2 flex items-center justify-center flex-shrink-0 transition-colors ${
                formData.nda_required ? 'bg-green-500 border-green-500' : 'border-slate-300 bg-white'
              }`}>
                {formData.nda_required && (
                  <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                  </svg>
                )}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <Lock className="w-4 h-4 text-slate-500 flex-shrink-0" />
                  <span className="text-sm font-semibold text-slate-800">Require NDA</span>
                  <HelpTip id="rfq.nda" />
                  {ndaCoverage && ndaCoverage.has_active && ndaCoverage.nda_credits_remaining > 0 ? (
                    <span className="text-xs font-medium bg-green-100 text-green-700 px-2 py-0.5 rounded-full">Covered by your subscription</span>
                  ) : (
                    <span className="text-xs font-medium bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full">+$10 handling fee</span>
                  )}
                </div>
                <p className="text-xs text-slate-500 leading-relaxed">
                  Providers must sign a mutual NDA before accessing your project details. You will also sign digitally. Requires account login.
                </p>
              </div>
            </div>
          </div>
          <div className="pt-2">
            <Button
              type="submit"
              disabled={isSubmitting}
              className="w-full h-12 bg-primary hover:bg-primary/90 text-white font-semibold rounded-xl shadow-sm transition-all duration-150 flex items-center justify-center gap-2 text-sm disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {isSubmitting ? (
                <>
                  <svg className="animate-spin h-4 w-4 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                  </svg>
                  Submitting RFQ...
                </>
              ) : (
                <>
                  Submit RFQ
                  <ArrowRight className="h-4 w-4" />
                </>
              )}
            </Button>
            <p className="text-center text-xs text-slate-500 mt-3">
              By submitting, you agree to our{' '}
              <Link href="/terms" className="underline hover:text-slate-600">Terms of Service</Link>{' '}
              and{' '}
              <Link href="/privacy" className="underline hover:text-slate-600">Privacy Policy</Link>.
            </p>
          </div>
        </form>
      </div>
    </div>
  );
}

export default function CreateRFQPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
      </div>
    }>
      <CreateRFQForm />
    </Suspense>
  );
}
