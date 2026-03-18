'use client';

import Link from 'next/link';
import { Building2, CheckCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';

const softwareFeatures = [
  'Appear on Software Providers page',
  'Direct link to your product',
  'Reach active engineering buyers',
  'Cancel anytime',
];

const featuredFeatures = [
  'Direct access to engineering customers',
  'Bypass the RFQ process',
  'Premium placement on Featured Firms page',
  'Cancel anytime',
];

const faqs = [
  { q: 'How does billing work?', a: 'You are billed $50/month per ad slot via Stripe. Your card is charged automatically each billing cycle. Manage your subscription through the billing portal at any time.' },
  { q: 'Can I cancel?', a: 'Yes, cancel anytime from your advertiser dashboard. Your ad remains active until the end of the current billing period.' },
  { q: 'How many slots are available?', a: 'There are a limited number of premium slots per page to ensure maximum visibility. Once slots are filled, new advertisers join a waitlist.' },
];

export default function AdvertisePage() {
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
        <section className="bg-blue-600 text-white py-20 px-6">
          <div className="max-w-4xl mx-auto text-center">
            <Badge className="bg-blue-500 text-white mb-4">Advertising</Badge>
            <h1 className="text-4xl font-bold mb-4">Advertise on ProMechDirectory</h1>
            <p className="text-xl text-blue-100">
              Reach thousands of engineers and procurement professionals actively searching for services.
            </p>
          </div>
        </section>

        <section className="py-16 px-6">
          <div className="max-w-4xl mx-auto">
            <h2 className="text-2xl font-bold text-center mb-10">Choose Your Ad Placement</h2>
            <div className="grid md:grid-cols-2 gap-8">

              <Card className="border-2 hover:border-blue-300 transition-colors">
                <CardHeader>
                  <Badge className="w-fit mb-2 bg-purple-100 text-purple-800">Software Providers</Badge>
                  <CardTitle className="text-2xl">
                    $50<span className="text-base font-normal text-gray-500">/month</span>
                  </CardTitle>
                  <CardDescription>Reach engineers actively searching for software tools</CardDescription>
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
                  <Link href="/register?role=advertiser&type=software">
                    <Button className="w-full mt-2">Get Started</Button>
                  </Link>
                </CardContent>
              </Card>

              <Card className="border-2 hover:border-blue-300 transition-colors">
                <CardHeader>
                  <Badge className="w-fit mb-2 bg-orange-100 text-orange-800">Featured Firms</Badge>
                  <CardTitle className="text-2xl">
                    $50<span className="text-base font-normal text-gray-500">/month</span>
                  </CardTitle>
                  <CardDescription>Direct access to engineering customers outside the RFQ flow</CardDescription>
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
                  <Link href="/register?role=advertiser&type=featured">
                    <Button className="w-full mt-2">Get Started</Button>
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
