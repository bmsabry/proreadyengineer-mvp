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
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { toast } from 'sonner';
import { CheckCircle, CreditCard, Mail, ArrowLeft, Loader2 } from 'lucide-react';

type Step = 'select' | 'payment' | 'form' | 'inquiry' | 'success';
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
                <li className="flex items-center gap-2"><CheckCircle className="h-4 w-4 text-purple-500" /> Built from your website &amp; materials</li>
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

        <p className="text-center text-sm text-muted-foreground mt-6">
          Already listed?{' '}
          <Link href="/provider/claim" className="text-primary hover:underline">Search &amp; claim your existing profile</Link>
        </p>
      </div>
    );
  }
            <div>
              <Label htmlFor="business_description">Business Description</Label>
              <Textarea
                id="business_description"
                value={formData.business_description}
                onChange={e => setFormData(p => ({...p, business_description: e.target.value}))}
                placeholder="Describe your firm's capabilities, experience, and specialties..."
                className="min-h-[120px]"
              />
            </div>
            <Button
              className="w-full bg-blue-600 hover:bg-blue-700 text-white"
              onClick={handleSubmitProfile}
              disabled={isSubmitting}
            >
              {isSubmitting ? <><Loader2 className="h-4 w-4 animate-spin mr-2" /> Submitting...</> : 'Create My Listing'}
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  // Step: inquiry
  if (step === 'inquiry') {
    return (
      <div className="container py-8 max-w-2xl">
        <button onClick={() => setStep('select')} className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground mb-6">
          <ArrowLeft className="h-4 w-4" /> Back
        </button>
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Mail className="h-5 w-5 text-purple-600" />
              AI-Assisted Listing Inquiry
            </CardTitle>
            <CardDescription>
              Tell us about your firm. Our team will build an AI-optimized profile within 1–2 business days.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="rounded-md bg-purple-50 border border-purple-200 p-4 text-sm text-purple-800">
              <strong>$750 one-time fee</strong> — includes AI profile build, tier evaluation, and onboarding support.
            </div>
            <div>
              <Label htmlFor="contact_name">Your Name *</Label>
              <Input
                id="contact_name"
                value={inquiryData.contact_name}
                onChange={e => setInquiryData(p => ({...p, contact_name: e.target.value}))}
                placeholder="Jane Smith"
              />
            </div>
            <div>
              <Label htmlFor="firm_name">Firm Name *</Label>
              <Input
                id="firm_name"
                value={inquiryData.firm_name}
                onChange={e => setInquiryData(p => ({...p, firm_name: e.target.value}))}
                placeholder="Acme Engineering LLC"
              />
            </div>
            <div>
              <Label htmlFor="firm_description">Tell us about your firm</Label>
              <Textarea
                id="firm_description"
                value={inquiryData.firm_description}
                onChange={e => setInquiryData(p => ({...p, firm_description: e.target.value}))}
                placeholder="Describe your specialties, capabilities, years in business, notable projects..."
                className="min-h-[140px]"
              />
            </div>
            <Button
              className="w-full bg-purple-600 hover:bg-purple-700 text-white"
              onClick={handleSubmitInquiry}
              disabled={isSubmitting}
            >
              {isSubmitting ? <><Loader2 className="h-4 w-4 animate-spin mr-2" /> Submitting...</> : 'Submit Inquiry'}
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  // Step: success (default return)
  return (
    <div className="container py-8 max-w-2xl">
      <Card>
        <CardContent className="py-12 text-center">
          <CheckCircle className="h-16 w-16 text-green-500 mx-auto mb-4" />
          <h2 className="text-2xl font-bold mb-2">
            {inquiryData.firm_name ? 'Inquiry Submitted!' : 'Your Listing is Live!'}
          </h2>
          <p className="text-muted-foreground mb-6">
            {inquiryData.firm_name
              ? 'Our team will review your information and reach out within 1–2 business days.'
              : 'Your firm is now listed in the ProReadyEngineer directory and will receive RFQ invitations for matching projects.'}
          </p>
          <div className="flex gap-3 justify-center">
            <Button asChild variant="outline">
              <Link href="/provider/dashboard">Go to Dashboard</Link>
            </Button>
            <Button asChild className="bg-blue-600 hover:bg-blue-700 text-white">
              <Link href="/provider/profile">View My Profile</Link>
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

export default function AddFirmPage() {
  return (
    <Suspense fallback={
      <div className="container py-8">
        <div className="flex items-center justify-center h-64">
          <p className="text-muted-foreground">Loading...</p>
        </div>
      </div>
    }>
      <AddFirmPageContent />
    </Suspense>
  );
}
