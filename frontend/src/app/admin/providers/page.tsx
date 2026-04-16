'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRequireAuth } from '@/hooks/useAuth';
import { api } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Search, Plus, Trash2, RefreshCw, ChevronLeft, ChevronRight, ChevronUp, AlertTriangle, Pencil } from 'lucide-react';
import { toast } from 'sonner';

interface AdminProvider {
  id: string;
  name: string;
  firm_name: string | null;
  city: string | null;
  state: string | null;
  business_evaluation_tier: string | null;
  primary_specialty: string | null;
  is_engineering_service: number | null;
  website: string | null;
  created_at: string | null;
}

interface NewProviderForm {
  firm_name: string;
  name: string;
  website: string;
  phone: string;
  address: string;
  city: string;
  state: string;
  postal_code: string;
  primary_specialty: string;
  business_description: string;
  capabilities: string;
  specialties: string;
  software_tools: string;
  secondary_specialties: string;
  certifications: string;
  notable_clients: string;
  equipment: string;
  email_addresses: string;
  proven_experience_notable_projects: string;
  proven_experience_case_studies: string;
  team_members: string;
  team_summary: string;
  projects: string;
}

const EMPTY_FORM: NewProviderForm = {
  firm_name: '', name: '', website: '', phone: '', address: '',
  city: '', state: '', postal_code: '', primary_specialty: '',
  business_description: '', capabilities: '', specialties: '',
  software_tools: '', secondary_specialties: '', certifications: '',
  notable_clients: '', equipment: '', email_addresses: '',
  proven_experience_notable_projects: '', proven_experience_case_studies: '',
  team_members: '', team_summary: '', projects: '',
};

function parseLines(val: string): string[] {
  return val.split('\n').map(s => s.trim()).filter(Boolean);
}

function joinCsv(arr: string[] | null | undefined): string {
  if (!arr || !Array.isArray(arr)) return '';
  return arr.join(', ');
}

function splitCsv(val: string): string[] {
  return val.split(',').map(s => s.trim()).filter(Boolean);
}


function formatDate(iso: string | null) {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

export default function AdminProvidersPage() {
  const { isLoading: authLoading } = useRequireAuth(['admin']);
  const [providers, setProviders] = useState<AdminProvider[]>([]);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [searchInput, setSearchInput] = useState('');
  const [showAddForm, setShowAddForm] = useState(false);
  const [form, setForm] = useState<NewProviderForm>(EMPTY_FORM);
  const [addStep, setAddStep] = useState<'url' | 'form'>('url');
  const [crawlUrl, setCrawlUrl] = useState('');
  const [isCrawling, setIsCrawling] = useState(false);
  const [crawlError, setCrawlError] = useState('');
  const [isAdding, setIsAdding] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState<AdminProvider | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [editProvider, setEditProvider] = useState(null as AdminProvider | null);
  const [editForm, setEditForm] = useState({ ...EMPTY_FORM });
  const [isEditLoading, setIsEditLoading] = useState(false);
  const [isEditSaving, setIsEditSaving] = useState(false);
  const [page, setPage] = useState(1);
  const PAGE_SIZE = 50;

  const loadProviders = useCallback(async () => {
    setIsLoading(true);
    try {
      const res = await api.admin.getProviders({ search, page, limit: PAGE_SIZE });
      if (res.data) {
        setProviders(res.data.providers || []);
        setTotal(res.data.total || 0);
      }
    } catch {
      toast.error('Failed to load providers');
    } finally {
      setIsLoading(false);
    }
  }, [search, page]);

  useEffect(() => {
    if (!authLoading) loadProviders();
  }, [authLoading, loadProviders]);

  const handleSearch = () => {
    setPage(1);
    setSearch(searchInput);
  };

  const handleAddProvider = async () => {
    if (!form.firm_name.trim() && !form.name.trim()) {
      toast.error('Firm Name or Display Name is required');
      return;
    }
    setIsAdding(true);
    try {
      const payload: Record<string, any> = {};
      const strFields = ['firm_name','name','website','phone','address','city','state',
        'postal_code','primary_specialty','business_description','team_summary','projects'];
      strFields.forEach(f => {
        const v = (form as any)[f]?.trim();
        if (v) payload[f] = v;
      });
      const arrFields = ['capabilities','specialties','software_tools','secondary_specialties',
        'certifications','notable_clients','equipment','email_addresses',
        'proven_experience_notable_projects','proven_experience_case_studies'];
      arrFields.forEach(f => {
        const lines = parseLines((form as any)[f] || '');
        if (lines.length > 0) payload[f] = lines;
      });
      await api.admin.createProvider(payload);
      toast.success('✅ Provider created — embedding queued automatically');
      setForm(EMPTY_FORM);
      setShowAddForm(false);
      loadProviders();
    } catch (e: any) {
      toast.error(e?.message || 'Failed to create provider');
    } finally {
      setIsAdding(false);
    }
  };

  const handleDelete = async () => {
    if (!deleteConfirm) return;
    setIsDeleting(true);
    try {
      await api.admin.deleteProvider(deleteConfirm.id);
      toast.success(`Provider "${deleteConfirm.name || deleteConfirm.firm_name}" deleted`);
      setDeleteConfirm(null);
      loadProviders();
    } catch (e: any) {
      toast.error(e?.message || 'Failed to delete provider');
    } finally {
      setIsDeleting(false);
    }
  };

  const handleEditOpen = async (p: AdminProvider) => {
    setEditProvider(p);
    setEditForm({ ...EMPTY_FORM });
    setIsEditLoading(true);
    try {
      const res = await api.admin.getProvider(p.id);
      const d = res.data;
      setEditForm({
        firm_name: d.firm_name || '',
        name: d.name || '',
        website: d.website || '',
        phone: d.phone || '',
        address: d.address || '',
        city: d.city || '',
        state: d.state || '',
        postal_code: d.postal_code || '',
        primary_specialty: d.primary_specialty || '',
        business_description: d.business_description || '',
        capabilities: joinCsv(d.capabilities),
        specialties: joinCsv(d.specialties),
        software_tools: joinCsv(d.software_tools),
        secondary_specialties: joinCsv(d.secondary_specialties),
        certifications: joinCsv(d.certifications),
        notable_clients: d.notable_clients || '',
        equipment: joinCsv(d.equipment),
        email_addresses: joinCsv(d.email_addresses),
        proven_experience_notable_projects: joinCsv(d.proven_experience_notable_projects),
        proven_experience_case_studies: joinCsv(d.proven_experience_case_studies),
        team_members: joinCsv(d.team_members),
        team_summary: d.team_summary || '',
        projects: d.projects || '',
      });
    } catch (e: any) {
      toast.error(e?.message || 'Failed to load provider details');
      setEditProvider(null);
    } finally {
      setIsEditLoading(false);
    }
  };

  const handleEditSave = async () => {
    if (!editProvider) return;
    setIsEditSaving(true);
    try {
      const payload: { [k: string]: any } = {};
      const strFields = ['firm_name','name','website','phone','address','city','state',
        'postal_code','primary_specialty','business_description','notable_clients','team_summary'];
      strFields.forEach(f => {
        payload[f] = (editForm as any)[f]?.trim() || null;
      });
      const arrFields = ['capabilities','specialties','software_tools','secondary_specialties',
        'certifications','equipment','email_addresses',
        'proven_experience_notable_projects','proven_experience_case_studies'];
      arrFields.forEach(f => {
        payload[f] = splitCsv((editForm as any)[f] || '');
      });
      await api.admin.updateProvider(editProvider.id, payload);
      toast.success('✅ Provider updated — embedding regeneration queued if needed');
      setEditProvider(null);
      loadProviders();
    } catch (e: any) {
      toast.error(e?.message || 'Failed to update provider');
    } finally {
      setIsEditSaving(false);
    }
  };


  const totalPages = Math.ceil(total / PAGE_SIZE);
  const sf = (field: keyof NewProviderForm, val: string) => setForm(f => ({ ...f, [field]: val }));

  const handleCrawl = async () => {
    if (!crawlUrl.trim()) { setCrawlError('Please enter a website URL'); return; }
    setIsCrawling(true);
    setCrawlError('');
    try {
      // Endpoint now runs synchronously and returns data directly - no polling needed
      const res = await api.admin.crawlWebsiteForProvider(crawlUrl.trim());
      const { status, data, detail } = res.data as any;
      if (status === 'done' && data) {
        setForm(prev => ({
          ...prev,
          firm_name: data.firm_name || data.name || prev.firm_name,
          name: data.name || data.firm_name || prev.name,
          website: crawlUrl.trim(),
          phone: data.phone || prev.phone,
          address: data.address || prev.address,
          city: data.city || prev.city,
          state: data.state || prev.state,
          postal_code: data.postal_code || prev.postal_code,
          primary_specialty: data.primary_specialty || prev.primary_specialty,
          business_description: data.business_description || prev.business_description,
          capabilities: Array.isArray(data.capabilities) ? data.capabilities.join('\n') : (data.capabilities || prev.capabilities),
          specialties: Array.isArray(data.specialties) ? data.specialties.join('\n') : (data.specialties || prev.specialties),
          software_tools: Array.isArray(data.software_tools) ? data.software_tools.join('\n') : (data.software_tools || prev.software_tools),
          secondary_specialties: Array.isArray(data.secondary_specialties) ? data.secondary_specialties.join('\n') : (data.secondary_specialties || prev.secondary_specialties),
          certifications: Array.isArray(data.certifications) ? data.certifications.join('\n') : (data.certifications || prev.certifications),
          notable_clients: Array.isArray(data.notable_clients) ? data.notable_clients.join('\n') : (data.notable_clients || prev.notable_clients),
          email_addresses: Array.isArray(data.email_addresses) ? data.email_addresses.join('\n') : (data.email_addresses || prev.email_addresses),
          proven_experience_notable_projects: Array.isArray(data.proven_experience_notable_projects) ? data.proven_experience_notable_projects.join('\n') : (data.proven_experience_notable_projects || prev.proven_experience_notable_projects),
          proven_experience_case_studies: Array.isArray(data.proven_experience_case_studies) ? data.proven_experience_case_studies.join('\n') : (data.proven_experience_case_studies || prev.proven_experience_case_studies),
          equipment: Array.isArray(data.equipment) ? data.equipment.join('\n') : (data.equipment || prev.equipment),
          team_members: Array.isArray(data.team_members) ? data.team_members.join('\n') : (data.team_members || prev.team_members),
          team_summary: data.team_summary || prev.team_summary,
          projects: data.projects || prev.projects,
        }));
        setAddStep('form');
        toast.success('Website crawled! Review and edit the pre-filled details.');
      } else {
        setCrawlError(detail || 'No data could be extracted. Please fill manually.');
      }
    } catch (err: any) {
      setCrawlError(err?.response?.data?.detail || 'Crawl failed. Please try again or fill manually.');
    } finally {
      setIsCrawling(false);
    }
  };


  return (
    <div className="p-8 max-w-7xl mx-auto">

      {/* Delete Confirmation Modal */}
      {deleteConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-white rounded-xl shadow-2xl p-6 max-w-md w-full mx-4">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-full bg-red-100 flex items-center justify-center">
                <AlertTriangle className="h-5 w-5 text-red-600" />
              </div>
              <div>
                <h3 className="font-bold text-slate-900">Delete Provider</h3>
                <p className="text-sm text-slate-500">This action cannot be undone</p>
              </div>
            </div>
            <p className="text-sm text-slate-700 mb-2">
              You are about to permanently delete:
            </p>
            <div className="bg-red-50 border border-red-200 rounded-lg p-3 mb-4">
              <p className="font-semibold text-red-900">{deleteConfirm.firm_name || deleteConfirm.name}</p>
              <p className="text-xs text-red-700">{deleteConfirm.city}{deleteConfirm.state ? `, ${deleteConfirm.state}` : ''} · ID: {deleteConfirm.id}</p>
            </div>
            <p className="text-xs text-slate-500 mb-4">
              This will also remove all associated memberships and claim requests. RFQ and quote data is preserved.
            </p>
            <div className="flex gap-3 justify-end">
              <Button variant="outline" onClick={() => setDeleteConfirm(null)} disabled={isDeleting}>
                Cancel
              </Button>
              <Button
                onClick={handleDelete}
                disabled={isDeleting}
                className="bg-red-600 hover:bg-red-700 text-white"
              >
                {isDeleting ? 'Deleting...' : 'Delete Permanently'}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Edit Provider Modal */}
      {editProvider && (
        <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/60 overflow-y-auto py-8">
          <div className="bg-white rounded-xl shadow-2xl w-full max-w-3xl mx-4 mb-8">
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200">
              <div>
                <h3 className="font-bold text-slate-900 text-lg">Edit Provider</h3>
                <p className="text-sm text-slate-500">{editProvider.firm_name || editProvider.name} · ID: {editProvider.id}</p>
              </div>
              <Button variant="ghost" size="sm" onClick={() => setEditProvider(null)} disabled={isEditSaving}>
                ✕
              </Button>
            </div>

            {isEditLoading ? (
              <div className="flex items-center justify-center py-20">
                <RefreshCw className="h-8 w-8 animate-spin text-blue-500" />
                <span className="ml-3 text-slate-600">Loading provider details...</span>
              </div>
            ) : (
              <div className="p-6 space-y-6">

                {/* Basic Info */}
                <div>
                  <h4 className="text-sm font-semibold text-slate-700 uppercase tracking-wide mb-3">Basic Info</h4>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <Label htmlFor="ef-firm_name">Company Name (firm_name)</Label>
                      <Input id="ef-firm_name" value={editForm.firm_name} onChange={e => setEditForm(f => ({ ...f, firm_name: e.target.value }))} placeholder="Acme Engineering LLC" />
                    </div>
                    <div>
                      <Label htmlFor="ef-name">Display Name</Label>
                      <Input id="ef-name" value={editForm.name} onChange={e => setEditForm(f => ({ ...f, name: e.target.value }))} placeholder="Acme Engineering" />
                    </div>
                    <div>
                      <Label htmlFor="ef-website">Website</Label>
                      <Input id="ef-website" value={editForm.website} onChange={e => setEditForm(f => ({ ...f, website: e.target.value }))} placeholder="https://acme.com" />
                    </div>
                    <div>
                      <Label htmlFor="ef-phone">Phone</Label>
                      <Input id="ef-phone" value={editForm.phone} onChange={e => setEditForm(f => ({ ...f, phone: e.target.value }))} placeholder="+1 555 000 0000" />
                    </div>
                  </div>
                </div>

                {/* Location */}
                <div>
                  <h4 className="text-sm font-semibold text-slate-700 uppercase tracking-wide mb-3">Location</h4>
                  <div className="grid grid-cols-2 gap-4">
                    <div className="col-span-2">
                      <Label htmlFor="ef-address">Address</Label>
                      <Input id="ef-address" value={editForm.address} onChange={e => setEditForm(f => ({ ...f, address: e.target.value }))} placeholder="123 Main St" />
                    </div>
                    <div>
                      <Label htmlFor="ef-city">City</Label>
                      <Input id="ef-city" value={editForm.city} onChange={e => setEditForm(f => ({ ...f, city: e.target.value }))} placeholder="Detroit" />
                    </div>
                    <div>
                      <Label htmlFor="ef-state">State</Label>
                      <Input id="ef-state" value={editForm.state} onChange={e => setEditForm(f => ({ ...f, state: e.target.value }))} placeholder="MI" />
                    </div>
                    <div>
                      <Label htmlFor="ef-postal">Postal Code</Label>
                      <Input id="ef-postal" value={editForm.postal_code} onChange={e => setEditForm(f => ({ ...f, postal_code: e.target.value }))} placeholder="48201" />
                    </div>
                  </div>
                </div>

                {/* Business Description */}
                <div>
                  <h4 className="text-sm font-semibold text-slate-700 uppercase tracking-wide mb-3">Business Description</h4>
                  <div className="space-y-4">
                    <div>
                      <Label htmlFor="ef-primary_specialty">Primary Specialty</Label>
                      <Input id="ef-primary_specialty" value={editForm.primary_specialty} onChange={e => setEditForm(f => ({ ...f, primary_specialty: e.target.value }))} placeholder="Structural Analysis" />
                    </div>
                    <div>
                      <Label htmlFor="ef-business_description">Business Description</Label>
                      <Textarea id="ef-business_description" rows={4} value={editForm.business_description} onChange={e => setEditForm(f => ({ ...f, business_description: e.target.value }))} placeholder="Describe the firm's core services and expertise..." />
                      <p className="text-xs text-slate-500 mt-1">Heavily weighs on the matching process, as evaluated by AI.</p>
                    </div>
                    <div>
                      <Label htmlFor="ef-notable_projects">Notable Projects</Label>
                      <Textarea id="ef-notable_projects" rows={3} value={editForm.proven_experience_notable_projects} onChange={e => setEditForm(f => ({ ...f, proven_experience_notable_projects: e.target.value }))} placeholder="Comma-separated project summaries" />
                      <p className="text-xs text-slate-500 mt-1">Comma-separated list — greatest impact on RFQ match determination.</p>
                    </div>
                  </div>
                </div>

                {/* Capabilities */}
                <div>
                  <h4 className="text-sm font-semibold text-slate-700 uppercase tracking-wide mb-3">Capabilities</h4>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <Label htmlFor="ef-capabilities">Capabilities</Label>
                      <Textarea id="ef-capabilities" rows={3} value={editForm.capabilities} onChange={e => setEditForm(f => ({ ...f, capabilities: e.target.value }))} placeholder="FEA, CFD, fatigue analysis" />
                      <p className="text-xs text-slate-500 mt-1">Comma-separated</p>
                    </div>
                    <div>
                      <Label htmlFor="ef-specialties">Specialties</Label>
                      <Textarea id="ef-specialties" rows={3} value={editForm.specialties} onChange={e => setEditForm(f => ({ ...f, specialties: e.target.value }))} placeholder="Aerospace, Automotive" />
                      <p className="text-xs text-slate-500 mt-1">Comma-separated</p>
                    </div>
                    <div>
                      <Label htmlFor="ef-secondary_specialties">Secondary Specialties</Label>
                      <Textarea id="ef-secondary_specialties" rows={2} value={editForm.secondary_specialties} onChange={e => setEditForm(f => ({ ...f, secondary_specialties: e.target.value }))} placeholder="Thermal, Vibration" />
                      <p className="text-xs text-slate-500 mt-1">Comma-separated</p>
                    </div>
                    <div>
                      <Label htmlFor="ef-software_tools">Software Tools</Label>
                      <Textarea id="ef-software_tools" rows={2} value={editForm.software_tools} onChange={e => setEditForm(f => ({ ...f, software_tools: e.target.value }))} placeholder="ANSYS, SolidWorks, MATLAB" />
                      <p className="text-xs text-slate-500 mt-1">Comma-separated</p>
                    </div>
                  </div>
                </div>

                {/* Additional */}
                <div>
                  <h4 className="text-sm font-semibold text-slate-700 uppercase tracking-wide mb-3">Additional</h4>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <Label htmlFor="ef-notable_clients">Notable Clients</Label>
                      <Input id="ef-notable_clients" value={editForm.notable_clients} onChange={e => setEditForm(f => ({ ...f, notable_clients: e.target.value }))} placeholder="NASA, Boeing, Ford" />
                    </div>
                    <div>
                      <Label htmlFor="ef-email_addresses">Email Addresses</Label>
                      <Input id="ef-email_addresses" value={editForm.email_addresses} onChange={e => setEditForm(f => ({ ...f, email_addresses: e.target.value }))} placeholder="contact@acme.com" />
                      <p className="text-xs text-slate-500 mt-1">Enter one email only for the firm.</p>
                    </div>
                    <div className="col-span-2">
                      <Label htmlFor="ef-certifications">Certifications</Label>
                      <Input id="ef-certifications" value={editForm.certifications} onChange={e => setEditForm(f => ({ ...f, certifications: e.target.value }))} placeholder="ISO 9001, AS9100" />
                      <p className="text-xs text-slate-500 mt-1">Comma-separated</p>
                    </div>
                  </div>
                </div>

                {/* Actions */}
                <div className="flex gap-3 justify-end pt-2 border-t border-slate-200">
                  <Button variant="outline" onClick={() => setEditProvider(null)} disabled={isEditSaving}>
                    Cancel
                  </Button>
                  <Button
                    onClick={handleEditSave}
                    disabled={isEditSaving}
                    className="bg-blue-600 hover:bg-blue-700 text-white"
                  >
                    {isEditSaving ? 'Saving...' : 'Save Changes'}
                  </Button>
                </div>

              </div>
            )}
          </div>
        </div>
      )}


      {/* Page Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Provider Firms</h1>
          <p className="text-sm text-slate-500 mt-1">{total.toLocaleString()} total firms in database</p>
        </div>
        <div className="flex gap-3">
          <Button variant="outline" size="sm" onClick={loadProviders} disabled={isLoading}>
            <RefreshCw className={`h-4 w-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
          <Button
            size="sm"
            onClick={() => setShowAddForm(v => !v)}
            className="bg-blue-600 hover:bg-blue-700 text-white"
          >
            {showAddForm ? <ChevronUp className="h-4 w-4 mr-2" /> : <Plus className="h-4 w-4 mr-2" />}
            {showAddForm ? 'Cancel' : 'Add New Firm'}
          </Button>
        </div>
      </div>

      {/* Add Firm Form */}
      {showAddForm && (
        <Card className="mb-6 border-2 border-blue-200 bg-blue-50">
          <CardHeader>
            <CardTitle className="text-blue-900">
              {addStep === 'url' ? '➕ Add New Firm' : '📋 New Firm Details'}
            </CardTitle>
            <CardDescription>Array fields: enter one item per line. Embedding is automatically queued on save.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">

            {/* STEP 1: Website URL input */}
            {addStep === 'url' && (
              <div className="space-y-4">
                <div className="rounded-lg bg-white border border-blue-200 p-4">
                  <p className="text-sm text-blue-900 font-medium mb-1">🌐 Automatic Data Extraction</p>
                  <p className="text-sm text-slate-600">
                    Enter the firm&apos;s website URL below. We will automatically extract all available information
                    including project experience, capabilities, and contact details.
                    You will review and edit before saving.
                  </p>
                </div>
                <div className="space-y-2">
                  <Label className="font-semibold">Firm Website URL</Label>
                  <Input
                    placeholder="https://www.firmname.com"
                    value={crawlUrl}
                    onChange={e => setCrawlUrl(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && handleCrawl()}
                  />
                  {crawlError && <p className="text-sm text-red-600">{crawlError}</p>}
                </div>
                <div className="flex gap-3">
                  <Button
                    onClick={handleCrawl}
                    disabled={isCrawling}
                    className="bg-blue-600 hover:bg-blue-700 text-white"
                  >
                    {isCrawling ? (
                      <><span className="mr-2">⏳</span>Extracting from website...</>
                    ) : (
                      <>🌐 Extract from Website</>
                    )}
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() => setAddStep('form')}
                    disabled={isCrawling}
                  >
                    Fill Manually Instead
                  </Button>
                </div>
              </div>
            )}

            {/* STEP 2: Full form fields */}
            {addStep === 'form' && (
              <div className="space-y-6">

            {/* CRITICAL */}
            <div className="space-y-3">
              <p className="text-xs font-bold text-red-600 uppercase tracking-wider border-b border-red-200 pb-1">🔴 Critical — Primary Search Ranking Inputs</p>
              <div>
                <Label className="font-semibold">Proven Experience / Notable Projects</Label>
                <p className="text-xs text-slate-500 mb-1">One project per line. Each line: what was done + how + why/outcome.</p>
                <Textarea rows={5} value={form.proven_experience_notable_projects}
                  placeholder="Performed fatigue analysis on aircraft landing gear using FEA to predict failure under cyclic loading.\nDesigned thermal management system for EV battery pack using CFD simulation."
                  onChange={e => sf('proven_experience_notable_projects', e.target.value)} />
              </div>
              <div>
                <Label className="font-semibold">Case Studies</Label>
                <Textarea rows={3} placeholder="One case study per line" value={form.proven_experience_case_studies}
                  onChange={e => sf('proven_experience_case_studies', e.target.value)} />
              </div>
              <div>
                <Label className="font-semibold">Business Description <span className="text-red-500">*</span></Label>
                <Textarea rows={3} placeholder="2–4 sentences describing what this firm does" value={form.business_description}
                  onChange={e => sf('business_description', e.target.value)} />
              </div>
            </div>

            {/* SCORING */}
            <div className="space-y-3">
              <p className="text-xs font-bold text-orange-600 uppercase tracking-wider border-b border-orange-200 pb-1">🟠 Required — Scoring & Matching</p>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label>Primary Specialty <span className="text-red-500">*</span></Label>
                  <Input placeholder="e.g. Structural Engineering" value={form.primary_specialty}
                    onChange={e => sf('primary_specialty', e.target.value)} />
                </div>
                <div>
                  <Label>Secondary Specialties</Label>
                  <Textarea rows={2} placeholder="One per line" value={form.secondary_specialties}
                    onChange={e => sf('secondary_specialties', e.target.value)} />
                </div>
              </div>
              <div className="grid grid-cols-3 gap-4">
                <div>
                  <Label>Capabilities</Label>
                  <Textarea rows={3} placeholder="One per line" value={form.capabilities}
                    onChange={e => sf('capabilities', e.target.value)} />
                </div>
                <div>
                  <Label>Specialties</Label>
                  <Textarea rows={3} placeholder="One per line" value={form.specialties}
                    onChange={e => sf('specialties', e.target.value)} />
                </div>
                <div>
                  <Label>Software Tools</Label>
                  <Textarea rows={3} placeholder="One per line" value={form.software_tools}
                    onChange={e => sf('software_tools', e.target.value)} />
                </div>
              </div>
            </div>

            {/* FIRM IDENTITY */}
            <div className="space-y-3">
              <p className="text-xs font-bold text-slate-600 uppercase tracking-wider border-b border-slate-200 pb-1">🟡 Required — Firm Identity & Contact</p>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label>Firm Name (Legal) <span className="text-red-500">*</span></Label>
                  <Input placeholder="Legal firm name" value={form.firm_name}
                    onChange={e => sf('firm_name', e.target.value)} />
                </div>
                <div>
                  <Label>Display Name <span className="text-red-500">*</span></Label>
                  <Input placeholder="Display name" value={form.name}
                    onChange={e => sf('name', e.target.value)} />
                </div>
                <div>
                  <Label>Website</Label>
                  <Input placeholder="https://..." value={form.website}
                    onChange={e => sf('website', e.target.value)} />
                </div>
                <div>
                  <Label>Phone</Label>
                  <Input placeholder="Phone number" value={form.phone}
                    onChange={e => sf('phone', e.target.value)} />
                </div>
              </div>
              <div>
                <Label>Email Addresses</Label>
                <Textarea rows={2} placeholder="One email per line" value={form.email_addresses}
                  onChange={e => sf('email_addresses', e.target.value)} />
              </div>
              <div className="grid grid-cols-4 gap-4">
                <div className="col-span-2">
                  <Label>Address</Label>
                  <Input placeholder="Street address" value={form.address}
                    onChange={e => sf('address', e.target.value)} />
                </div>
                <div>
                  <Label>City</Label>
                  <Input value={form.city} onChange={e => sf('city', e.target.value)} />
                </div>
                <div>
                  <Label>State</Label>
                  <Input value={form.state} onChange={e => sf('state', e.target.value)} />
                </div>
              </div>
              <div className="w-32">
                <Label>Postal Code</Label>
                <Input value={form.postal_code} onChange={e => sf('postal_code', e.target.value)} />
              </div>
            </div>

            {/* OPTIONAL */}
            <div className="space-y-3">
              <p className="text-xs font-bold text-slate-400 uppercase tracking-wider border-b border-slate-200 pb-1">🟢 Optional — Credentials & Team</p>
              <div className="grid grid-cols-3 gap-4">
                <div>
                  <Label>Certifications</Label>
                  <Textarea rows={3} placeholder="One per line" value={form.certifications}
                    onChange={e => sf('certifications', e.target.value)} />
                </div>
                <div>
                  <Label>Notable Clients</Label>
                  <Textarea rows={3} placeholder="One per line" value={form.notable_clients}
                    onChange={e => sf('notable_clients', e.target.value)} />
                </div>
                <div>
                  <Label>Equipment</Label>
                  <Textarea rows={3} placeholder="One per line" value={form.equipment}
                    onChange={e => sf('equipment', e.target.value)} />
                </div>
              </div>
              <div>
                <Label>Team Summary</Label>
                <Textarea rows={2} placeholder="Brief description of the team" value={form.team_summary}
                  onChange={e => sf('team_summary', e.target.value)} />
              </div>
              <div>
                <Label>Projects (General Portfolio)</Label>
                <Textarea rows={2} placeholder="General project portfolio description" value={form.projects}
                  onChange={e => sf('projects', e.target.value)} />
              </div>
            </div>

            {/* Save button */}
            <div className="flex gap-3 pt-2">
              <Button
                onClick={handleAddProvider}
                disabled={isAdding}
                className="bg-blue-600 hover:bg-blue-700 text-white"
              >
                {isAdding ? 'Creating...' : '✅ Create Firm & Queue Embedding'}
              </Button>
              <Button variant="outline" onClick={() => { setShowAddForm(false); setForm(EMPTY_FORM); setAddStep('url'); setCrawlUrl(''); setCrawlError(''); }}>
                Cancel
              </Button>
            </div>


              </div>
            )}

          </CardContent>
        </Card>
      )}

      {/* Search bar */}
      <div className="flex gap-3 mb-4">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
          <Input
            className="pl-9"
            placeholder="Search by name, city, specialty..."
            value={searchInput}
            onChange={e => setSearchInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleSearch()}
          />
        </div>
        <Button onClick={handleSearch} variant="outline">Search</Button>
        {search && (
          <Button variant="ghost" onClick={() => { setSearch(''); setSearchInput(''); setPage(1); }}>
            <ChevronLeft className="h-4 w-4 mr-1" /> Clear
          </Button>
        )}
      </div>

      {/* Providers Table */}
      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="py-16 text-center text-slate-400">Loading providers...</div>
          ) : providers.length === 0 ? (
            <div className="py-16 text-center text-slate-400">No providers found</div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow className="bg-slate-50">
                  <TableHead className="font-semibold">Firm Name</TableHead>
                  <TableHead className="font-semibold">Location</TableHead>
                  <TableHead className="font-semibold">Tier</TableHead>
                  <TableHead className="font-semibold">Primary Specialty</TableHead>
                  <TableHead className="font-semibold">Website</TableHead>
                  <TableHead className="font-semibold">Added</TableHead>
                  <TableHead className="text-right font-semibold">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {providers.map(p => (
                  <TableRow key={p.id} className="hover:bg-slate-50">
                    <TableCell>
                      <div className="font-medium text-slate-900">{p.firm_name || p.name || '—'}</div>
                      {p.firm_name && p.name && p.firm_name !== p.name && (
                        <div className="text-xs text-slate-400">{p.name}</div>
                      )}
                    </TableCell>
                    <TableCell className="text-slate-600 text-sm">
                      {[p.city, p.state].filter(Boolean).join(', ') || '—'}
                    </TableCell>
                    <TableCell>
                      {p.business_evaluation_tier ? (
                        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-bold bg-blue-100 text-blue-800">
                          {p.business_evaluation_tier}
                        </span>
                      ) : '—'}
                    </TableCell>
                    <TableCell className="text-slate-600 text-sm max-w-[200px] truncate">
                      {p.primary_specialty || '—'}
                    </TableCell>
                    <TableCell className="text-sm">
                      {p.website ? (
                        <a href={p.website} target="_blank" rel="noopener noreferrer"
                          className="text-blue-600 hover:underline truncate block max-w-[140px]">
                          {p.website.replace(/^https?:\/\/(www\.)?/, '')}
                        </a>
                      ) : '—'}
                    </TableCell>
                    <TableCell className="text-slate-500 text-sm">{formatDate(p.created_at)}</TableCell>
                    <TableCell className="text-right">
                      <div className="flex items-center justify-end gap-1">
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => handleEditOpen(p)}
                          className="text-blue-500 hover:text-blue-700 hover:bg-blue-50"
                        >
                          <Pencil className="h-4 w-4" />
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => setDeleteConfirm(p)}
                          className="text-red-500 hover:text-red-700 hover:bg-red-50"
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between mt-4">
          <p className="text-sm text-slate-500">
            Showing {((page - 1) * PAGE_SIZE) + 1}–{Math.min(page * PAGE_SIZE, total)} of {total.toLocaleString()} firms
          </p>
          <div className="flex gap-2">
            <Button
              variant="outline" size="sm"
              onClick={() => setPage(p => Math.max(1, p - 1))}
              disabled={page === 1 || isLoading}
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <span className="flex items-center px-3 text-sm font-medium">
              {page} / {totalPages}
            </span>
            <Button
              variant="outline" size="sm"
              onClick={() => setPage(p => Math.min(totalPages, p + 1))}
              disabled={page === totalPages || isLoading}
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}

    </div>
  );
}
