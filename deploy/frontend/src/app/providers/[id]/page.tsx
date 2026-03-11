'use client';

import { useState, useEffect } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { api } from '@/lib/api';
import { Provider } from '@/types';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { MapPin, Globe, Phone, Mail, Star, Building2 } from 'lucide-react';

export default function PublicProviderPage() {
  const { id } = useParams();
  const [provider, setProvider] = useState<Provider | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const fetchProvider = async () => {
      try {
        const response = await api.providers.getPublic(id as string);
        setProvider(response.data);
      } catch (error) {
        console.error('Failed to fetch provider:', error);
      } finally {
        setIsLoading(false);
      }
    };

    if (id) {
      fetchProvider();
    }
  }, [id]);

  if (isLoading) {
    return (
      <div className="container py-8">
        <div className="flex items-center justify-center h-64">
          <p className="text-muted-foreground">Loading...</p>
        </div>
      </div>
    );
  }

  if (!provider) {
    return (
      <div className="container py-8">
        <p className="text-center text-muted-foreground">Provider not found</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      {/* Header */}
      <header className="border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <div className="container flex h-14 items-center">
          <Link href="/" className="flex items-center gap-2 font-bold text-xl">
            <Building2 className="h-6 w-6" />
            <span>ProReadyEngineer</span>
          </Link>
          <nav className="ml-auto flex gap-4">
            <Link href="/search">
              <Button variant="ghost">Search</Button>
            </Link>
            <Link href="/login">
              <Button variant="ghost">Sign In</Button>
            </Link>
          </nav>
        </div>
      </header>

      <main className="container py-8">
        <div className="max-w-4xl mx-auto">
          <Card>
            <CardHeader>
              <div className="flex justify-between items-start">
                <div>
                  <CardTitle className="text-2xl">{provider.name}</CardTitle>
                  <CardDescription className="mt-2">
                    <div className="flex items-center gap-4 text-sm">
                      <span className="flex items-center gap-1">
                        <MapPin className="h-4 w-4" />
                        {provider.city}, {provider.state}
                      </span>
                      {provider.tier && (
                        <span className="flex items-center gap-1">
                          <Star className="h-4 w-4" />
                          Tier {provider.tier}
                        </span>
                      )}
                    </div>
                  </CardDescription>
                </div>
                <Badge variant="outline">
                  {provider.is_engineering_service ? 'Engineering Service' : 'Service Provider'}
                </Badge>
              </div>
            </CardHeader>
            <CardContent className="space-y-6">
              {provider.primary_specialty && (
                <div>
                  <h3 className="font-semibold mb-2">Primary Specialty</h3>
                  <p>{provider.primary_specialty}</p>
                </div>
              )}

              {provider.business_description && (
                <div>
                  <h3 className="font-semibold mb-2">About</h3>
                  <p className="text-muted-foreground">{provider.business_description}</p>
                </div>
              )}

              <div className="grid grid-cols-2 gap-4 pt-4 border-t">
                {provider.website && (
                  <div className="flex items-center gap-2">
                    <Globe className="h-4 w-4 text-muted-foreground" />
                    <a href={provider.website} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">
                      Website
                    </a>
                  </div>
                )}
                {provider.phone && (
                  <div className="flex items-center gap-2">
                    <Phone className="h-4 w-4 text-muted-foreground" />
                    <span>{provider.phone}</span>
                  </div>
                )}
              </div>

              {provider.capabilities && provider.capabilities.length > 0 && (
                <div>
                  <h3 className="font-semibold mb-2">Capabilities</h3>
                  <div className="flex flex-wrap gap-2">
                    {provider.capabilities.map((cap, index) => (
                      <Badge key={index} variant="secondary">{cap}</Badge>
                    ))}
                  </div>
                </div>
              )}

              {provider.software_tools && provider.software_tools.length > 0 && (
                <div>
                  <h3 className="font-semibold mb-2">Software Tools</h3>
                  <div className="flex flex-wrap gap-2">
                    {provider.software_tools.map((tool, index) => (
                      <Badge key={index} variant="outline">{tool}</Badge>
                    ))}
                  </div>
                </div>
              )}

              {provider.certifications && provider.certifications.length > 0 && (
                <div>
                  <h3 className="font-semibold mb-2">Certifications</h3>
                  <ul className="list-disc list-inside text-muted-foreground">
                    {provider.certifications.map((cert, index) => (
                      <li key={index}>{cert}</li>
                    ))}
                  </ul>
                </div>
              )}
            </CardContent>
          </Card>

          <div className="mt-8 flex justify-center">
            <Link href="/customer/rfq/new">
              <Button size="lg">
                Submit RFQ to {provider.name}
              </Button>
            </Link>
          </div>
        </div>
      </main>
    </div>
  );
}
