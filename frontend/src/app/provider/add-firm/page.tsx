'use client';

import { useState, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { useRequireAuth } from '@/hooks/useAuth';
import { api } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { toast } from 'sonner';
import { CheckCircle, CreditCard, Mail, ArrowLeft, Loader2 } from 'lucide-react';

type Step = 'select' | 'payment' | 'form' | 'inquiry' | 'success';

function AddFirmContent() {
  const { user, isLoading: authLoading } = useRequireAuth(['provider']);
  const router = useRouter();
  const searchParams = useSearchParams();
  const isPremium = searchParams.get('tier') === 'premium';

  const [step, setStep] = useState<Step>(isPremium ? 'inquiry' : 'select');
  const [isLoading, setIsLoading] = useState(false);
  const [paymentIntentId, setPaymentIntentId] = useState('');
  const [clientSecret, setClientSecret] = useState('');

  // Self-service form state
  const [firmName, setFirmName] = useState('');
  const [city, setCity] = useState('');
  const [state, setState] = useState('');
  const [website, setWebsite] = useState('');
  const [phone, setPhone] = useState('');
  const [primarySpecialty, setPrimarySpecialty] = useState('');
  const [businessDescription, setBusinessDescription] = useState('');
  const [notableProjects, setNotableProjects] = useState('');

  // Inquiry form state
  const [inquiryFirmName, setInquiryFirmName] = useState('');
  const [inquiryDescription, setInquiryDescription] = useState('');
  const [contactName, setContactName] = useState('');

  const handleStartPayment = async () => {
    setIsLoading(true);
    try {
      const response = await api.providers.selfRegisterCheckout();
      const data = response.data as any;
      setPaymentIntentId(data.payment_intent_id || data.external_payment_id || '');
      setClientSecret(data.client_secret || '');
      setStep('payment');
    } catch (error: any) {
      toast.error(error?.response?.data?.detail || 'Failed to initiate payment');
    } finally {
      setIsLoading(false);
    }
  };

  const handlePaymentConfirm = () => {
    setStep('form');
  };

  const handleSelfRegisterSubmit = async () => {
    if (!firmName.trim()) {
      toast.error('Firm name is required');
      return;
    }
    setIsLoading(true);
    try {
      const projects = notableProjects
        .split('\n')
        .map((p) => p.trim())
        .filter((p) => p.length > 0);
      await api.providers.selfRegisterSubmit({
        name: firmName,
        city: city || undefined,
        state: state || undefined,
        website: website || undefined,
        phone: phone || undefined,
        primary_specialty: primarySpecialty || undefined,
        business_description: businessDescription || undefined,
        proven_experience_notable_projects: projects,
        payment_intent_id: paymentIntentId,
      });
      setStep('success');
    } catch (error: any) {
      toast.error(error?.response?.data?.detail || 'Failed to submit listing');
    } finally {
      setIsLoading(false);
    }
  };

  const handleInquirySubmit = async () => {
    if (!inquiryFirmName.trim() || !contactName.trim()) {
      toast.error('Firm name and contact name are required');
      return;
    }
    setIsLoading(true);
    try {
      await api.providers.listingInquiry({
        firm_name: inquiryFirmName,
        firm_description: inquiryDescription,
        contact_name: contactName,
      });
      setStep('success');
    } catch (error: any) {
      toast.error(error?.response?.data?.detail || 'Failed to send inquiry');
    } finally {
      setIsLoading(false);
    }
  };

  if (authLoading) {
    return (
      <div className="container py-8">
        <div className="flex items-center justify-center h-64">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      </div>
    );
  }

  return (
    <div className="container py-8 max-w-2xl">
      <Link href="/provider/dashboard" className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground mb-6">
        <ArrowLeft className="h-4 w-4" />
        Back to Dashboard
      </Link>

      {/* Step: Select */}
      {step === 'select' && (
        <div>
          <h1 className="text-3xl font-bold mb-2">Add Your Firm</h1>
          <p className="text-muted-foreground mb-8">Choose a listing option that works for you</p>

          <div className="grid gap-4">
            {/* Self-Service Option */}
            <Card className="border-blue-200 hover:border-blue-400 transition-colors">
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="text-lg">Self-Service Listing</CardTitle>
                  <Badge className="bg-blue-600 text-white text-base px-3 py-1">$100</Badge>
                </div>
                <CardDescription>Build and publish your own profile.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                <ul className="text-sm space-y-1 text-muted-foreground">
                  <li className="flex items-center gap-2"><CheckCircle className="h-4 w-4 text-blue-500" /> Instant listing after payment</li>
                  <li className="flex items-center gap-2"><CheckCircle className="h-4 w-4 text-blue-500" /> You control the content</li>
                  <li className="flex items-center gap-2"><CheckCircle className="h-4 w-4 text-blue-500" /> Receive matching RFQ teasers</li>
                  <li className="flex items-center gap-2"><CheckCircle className="h-4 w-4 text-blue-500" /> One-time fee, no subscription</li>
                </ul>
                <Button
                  className="w-full bg-blue-600 hover:bg-blue-700 text-white"
                  onClick={handleStartPayment}
                  disabled={isLoading}
                >
                  {isLoading ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <CreditCard className="h-4 w-4 mr-2" />}
                  Get Started — $100
                </Button>
              </CardContent>
            </Card>

            {/* AI-Assisted Option */}
            <Card className="border-purple-200 hover:border-purple-400 transition-colors">
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="text-lg">AI-Assisted Listing</CardTitle>
                  <Badge className="bg-purple-600 text-white text-base px-3 py-1">$750</Badge>
                </div>
                <CardDescription>Our team builds your profile using AI.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                <ul className="text-sm space-y-1 text-muted-foreground">
                  <li className="flex items-center gap-2"><CheckCircle className="h-4 w-4 text-purple-500" /> AI-optimized business description</li>
                  <li className="flex items-center gap-2"><CheckCircle className="h-4 w-4 text-purple-500" /> Built from your website and materials</li>
                  <li className="flex items-center gap-2"><CheckCircle className="h-4 w-4 text-purple-500" /> Includes tier evaluation</li>
                  <li className="flex items-center gap-2"><CheckCircle className="h-4 w-4 text-purple-500" /> Dedicated onboarding support</li>
                </ul>
                <Button
                  className="w-full bg-purple-600 hover:bg-purple-700 text-white"
                  onClick={() => setStep('inquiry')}
                >
                  <Mail className="h-4 w-4 mr-2" />
                  Request AI Listing
                </Button>
              </CardContent>
            </Card>
          </div>
        </div>
      )}

      {/* Step: Payment */}
      {step === 'payment' && (
        <div>
          <h1 className="text-3xl font-bold mb-2">Complete Payment</h1>
          <p className="text-muted-foreground mb-8">One-time fee for self-service listing</p>
          <Card>
            <CardHeader>
              <CardTitle>Self-Service Listing — $100</CardTitle>
              <CardDescription>Secure payment via Stripe</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="bg-gray-50 rounded-lg p-4 text-sm text-muted-foreground">
                <p className="font-medium text-foreground mb-1">What you get:</p>
                <ul className="space-y-1">
                  <li>• Your firm listed in our directory of 5,400+ providers</li>
                  <li>• Receive RFQ teasers matching your specialties</li>
                  <li>• Ability to submit quotes to matched projects</li>
                </ul>
              </div>
              <div className="border rounded-lg p-4 bg-yellow-50 text-sm text-yellow-800">
                <p className="font-medium">Demo Mode</p>
                <p>Payment integration is configured in admin settings. Contact us to complete your listing.</p>
              </div>
              <div className="flex gap-3">
                <Button variant="outline" onClick={() => setStep('select')} className="flex-1">
                  Back
                </Button>
                <Button className="flex-1 bg-blue-600 hover:bg-blue-700 text-white" onClick={handlePaymentConfirm}>
                  <CreditCard className="h-4 w-4 mr-2" />
                  Confirm Payment
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Step: Form */}
      {step === 'form' && (
        <div>
          <h1 className="text-3xl font-bold mb-2">Your Firm Profile</h1>
          <p className="text-muted-foreground mb-8">Fill in your firm details. Be specific about your capabilities and past projects.</p>
          <Card>
            <CardContent className="pt-6 space-y-4">
              <div>
                <Label htmlFor="firmName">Firm Name *</Label>
                <Input id="firmName" value={firmName} onChange={(e) => setFirmName(e.target.value)} placeholder="Acme Engineering LLC" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label htmlFor="city">City</Label>
                  <Input id="city" value={city} onChange={(e) => setCity(e.target.value)} placeholder="Houston" />
                </div>
                <div>
                  <Label htmlFor="state">State</Label>
                  <Input id="state" value={state} onChange={(e) => setState(e.target.value)} placeholder="TX" />
                </div>
              </div>
              <div>
                <Label htmlFor="website">Website</Label>
                <Input id="website" value={website} onChange={(e) => setWebsite(e.target.value)} placeholder="https://acmeengineering.com" />
              </div>
              <div>
                <Label htmlFor="phone">Phone</Label>
                <Input id="phone" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+1 (555) 000-0000" />
              </div>
              <div>
                <Label htmlFor="specialty">Primary Specialty</Label>
                <Input id="specialty" value={primarySpecialty} onChange={(e) => setPrimarySpecialty(e.target.value)} placeholder="Thermal & Fluid Systems" />
              </div>
              <div>
                <Label htmlFor="description">Business Description</Label>
                <Textarea
                  id="description"
                  value={businessDescription}
                  onChange={(e) => setBusinessDescription(e.target.value)}
                  placeholder="Describe your firm's expertise, focus areas, and what makes you unique..."
                  rows={4}
                />
              </div>
              <div>
                <Label htmlFor="projects">Notable Projects (one per line)</Label>
                <Textarea
                  id="projects"
                  value={notableProjects}
                  onChange={(e) => setNotableProjects(e.target.value)}
                  placeholder="CFD analysis of gas turbine combustor for Tier 1 aerospace client\nStructural fatigue analysis for offshore platform design\nThermal management system for EV battery pack"
                  rows={5}
                />
              </div>
              <div className="flex gap-3 pt-2">
                <Button variant="outline" onClick={() => setStep('payment')} className="flex-1">
                  Back
                </Button>
                <Button
                  className="flex-1 bg-blue-600 hover:bg-blue-700 text-white"
                  onClick={handleSelfRegisterSubmit}
                  disabled={isLoading}
                >
                  {isLoading ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : null}
                  Submit Listing
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Step: Inquiry */}
      {step === 'inquiry' && (
        <div>
          <h1 className="text-3xl font-bold mb-2">AI-Assisted Listing</h1>
          <p className="text-muted-foreground mb-8">Tell us about your firm and we'll build your profile using AI.</p>
          <Card>
            <CardHeader>
              <CardTitle>Listing Inquiry</CardTitle>
              <CardDescription>Our team will reach out within 1-2 business days to begin your onboarding.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <Label htmlFor="contactName">Your Name *</Label>
                <Input id="contactName" value={contactName} onChange={(e) => setContactName(e.target.value)} placeholder="Jane Smith" />
              </div>
              <div>
                <Label htmlFor="inquiryFirmName">Firm Name *</Label>
                <Input id="inquiryFirmName" value={inquiryFirmName} onChange={(e) => setInquiryFirmName(e.target.value)} placeholder="Acme Engineering LLC" />
              </div>
              <div>
                <Label htmlFor="inquiryDescription">Brief Description</Label>
                <Textarea
                  id="inquiryDescription"
                  value={inquiryDescription}
                  onChange={(e) => setInquiryDescription(e.target.value)}
                  placeholder="Tell us about your firm's specialties, experience, and what kinds of projects you handle..."
                  rows={4}
                />
              </div>
              <div className="bg-purple-50 rounded-lg p-4 text-sm text-purple-800">
                <p className="font-medium mb-1">What happens next?</p>
                <ol className="list-decimal list-inside space-y-1">
                  <li>We review your submission</li>
                  <li>Our AI analyzes your website and materials</li>
                  <li>We build and optimize your profile</li>
                  <li>You review and approve before publishing</li>
                </ol>
              </div>
              <div className="flex gap-3">
                <Button variant="outline" onClick={() => setStep('select')} className="flex-1">
                  Back
                </Button>
                <Button
                  className="flex-1 bg-purple-600 hover:bg-purple-700 text-white"
                  onClick={handleInquirySubmit}
                  disabled={isLoading}
                >
                  {isLoading ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Mail className="h-4 w-4 mr-2" />}
                  Send Inquiry
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Step: Success */}
      {step === 'success' && (
        <div className="text-center py-12">
          <div className="flex justify-center mb-4">
            <CheckCircle className="h-16 w-16 text-green-500" />
          </div>
          <h1 className="text-3xl font-bold mb-2">You're All Set!</h1>
          <p className="text-muted-foreground mb-8 max-w-md mx-auto">
            Your submission has been received. You'll receive a confirmation email shortly.
          </p>
          <div className="flex gap-3 justify-center">
            <Button variant="outline" onClick={() => router.push('/provider/dashboard')}>
              Go to Dashboard
            </Button>
            <Button className="bg-blue-600 hover:bg-blue-700 text-white" onClick={() => router.push('/provider/claim')}>
              Claim Existing Listing
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

export default function AddFirmPage() {
  return (
    <Suspense
      fallback={
        <div className="container py-8">
          <div className="flex items-center justify-center h-64">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        </div>
      }
    >
      <AddFirmContent />
    </Suspense>
  );
}
