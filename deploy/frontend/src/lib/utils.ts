import { type ClassValue, clsx } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatCurrency(amount: number, currency: string = 'USD'): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: currency,
  }).format(amount);
}

export function formatDate(date: string | Date): string {
  return new Intl.DateTimeFormat('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  }).format(new Date(date));
}

export function formatDateTime(date: string | Date): string {
  return new Intl.DateTimeFormat('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(date));
}

export function formatFileSize(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

export function getRFQStatusBadgeColor(status: string): string {
  const colors: Record<string, string> = {
    'draft': 'bg-gray-500',
    'submitted': 'bg-blue-500',
    'awaiting_nda_payment': 'bg-yellow-500',
    'awaiting_customer_signature': 'bg-orange-500',
    'open_for_dispatch': 'bg-green-500',
    'dispatching': 'bg-blue-600',
    'open_for_unlock': 'bg-indigo-500',
    'quote_limit_reached': 'bg-red-500',
    'customer_selected_provider': 'bg-green-600',
    'closed_no_selection': 'bg-gray-600',
    'cancelled': 'bg-red-600',
  };
  return colors[status] || 'bg-gray-500';
}

export function getQuoteStatusBadgeColor(status: string): string {
  const colors: Record<string, string> = {
    'draft': 'bg-gray-500',
    'submitted': 'bg-blue-500',
    'withdrawn': 'bg-gray-600',
    'customer_viewed': 'bg-yellow-500',
    'shortlisted': 'bg-orange-500',
    'accepted': 'bg-green-500',
    'not_selected': 'bg-red-500',
    'expired': 'bg-gray-400',
  };
  return colors[status] || 'bg-gray-500';
}

export function getTierColor(tier: string): string {
  const colors: Record<string, string> = {
    'A': 'text-green-600 font-bold',
    'B': 'text-blue-600 font-semibold',
    'C': 'text-yellow-600',
    'D': 'text-orange-600',
    'E': 'text-red-600',
  };
  return colors[tier] || 'text-gray-600';
}
