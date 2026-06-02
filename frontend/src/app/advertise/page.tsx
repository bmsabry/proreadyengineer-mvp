'use client';

import { useEffect } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Building2, CheckCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { useAuth } from '@/contexts/AuthContext';

const softwareFeatures = [
  'Appear on the Software Providers directory',
  'Direct link to your product page',
  'LLM-powered search visibility for engineering buyers',
  'Cancel anytime',
];

const featuredFeatures = [
  'Direct access to engineering customers',
  'Premium placement on Featured Firms directory',
  'LLM-powered search visibility with matching',
  'Cancel anytime',
];

const faqs = [
  { q: 'How does billing work?', a: 'You are billed $50/month per ad via Stripe, charged automatically each billing cycle. The $50/month rate is our founding (introductory) price — after the introductory period it rises to $350/month, but advertisers who subscribe now keep $50/month for their full first year. Manage your subscription at any time.' },
  { q: 'Can I cancel?', a: 'Yes, cancel anytime from your dashboard. Your ad remains active until the end of the current billing period.' },
  { q: 'How does the ad creation work?', a: 'Just provide your website URL and/or upload a brochure. Our AI reads your materials and generates a professional ad card. Admin reviews it before it goes live.' },
  { q: 'How many ads can I place?', a: 'There is no limit. Each directory page expands to show all active ads, so your listing is always visible.' },
];

export default function AdvertisePage() {
  const { user, isLoading } = useAuth();
  const router = useRouter();

  // If logged-in provider, redirect to submission flow
  useEffect(() => {
    if (!isLoading && user) {
      const roles = user.roles ?? [];
      if (roles.includes('provider')) {
        router.push('/provider/advertise');
        return;
      }
    }
  }, [user, isLoading, router]);

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      <header className="bg-white border-b px-6 py-4">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <Link href="/" className="flex items-center gap-2">
            <Building2 className="h-6 w-6 text-blue-600" />
            <span className="font-bold text-lg">ProMechDirectory</span>
          </Link>
          <nav className="flex items-center gap-4">
            <Link href="/search" className="text-sm text-gray-600 hover:text-gray-900">Search</Link>
            <Link href="/login"><Button variant="outline" size="sm">Sign In</Button></Link>
          </nav>
        </div>
      </header>

      <main className="flex-1">
        <section className="bg-gradient-to-br from-primary to-[#1a3d6e] text-white py-20 px-6">
          <div className="max-w-4xl mx-auto text-center">
            <Badge className="bg-white/20 text-white mb-4 border-white/30">Advertising</Badge>
            <h1 className="text-4xl font-bold mb-4">Advertise on ProMechDirectory</h1>
            <p className="text-xl text-blue-100 mb-2">
              Reach thousands of engineers and procurement professionals actively searching for services.
            </p>
            <p className="text-sm text-blue-200">
              AI-powered ad generation — just provide your website or upload a brochure.
            </p>
          </div>
        </section>

        <section className="py-16 px-6">
          <div className="max-w-4xl mx-auto">
            <h2 className="text-2xl font-bold text-center mb-10">Choose Your Ad Placement</h2>
            <div className="grid md:grid-cols-2 gap-8">

              <Card className="border-2 hover:border-violet-300 transition-colors">
                <CardHeader>
                  <Badge className="w-fit mb-2 bg-purple-100 text-purple-800">Software Providers</Badge>
                  <CardTitle className="text-2xl">
                    $50<span className="text-base font-normal text-gray-500">/month</span>
                  </CardTitle>
                  <CardDescription>Promote your software tools to active engineering buyers</CardDescription>
                  <p className="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded-md px-2.5 py-2 mt-2 leading-relaxed">
                    <span className="font-semibold">Founding rate.</span> $50/month is our introductory founding price. After the introductory period the price rises to <span className="font-semibold">$350/month</span> — but subscribe now and you keep $50/month for your full first year.
                  </p>
                </CardHeader>
                <CardContent className="space-y-4">
                  <ul className="space-y-2">
                    {softwareFeatures.map((f) => (
                      <li key={f} className="flex items-center gap-2 text-sm">
                        <CheckCircle className="h-4 w-4 text-green-500 flex-shrink-0" />
                        {f}
                      </li>
                    ))}
                  </ul>
                  <Link href="/register?role=provider&redirect=/provider/advertise?type=software-providers">
                    <Button className="w-full mt-2 bg-primary hover:bg-primary/90">Get Started</Button>
                  </Link>
                </CardContent>
              </Card>

              <Card className="border-2 hover:border-violet-300 transition-colors">
                <CardHeader>
                  <Badge className="w-fit mb-2 bg-orange-100 text-orange-800">Featured Firms</Badge>
                  <CardTitle className="text-2xl">
                    $50<span className="text-base font-normal text-gray-500">/month</span>
                  </CardTitle>
                  <CardDescription>Direct access to engineering customers outside the RFQ flow</CardDescription>
                  <p className="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded-md px-2.5 py-2 mt-2 leading-relaxed">
                    <span className="font-semibold">Founding rate.</span> $50/month is our introductory founding price. After the introductory period the price rises to <span className="font-semibold">$350/month</span> — but subscribe now and you keep $50/month for your full first year.
                  </p>
                </CardHeader>
                <CardContent className="space-y-4">
                  <ul className="space-y-2">
                    {featuredFeatures.map((f) => (
                      <li key={f} className="flex items-center gap-2 text-sm">
                        <CheckCircle className="h-4 w-4 text-green-500 flex-shrink-0" />
                        {f}
                      </li>
                    ))}
                  </ul>
                  <Link href="/register?role=provider&redirect=/provider/advertise?type=featured-firms">
                    <Button className="w-full mt-2 bg-primary hover:bg-primary/90">Get Started</Button>
                  </Link>
                </CardContent>
              </Card>

            </div>
          </div>
        </section>

        <section className="py-12 px-6 bg-white">
          <div className="max-w-2xl mx-auto">
            <h2 className="text-2xl font-bold text-center mb-8">Frequently Asked Questions</h2>
            <div className="space-y-6">
              {faqs.map((faq) => (
                <div key={faq.q} className="border-b pb-4">
                  <h3 className="font-semibold mb-2">{faq.q}</h3>
                  <p className="text-gray-600 text-sm">{faq.a}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="py-10 px-6 text-center bg-gray-50">
          <p className="text-gray-600">
            Already have an account?{' '}
            <Link href="/login" className="text-blue-600 hover:underline font-medium">
              Sign in to manage your ads
            </Link>
          </p>
        </section>
      </main>
    </div>
  );
}
