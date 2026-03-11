'use client';

import { useRequireAuth } from '@/hooks/useAuth';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Users, FileText, DollarSign, Building2 } from 'lucide-react';

export default function AdminDashboard() {
  const { isLoading } = useRequireAuth(['admin']);

  if (isLoading) {
    return (
      <div className="container py-8">
        <div className="flex items-center justify-center h-64">
          <p className="text-muted-foreground">Loading...</p>
        </div>
      </div>
    );
  }

  const stats = [
    { title: 'Total Users', value: '1,234', icon: Users, description: 'Active accounts' },
    { title: 'RFQs', value: '567', icon: FileText, description: 'Total requests' },
    { title: 'Providers', value: '890', icon: Building2, description: 'Registered firms' },
    { title: 'Revenue', value: '$45,678', icon: DollarSign, description: 'This month' },
  ];

  return (
    <div className="container py-8">
      <h1 className="text-3xl font-bold mb-8">Admin Dashboard</h1>

      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4">
        {stats.map((stat) => (
          <Card key={stat.title}>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">{stat.title}</CardTitle>
              <stat.icon className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stat.value}</div>
              <p className="text-xs text-muted-foreground">{stat.description}</p>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
