'use client';

import React, { useState, useEffect, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { useRequireAuth } from '@/hooks/useAuth';
import { api } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { toast } from 'sonner';
import { Globe, Loader2, X, Plus } from 'lucide-react';

// ─── Tag Input Component ─────────────────────────────────────────────────────
function TagInput({
  label,
  required,
  values,
  onChange,
  placeholder,
}: {
  label: string;
  required?: boolean;
  values: string[];
  onChange: (vals: string[]) => void;
  placeholder?: string;
}): React.ReactElement {
  const [input, setInput] = useState('');

  const add = () => {
    const v = input.trim();
    if (v && !values.includes(v)) {
      onChange([...values, v]);
      setInput('');
    }
  };

  return (
    <div className="space-y-1">
      <Label>
        {label}{' '}
        {required ? (
          <span className="text-red-500">*</span>
        ) : (
          <span className="text-slate-500 text-xs">(optional)</span>
        )}
      </Label>
      <div className="flex gap-2">
        <Input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              add();
            }
          }}
          placeholder={placeholder || 'Type and press Enter'}
        />
        <Button type="button" variant="outline" size="sm" onClick={add}>
          <Plus className="h-4 w-4" />
        </Button>
      </div>
      <div className="flex flex-wrap gap-1 mt-1">
        {values.map((v, i) => (
          <span
            key={i}
            className="inline-flex items-center gap-1 px-2 py-0.5 bg-slate-100 rounded text-xs"
          >
            {v}
            <button
              type="button"
              onClick={() => onChange(values.filter((_, j) => j !== i))}
            >
              <X className="h-3 w-3" />
            </button>
          </span>
        ))}
      </div>
    </div>
  );
}

// ─── Main Page Component ─────────────────────────────────────────────────────
export default function FullProfileEditPage(): React.ReactElement {
  const { isLoading: authLoading } = useRequireAuth(['provider']);
  const router = useRouter();

  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [isCrawling, setIsCrawling] = useState(false);
  const [crawlUrl, setCrawlUrl] = useState('');
  const [crawlTaskId, setCrawlTaskId] = useState<string | null>(null);
  const [crawlStatus, setCrawlStatus] = useState<string>('');
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const [form, setForm] = useState({
    proven_experience_notable_projects: [] as string[],
    proven_experience_case_studies: [] as string[],
    business_description: '',
    primary_specialty: '',
    capabilities: [] as string[],
    specialties: [] as string[],
    software_tools: [] as string[],
    secondary_specialties: [] as string[],
    firm_name: '',
    name: '',
    website: '',
    phone: '',
    email_addresses: [] as string[],
    city: '',
    state: '',
    address: '',
    postal_code: '',
    certifications: [] as string[],
    notable_clients: [] as string[],
    equipment: [] as string[],
    team_members: [] as string[],
    team_summary: '',
    projects: '',
  });

  // ─── Load on mount ──────────────────────────────────────────────────────────
  useEffect(() => {
    if (authLoading) return;
    const init = async () => {
      try {
        const statusRes = await api.providers.getFullEditStatus();
        if (!statusRes.data?.paid) {
          toast.error('Full profile editing requires the one-time unlock payment.');
          router.push('/provider/profile');
          return;
        }
        const profileRes = await api.providers.getProfile();
        if (profileRes.data) {
          const p = profileRes.data as any;
          setForm({
            proven_experience_notable_projects: p.proven_experience_notable_projects || [],
            proven_experience_case_studies: p.proven_experience_case_studies || [],
            business_description: p.business_description || '',
            primary_specialty: p.primary_specialty || '',
            capabilities: p.capabilities || [],
            specialties: p.specialties || [],
            software_tools: p.software_tools || [],
            secondary_specialties: p.secondary_specialties || [],
            firm_name: p.firm_name || '',
            name: p.name || '',
            website: p.website || '',
            phone: p.phone || '',
            email_addresses: p.email_addresses || [],
            city: p.city || '',
            state: p.state || '',
            address: p.address || '',
            postal_code: p.postal_code || '',
            certifications: p.certifications || [],
            notable_clients: p.notable_clients || [],
            equipment: p.equipment || [],
            team_members: p.team_members || [],
            team_summary: p.team_summary || '',
            projects: p.projects || '',
          });
          if (p.website) setCrawlUrl(p.website);
        }
      } catch {
        toast.error('Failed to load profile data');
      } finally {
        setIsLoading(false);
      }
    };
    init();
  }, [authLoading, router]);

  // Cleanup poll on unmount
  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  // ─── Helpers ────────────────────────────────────────────────────────────────
  const setField = (key: keyof typeof form) => (val: any) =>
    setForm((prev) => ({ ...prev, [key]: val }));

  const setTextField =
    (key: keyof typeof form) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
      setForm((prev) => ({ ...prev, [key]: e.target.value }));

  // ─── Website crawl ──────────────────────────────────────────────────────────
  const handleStartCrawl = async () => {
    if (!crawlUrl.trim()) {
      toast.error('Please enter a website URL');
      return;
    }
    if (pollRef.current) clearInterval(pollRef.current);
    setIsCrawling(true);
    setCrawlStatus('Starting...');
    try {
      const res = await api.providers.startWebsiteCrawl(crawlUrl.trim());
      const taskId = res.data?.task_id;
      if (!taskId) throw new Error('No task ID returned');
      setCrawlTaskId(taskId);
      setCrawlStatus('Crawling...');
      toast.info('Website crawl started. Auto-filling fields when ready...');
      pollRef.current = setInterval(async () => {
        try {
          const pr = await api.providers.getCrawlStatus(taskId);
          const st = pr.data?.status;
          setCrawlStatus(st || 'Processing...');
          if (st === 'SUCCESS' && pr.data?.data) {
            if (pollRef.current) clearInterval(pollRef.current);
            pollRef.current = null;
            setIsCrawling(false);
            setCrawlStatus('');
            const d = pr.data.data as any;
            setForm((prev) => ({
              ...prev,
              business_description: prev.business_description || d.business_description || '',
              primary_specialty: prev.primary_specialty || d.primary_specialty || '',
              capabilities: prev.capabilities.length ? prev.capabilities : (d.capabilities || []),
              specialties: prev.specialties.length ? prev.specialties : (d.specialties || []),
              software_tools: prev.software_tools.length ? prev.software_tools : (d.software_tools || []),
              notable_clients: prev.notable_clients.length ? prev.notable_clients : (d.notable_clients || []),
              certifications: prev.certifications.length ? prev.certifications : (d.certifications || []),
              team_summary: prev.team_summary || d.team_summary || '',
            }));
            toast.success('Auto-fill complete! Review and save your profile.');
          } else if (st === 'FAILURE') {
            if (pollRef.current) clearInterval(pollRef.current);
            pollRef.current = null;
            setIsCrawling(false);
            setCrawlStatus('');
            toast.error(pr.data?.error || 'Crawl failed. Please fill fields manually.');
          }
        } catch {
          if (pollRef.current) clearInterval(pollRef.current);
          pollRef.current = null;
          setIsCrawling(false);
          setCrawlStatus('');
          toast.error('Crawl polling error');
        }
      }, 3000);
    } catch (e: any) {
      setIsCrawling(false);
      setCrawlStatus('');
      toast.error(e?.response?.data?.detail || 'Failed to start crawl');
    }
  };

  // ─── Save ───────────────────────────────────────────────────────────────────
  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSaving(true);
    try {
      await api.providers.saveFullEdit(form);
      toast.success('Full profile saved successfully!');
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'Failed to save profile');
    } finally {
      setIsSaving(false);
    }
  };

  // ─── Loading guard ──────────────────────────────────────────────────────────
  if (authLoading || isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-slate-500" />
      </div>
    );
  }

  // ─── Render ─────────────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-slate-50">
      <div className="container max-w-3xl py-8 px-4">

        {/* Page header */}
        <div className="mb-6 flex items-center gap-4">
          <Button
            variant="outline"
            size="sm"
            onClick={() => router.push('/provider/profile')}
          >
            ← Back to Profile
          </Button>
          <div>
            <h1 className="text-2xl font-bold">Full Profile Editor</h1>
            <p className="text-sm text-slate-500">
              Complete your profile to maximize RFQ match ranking
            </p>
          </div>
        </div>

        {/* Auto-Fill from Website */}
        <Card className="mb-6 border-blue-200 bg-blue-50">
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <Globe className="h-4 w-4 text-blue-600" />
              Auto-Fill from Website
            </CardTitle>
            <CardDescription>
              Enter your company website and we&apos;ll extract information to pre-fill the fields below.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex gap-2">
              <Input
                value={crawlUrl}
                onChange={(e) => setCrawlUrl(e.target.value)}
                placeholder="https://www.yourfirm.com"
                disabled={isCrawling}
                className="bg-white"
              />
              <Button
                type="button"
                onClick={handleStartCrawl}
                disabled={isCrawling}
                variant="outline"
                className="shrink-0 border-blue-400 text-blue-700 hover:bg-blue-100"
              >
                {isCrawling ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin mr-1" />
                    {crawlStatus || 'Crawling...'}
                  </>
                ) : (
                  'Auto-Fill'
                )}
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* Main form */}
        <form onSubmit={handleSave} className="space-y-6">

          {/* ── Proven Experience ── */}
          <Card className="border-amber-200">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <span className="text-amber-500">★</span> Proven Experience
                <span className="ml-1 text-xs font-normal text-amber-700 bg-amber-100 px-2 py-0.5 rounded">
                  #1 Ranking Factor
                </span>
              </CardTitle>
              <CardDescription>
                Detail your firm&apos;s real-world projects and achievements.
                This is the most impactful section for RFQ matching.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <TagInput
                label="Notable Projects"
                required
                values={form.proven_experience_notable_projects}
                onChange={setField('proven_experience_notable_projects')}
                placeholder="e.g. Fatigue analysis for aerospace bracket — 2023"
              />
              <TagInput
                label="Case Studies / Success Stories"
                values={form.proven_experience_case_studies}
                onChange={setField('proven_experience_case_studies')}
                placeholder="e.g. Reduced weight by 30% using topology optimization"
              />
              <div className="space-y-1">
                <Label>
                  Projects Summary{' '}
                  <span className="text-slate-500 text-xs">(optional — free text)</span>
                </Label>
                <Textarea
                  rows={4}
                  value={form.projects}
                  onChange={setTextField('projects')}
                  placeholder="Describe notable project history and achievements in paragraph form..."
                />
              </div>
            </CardContent>
          </Card>

          {/* ── Business Description & Specialties ── */}
          <Card>
            <CardHeader>
              <CardTitle>Business Description &amp; Specialties</CardTitle>
              <CardDescription>
                How your firm is described in search results and RFQ matching.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-1">
                <Label htmlFor="business_description">
                  Business Description <span className="text-red-500">*</span>
                </Label>
                <Textarea
                  id="business_description"
                  rows={5}
                  value={form.business_description}
                  onChange={setTextField('business_description')}
                  placeholder="Describe your engineering firm's core services, expertise, and value proposition..."
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="primary_specialty">
                  Primary Specialty <span className="text-red-500">*</span>
                </Label>
                <Input
                  id="primary_specialty"
                  value={form.primary_specialty}
                  onChange={setTextField('primary_specialty')}
                  placeholder="e.g. Structural FEA, CFD Analysis, Mechanical Design"
                />
              </div>
              <TagInput
                label="Secondary Specialties"
                values={form.secondary_specialties}
                onChange={setField('secondary_specialties')}
                placeholder="e.g. Thermal Analysis, Fatigue Testing"
              />
              <TagInput
                label="Capabilities"
                required
                values={form.capabilities}
                onChange={setField('capabilities')}
                placeholder="e.g. FEA Simulation, DFM Review, Prototyping"
              />
              <TagInput
                label="Specialties / Keywords"
                values={form.specialties}
                onChange={setField('specialties')}
                placeholder="e.g. ASME, Aerospace, Medical Devices"
              />
              <TagInput
                label="Software Tools"
                values={form.software_tools}
                onChange={setField('software_tools')}
                placeholder="e.g. ANSYS, SolidWorks, CATIA"
              />
            </CardContent>
          </Card>

          {/* ── Firm Information ── */}
          <Card>
            <CardHeader>
              <CardTitle>Firm Information</CardTitle>
              <CardDescription>Basic company details shown on your public profile.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1">
                  <Label htmlFor="firm_name">Firm Name <span className="text-red-500">*</span></Label>
                  <Input
                    id="firm_name"
                    value={form.firm_name}
                    onChange={setTextField('firm_name')}
                    placeholder="Your Engineering Firm LLC"
                  />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="name">
                    Display Name <span className="text-slate-500 text-xs">(optional)</span>
                  </Label>
                  <Input
                    id="name"
                    value={form.name}
                    onChange={setTextField('name')}
                    placeholder="Short display name"
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1">
                  <Label htmlFor="website">Website</Label>
                  <Input
                    id="website"
                    value={form.website}
                    onChange={setTextField('website')}
                    placeholder="https://www.yourfirm.com"
                  />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="phone">Phone</Label>
                  <Input
                    id="phone"
                    value={form.phone}
                    onChange={setTextField('phone')}
                    placeholder="+1 (555) 000-0000"
                  />
                </div>
              </div>
              <TagInput
                label="Email Addresses"
                values={form.email_addresses}
                onChange={setField('email_addresses')}
                placeholder="contact@yourfirm.com"
              />
            </CardContent>
          </Card>

          {/* ── Location ── */}
          <Card>
            <CardHeader>
              <CardTitle>Location</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-1">
                <Label htmlFor="address">Street Address</Label>
                <Input
                  id="address"
                  value={form.address}
                  onChange={setTextField('address')}
                  placeholder="123 Engineering Ave"
                />
              </div>
              <div className="grid grid-cols-3 gap-4">
                <div className="space-y-1">
                  <Label htmlFor="city">City</Label>
                  <Input
                    id="city"
                    value={form.city}
                    onChange={setTextField('city')}
                    placeholder="Detroit"
                  />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="state">State</Label>
                  <Input
                    id="state"
                    value={form.state}
                    onChange={setTextField('state')}
                    placeholder="MI"
                  />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="postal_code">Postal Code</Label>
                  <Input
                    id="postal_code"
                    value={form.postal_code}
                    onChange={setTextField('postal_code')}
                    placeholder="48201"
                  />
                </div>
              </div>
            </CardContent>
          </Card>

          {/* ── Credentials & Clients ── */}
          <Card>
            <CardHeader>
              <CardTitle>Credentials &amp; Notable Clients</CardTitle>
              <CardDescription>
                Certifications and notable client relationships build trust with potential customers.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <TagInput
                label="Certifications"
                values={form.certifications}
                onChange={setField('certifications')}
                placeholder="e.g. ISO 9001, AS9100, NADCAP"
              />
              <TagInput
                label="Notable Clients"
                values={form.notable_clients}
                onChange={setField('notable_clients')}
                placeholder="e.g. Boeing, SpaceX, Ford"
              />
              <TagInput
                label="Equipment"
                values={form.equipment}
                onChange={setField('equipment')}
                placeholder="e.g. MTS Load Frame, Instron, 3D Printer"
              />
            </CardContent>
          </Card>

          {/* ── Team ── */}
          <Card>
            <CardHeader>
              <CardTitle>Team</CardTitle>
              <CardDescription>
                Tell customers about your engineering team.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-1">
                <Label htmlFor="team_summary">
                  Team Summary <span className="text-slate-500 text-xs">(optional)</span>
                </Label>
                <Textarea
                  id="team_summary"
                  rows={3}
                  value={form.team_summary}
                  onChange={setTextField('team_summary')}
                  placeholder="Brief description of your team's size, background, and expertise..."
                />
              </div>
              <TagInput
                label="Key Team Members"
                values={form.team_members}
                onChange={setField('team_members')}
                placeholder="e.g. Jane Smith, P.E. — Structural Lead"
              />
            </CardContent>
          </Card>

          {/* ── Save Button ── */}
          <div className="flex gap-3 pb-8">
            <Button
              type="submit"
              disabled={isSaving}
              className="flex-1 bg-emerald-600 hover:bg-emerald-700 text-white"
            >
              {isSaving ? (
                <><Loader2 className="h-4 w-4 animate-spin mr-2" />Saving...</>
              ) : (
                'Save Full Profile'
              )}
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={() => router.push('/provider/profile')}
            >
              Cancel
            </Button>
          </div>

        </form>
      </div>
    </div>
  );
}
