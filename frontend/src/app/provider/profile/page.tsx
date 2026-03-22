'use client';

import { useState, useEffect } from 'react';
import { useRequireAuth } from '@/hooks/useAuth';
import { api } from '@/lib/api';
import { Provider } from '@/types';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { toast } from 'sonner';

export default function ProviderProfilePage() {
  const { user, isLoading: authLoading } = useRequireAuth(['provider']);
  const [provider, setProvider] = useState<Provider | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isInviteFlow, setIsInviteFlow] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  
  const [formData, setFormData] = useState({
    name: '',
    website: '',
    phone: '',
    address: '',
    city: '',
    state: '',
    postal_code: '',
    primary_specialty: '',
    business_description: '',
    capabilities: [] as string[],
    specialties: [] as string[],
    software_tools: [] as string[],
    certifications: [] as string[],
  });

  useEffect(() => {
    const fetchProvider = async () => {
      const applyProfileData = (data: any) => {
        setProvider(data);
        setFormData({
          name: data.name || '',
          website: data.website || '',
          phone: data.phone || '',
          address: data.address || '',
          city: data.city || '',
          state: data.state || '',
          postal_code: data.postal_code || '',
          primary_specialty: data.primary_specialty || '',
          business_description: data.business_description || '',
          capabilities: data.capabilities || [],
          specialties: data.specialties || [],
          software_tools: data.software_tools || [],
          certifications: data.certifications || [],
        });
      };

      // Check for pending invite token FIRST (before any profile load attempt)
      const pendingToken = typeof window !== 'undefined'
        ? localStorage.getItem('pendingInviteToken')
        : null;

      if (pendingToken) {
        // Mark as invite flow so we show the right message if profile still not found
        setIsInviteFlow(true);
        console.log('[Profile] Pending invite token found, redeeming BEFORE profile load...');
        try {
          await api.auth.redeemInvite(pendingToken);
          console.log('[Profile] Invite token redeemed successfully');
        } catch (redeemErr) {
          console.warn('[Profile] Invite redemption failed (may already be redeemed):', redeemErr);
          // Continue anyway - the backend may have already created the membership
        }
      }

      // Now attempt to load the profile (after any redemption attempt)
      try {
        const response = await api.providers.getProfile();
        if (response.data) {
          applyProfileData(response.data);
          // SUCCESS: clean up invite tokens from localStorage
          if (pendingToken) {
            localStorage.removeItem('pendingInviteToken');
            localStorage.removeItem('pendingInviteRfqId');
            console.log('[Profile] Firm linked successfully, cleared invite tokens from localStorage');
          }
        }
      } catch (err) {
        // Profile not found - if this was an invite flow, show linking message
        if (pendingToken) {
          console.warn('[Profile] Profile not found after invite redemption - showing linking message');
        } else {
          console.warn('[Profile] No provider profile found and no invite token present');
        }
      } finally {
        setIsLoading(false);
      }
    };

    if (user) {
      fetchProvider();
    }
  }, [user]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSaving(true);
    
    try {
      await api.providers.updateProfile(formData);
      toast.success('Profile updated successfully');
    } catch (error) {
      toast.error('Failed to update profile');
    } finally {
      setIsSaving(false);
    }
  };

  if (authLoading || isLoading) {
    return (
      <div className="container py-8">
        <div className="flex items-center justify-center h-64">
          <p className="text-muted-foreground">Loading...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="container py-8 max-w-3xl">
      <h1 className="text-3xl font-bold mb-2">Provider Profile</h1>
      <p className="text-muted-foreground mb-8">
        Manage your engineering firm&apos;s public profile
      </p>

      {!provider ? (
        <Card>
          <CardContent className="py-8 text-center">
            <div className="max-w-sm mx-auto">
              <div className="w-16 h-16 bg-blue-100 rounded-full flex items-center justify-center mx-auto mb-4">
                <svg className="w-8 h-8 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-2 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
                </svg>
              </div>
              {isInviteFlow || (user?.roles || []).includes('provider') ? (
                // Invited providers: show linking message, NOT claim/add buttons
                <>
                  <h3 className="text-lg font-semibold mb-2">Linking Your Firm&hellip;</h3>
                  <p className="text-muted-foreground text-sm mb-6">
                    Your engineering firm is being linked to your account. Please refresh this page in a moment.
                  </p>
                  <Button onClick={() => window.location.reload()} variant="default">
                    Refresh Page
                  </Button>
                </>
              ) : (
                // Non-invite users: show claim/add options
                <>
                  <h3 className="text-lg font-semibold mb-2">No Firm Linked Yet</h3>
                  <p className="text-muted-foreground text-sm mb-6">
                    Your account is not yet linked to an engineering firm. Search for your firm below to claim it, or add a new one.
                  </p>
                  <div className="flex flex-col gap-3">
                    <Button onClick={() => window.location.href = '/provider/claim'} variant="default">
                      Search &amp; Claim Your Firm
                    </Button>
                    <Button onClick={() => window.location.href = '/provider/add-firm'} variant="outline">
                      Add New Firm
                    </Button>
                  </div>
                </>
              )}
            </div>
          </CardContent>
        </Card>
      ) : (
        <form onSubmit={handleSubmit}>
          <div className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle>Basic Information</CardTitle>
                <CardDescription>Your company details</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="name">Company Name</Label>
                  <Input
                    id="name"
                    value={formData.name}
                    onChange={(e) => setFormData(prev => ({ ...prev, name: e.target.value }))}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="website">Website</Label>
                  <Input
                    id="website"
                    value={formData.website}
                    onChange={(e) => setFormData(prev => ({ ...prev, website: e.target.value }))}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="phone">Phone</Label>
                  <Input
                    id="phone"
                    value={formData.phone}
                    onChange={(e) => setFormData(prev => ({ ...prev, phone: e.target.value }))}
                  />
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Location</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="address">Address</Label>
                  <Input
                    id="address"
                    value={formData.address}
                    onChange={(e) => setFormData(prev => ({ ...prev, address: e.target.value }))}
                  />
                </div>
                <div className="grid grid-cols-3 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="city">City</Label>
                    <Input
                      id="city"
                      value={formData.city}
                      onChange={(e) => setFormData(prev => ({ ...prev, city: e.target.value }))}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="state">State</Label>
                    <Input
                      id="state"
                      value={formData.state}
                      onChange={(e) => setFormData(prev => ({ ...prev, state: e.target.value }))}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="postal_code">Postal Code</Label>
                    <Input
                      id="postal_code"
                      value={formData.postal_code}
                      onChange={(e) => setFormData(prev => ({ ...prev, postal_code: e.target.value }))}
                    />
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Business Description</CardTitle>
                <CardDescription>
                  Describe your engineering capabilities and specialties
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="primary_specialty">Primary Specialty</Label>
                  <Input
                    id="primary_specialty"
                    value={formData.primary_specialty}
                    onChange={(e) => setFormData(prev => ({ ...prev, primary_specialty: e.target.value }))}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="business_description">Business Description</Label>
                  <Textarea
                    id="business_description"
                    rows={5}
                    value={formData.business_description}
                    onChange={(e) => setFormData(prev => ({ ...prev, business_description: e.target.value }))}
                  />
                </div>
              </CardContent>
            </Card>

            <Button type="submit" className="w-full" disabled={isSaving}>
              {isSaving ? 'Saving...' : 'Save Changes'}
            </Button>
          </div>
        </form>
      )}
    </div>
  );
}
