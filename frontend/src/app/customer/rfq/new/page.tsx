'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
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

const tollgateOptions = [
  { value: 'TG0', label: 'TG0: Idea Generation' },
  { value: 'TG1', label: 'TG1: Basic Engineering' },
  { value: 'TG3', label: 'TG3: Intermediate Analysis' },
  { value: 'TG4', label: 'TG4: Full Scale Modeling' },
  { value: 'TG6', label: 'TG6: Full System Testing' },
  { value: 'All', label: 'All Phases' },
  { value: 'DontKnow', label: "Don't Know" },
];

export default function CreateRFQPage() {
  const { user, isLoading: authLoading } = useRequireAuth(['customer']);
  const router = useRouter();
  
  const [formData, setFormData] = useState({
    customer_email: user?.email || '',
    business_name: '',
    contact_name: '',
    project_description: '',
    urgency: 'Intermediate' as 'High' | 'Intermediate' | 'Low',
    tollgate_phases: [] as string[],
    nda_required: false,
  });
  
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleTollgateToggle = (value: string) => {
    setFormData(prev => ({
      ...prev,
      tollgate_phases: prev.tollgate_phases.includes(value)
        ? prev.tollgate_phases.filter(p => p !== value)
        : [...prev.tollgate_phases, value]
    }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    
    try {
      const response = await api.rfqs.create(formData);
      toast.success('RFQ created successfully');
      
      if (formData.nda_required) {
        router.push(`/customer/rfq/${response.data.id}/nda`);
      } else {
        router.push(`/customer/rfq/${response.data.id}`);
      }
    } catch (error) {
      toast.error('Failed to create RFQ');
    } finally {
      setIsSubmitting(false);
    }
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
    <div className="container py-8 max-w-3xl">
      <h1 className="text-3xl font-bold mb-2">Create New RFQ</h1>
      <p className="text-muted-foreground mb-8">Describe your engineering project to receive quotes</p>
      
      <form onSubmit={handleSubmit}>
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Contact Information</CardTitle>
              <CardDescription>How providers can reach you</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="customer_email">Email *</Label>
                <Input
                  id="customer_email"
                  type="email"
                  value={formData.customer_email}
                  onChange={(e) => setFormData(prev => ({ ...prev, customer_email: e.target.value }))}
                  required
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="business_name">Business Name</Label>
                <Input
                  id="business_name"
                  value={formData.business_name}
                  onChange={(e) => setFormData(prev => ({ ...prev, business_name: e.target.value }))}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="contact_name">Contact Name</Label>
                <Input
                  id="contact_name"
                  value={formData.contact_name}
                  onChange={(e) => setFormData(prev => ({ ...prev, contact_name: e.target.value }))}
                />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Project Details</CardTitle>
              <CardDescription>Tell us about your engineering needs</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="project_description">Project Description *</Label>
                <Textarea
                  id="project_description"
                  rows={5}
                  value={formData.project_description}
                  onChange={(e) => setFormData(prev => ({ ...prev, project_description: e.target.value }))}
                  placeholder="Describe your project requirements, technical specifications, timeline..."
                  required
                />
              </div>
              
              <div className="space-y-2">
                <Label htmlFor="urgency">Urgency *</Label>
                <Select
                  value={formData.urgency}
                  onValueChange={(value) => setFormData(prev => ({ ...prev, urgency: value as any }))}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="High">High</SelectItem>
                    <SelectItem value="Intermediate">Intermediate</SelectItem>
                    <SelectItem value="Low">Low</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label>Tollgate Phases</Label>
                <div className="grid grid-cols-2 gap-2">
                  {tollgateOptions.map((option) => (
                    <div key={option.value} className="flex items-center space-x-2">
                      <Checkbox
                        id={`tollgate-${option.value}`}
                        checked={formData.tollgate_phases.includes(option.value)}
                        onCheckedChange={() => handleTollgateToggle(option.value)}
                      />
                      <Label htmlFor={`tollgate-${option.value}`} className="font-normal text-sm">
                        {option.label}
                      </Label>
                    </div>
                  ))}
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>NDA & Attachments</CardTitle>
              <CardDescription>Additional requirements</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center space-x-2">
                <Checkbox
                  id="nda_required"
                  checked={formData.nda_required}
                  onCheckedChange={(checked) => 
                    setFormData(prev => ({ ...prev, nda_required: checked as boolean }))
                  }
                />
                <Label htmlFor="nda_required" className="font-normal">
                  NDA Required ($5 handling fee)
                </Label>
              </div>
              
              <div className="pt-4 border-t">
                <Button type="button" variant="outline">
                  Upload Project Files (PDF, DOCX, DWG, STEP)
                </Button>
                <p className="text-sm text-muted-foreground mt-2">Max file size: 25MB</p>
              </div>
            </CardContent>
          </Card>

          <div className="flex gap-4">
            <Button type="submit" className="flex-1" disabled={isSubmitting}>
              {isSubmitting ? 'Creating...' : 'Create RFQ'}
            </Button>
            <Button type="button" variant="outline" onClick={() => router.back()}>
              Cancel
            </Button>
          </div>
        </div>
      </form>
    </div>
  );
}
