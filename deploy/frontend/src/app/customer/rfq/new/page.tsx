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
import { toast } from 'sonner';
import { Home } from 'lucide-react';

const tollgateOptions = [
  { value: 'TG0', label: 'TG0: Idea Generation' },
  { value: 'TG1', label: 'TG1: Basic Engineering' },
  { value: 'TG3', label: 'TG3: Intermediate Analysis' },
  { value: 'TG4', label: 'TG4: Full Scale Modeling' },
  { value: 'TG6', label: 'TG6: Full System Testing' },
  { value: 'All', label: 'All Phases' },
  { value: 'DontKnow', label: "Don't Know" },
];

function CreateRFQForm() {
  const { user, isLoading: authLoading } = useRequireAuth(['customer', 'admin']);
  const router = useRouter();
  const searchParams = useSearchParams();
  const prefilledQuery = searchParams.get('q') || '';

  // Retrieve S3 key of document uploaded during search (if any)
  const [docS3Key] = useState<string | null>(() => {
    if (typeof window !== 'undefined') {
      const key = sessionStorage.getItem('docSearchS3Key');
      if (key) sessionStorage.removeItem('docSearchS3Key'); // consume it once
      return key;
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

  // Pre-fill email and name from user when available
  useEffect(() => {
    if (user) {
      setFormData(prev => ({
        ...prev,
        customer_email: user.email || '',
        contact_name: prev.contact_name,
        // Only set description from URL if not already set
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

    // Step 1: Create the RFQ draft
    try {
      const response = await api.rfqs.create({
        ...formData,
        ...(docS3Key ? { document_s3_key: docS3Key } : {}),
      });
      rfqId = response.data.id;
    } catch (error: any) {
      const msg = error.response?.data?.detail || 'Failed to create RFQ. Please check your details and try again.';
      toast.error(msg);
      setIsSubmitting(false);
      return;
    }

    // Step 2: Submit for AI matching + dispatch
    // Backend returns 202 immediately — AI search runs in the background
    try {
      await api.rfqs.submit(rfqId!);
      toast.success('RFQ submitted! AI is matching providers and dispatch is in progress...');
    } catch (error: any) {
      const detail = error.response?.data?.detail || '';
      if (detail.includes('already submitted')) {
        toast.success('RFQ already submitted! Redirecting to tracking...');
      } else {
        // RFQ was created — dispatch may still happen, redirect to tracking
        toast.warning('RFQ saved. Redirecting to tracking page...');
      }
    }

    // Always redirect — RFQ is created regardless of submit status
    if (formData.nda_required) {
      router.push(`/nda/${rfqId}/sign`);
    } else {
      router.push(`/customer/rfq/${rfqId}/tracking`);
    }
    setIsSubmitting(false);
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
    <div className="container py-8 max-w-2xl">
      <div className="flex items-center gap-4 mb-6">
        <Link href="/">
          <Button variant="ghost" size="sm" className="flex items-center gap-1">
            <Home className="h-4 w-4" />
            Back to Search
          </Button>
        </Link>
        <div>
          <h1 className="text-3xl font-bold">Request for Quote</h1>
          <p className="text-muted-foreground">Describe your project and we'll contact matched providers</p>
        </div>
      </div>

      {prefilledQuery && (
        <div className="mb-4 rounded-md bg-blue-50 border border-blue-200 p-3 text-sm text-blue-800">
          ✅ Your search query has been pre-filled below. Review and complete the form.
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle>Contact Information</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <Label htmlFor="email">Email *</Label>
              <Input
                id="email"
                type="email"
                required
                value={formData.customer_email}
                onChange={e => setFormData(prev => ({ ...prev, customer_email: e.target.value }))}
              />
            </div>
            <div>
              <Label htmlFor="business_name">Business Name *</Label>
              <Input
                id="business_name"
                required
                value={formData.business_name}
                onChange={e => setFormData(prev => ({ ...prev, business_name: e.target.value }))}
              />
            </div>
            <div>
              <Label htmlFor="contact_name">Contact Name *</Label>
              <Input
                id="contact_name"
                required
                value={formData.contact_name}
                onChange={e => setFormData(prev => ({ ...prev, contact_name: e.target.value }))}
              />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Project Details</CardTitle>
            <CardDescription>Describe what you need in as much detail as possible</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <Label htmlFor="description">Project Description *</Label>
              <Textarea
                id="description"
                required
                rows={5}
                placeholder="Describe your engineering project, requirements, and goals..."
                value={formData.project_description}
                onChange={e => setFormData(prev => ({ ...prev, project_description: e.target.value }))}
              />
            </div>
            <div>
              <Label htmlFor="urgency">Urgency</Label>
              <Select
                value={formData.urgency}
                onValueChange={v => setFormData(prev => ({ ...prev, urgency: v as 'High' | 'Intermediate' | 'Low' }))}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="High">High — Need quotes ASAP</SelectItem>
                  <SelectItem value="Intermediate">Intermediate — Within a few weeks</SelectItem>
                  <SelectItem value="Low">Low — Exploratory / Planning</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="mb-2 block">Project Phases (select all that apply)</Label>
              <div className="grid grid-cols-2 gap-2">
                {tollgateOptions.map(opt => (
                  <div key={opt.value} className="flex items-center gap-2">
                    <Checkbox
                      id={opt.value}
                      checked={formData.tollgate_phases.includes(opt.value)}
                      onCheckedChange={() => handleTollgateToggle(opt.value)}
                    />
                    <Label htmlFor={opt.value} className="font-normal cursor-pointer">{opt.label}</Label>
                  </div>
                ))}
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Checkbox
                id="nda"
                checked={formData.nda_required}
                onCheckedChange={v => setFormData(prev => ({ ...prev, nda_required: Boolean(v) }))}
              />
              <Label htmlFor="nda" className="font-normal cursor-pointer">
                Require NDA before sharing project details ($5 document handling fee)
              </Label>
            </div>
          </CardContent>
        </Card>

        <div className="flex gap-3">
          <Button type="submit" disabled={isSubmitting} className="flex-1">
            {isSubmitting ? 'Submitting...' : 'Submit RFQ — Start Automated Quote Collection'}
          </Button>
          <Link href="/customer/dashboard">
            <Button type="button" variant="outline">Cancel</Button>
          </Link>
        </div>
      </form>
    </div>
  );
}

export default function CreateRFQPage() {
  return (
    <Suspense fallback={<div className="container py-8"><p>Loading...</p></div>}>
      <CreateRFQForm />
    </Suspense>
  );
}
