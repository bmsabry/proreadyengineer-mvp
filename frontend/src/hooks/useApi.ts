'use client';

import { useState, useCallback } from 'react';
import { AxiosError } from 'axios';

interface UseApiState<T> {
  data: T | null;
  isLoading: boolean;
  error: string | null;
}

interface UseApiReturn<T, P extends unknown[]> extends UseApiState<T> {
  execute: (...params: P) => Promise<T | null>;
  reset: () => void;
}

export function useApi<T, P extends unknown[]>(
  apiFunction: (...params: P) => Promise<{ data: T }>
): UseApiReturn<T, P> {
  const [state, setState] = useState<UseApiState<T>>({
    data: null,
    isLoading: false,
    error: null,
  });

  const execute = useCallback(
    async (...params: P): Promise<T | null> => {
      setState(prev => ({ ...prev, isLoading: true, error: null }));
      try {
        const response = await apiFunction(...params);
        setState({ data: response.data, isLoading: false, error: null });
        return response.data;
      } catch (err) {
        const error = err as AxiosError<{ detail: string }>;
        const errorMessage = error.response?.data?.detail || error.message || 'An error occurred';
        setState(prev => ({ ...prev, isLoading: false, error: errorMessage }));
        return null;
      }
    },
    [apiFunction]
  );

  const reset = useCallback(() => {
    setState({ data: null, isLoading: false, error: null });
  }, []);

  return { ...state, execute, reset };
}

export function useApiList<T>(
  apiFunction: (params?: Record<string, unknown>) => Promise<{ data: { items: T[]; total: number; page: number; page_size: number } }>
) {
  const [items, setItems] = useState<T[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pagination, setPagination] = useState({ total: 0, page: 1, pageSize: 20 });

  const fetch = useCallback(
    async (params?: Record<string, unknown>) => {
      setIsLoading(true);
      setError(null);
      try {
        const response = await apiFunction(params);
        setItems(response.data.items);
        setPagination({
          total: response.data.total,
          page: response.data.page,
          pageSize: response.data.page_size,
        });
      } catch (err) {
        const error = err as AxiosError<{ detail: string }>;
        setError(error.response?.data?.detail || error.message || 'An error occurred');
      } finally {
        setIsLoading(false);
      }
    },
    [apiFunction]
  );

  return { items, isLoading, error, pagination, fetch };
}
