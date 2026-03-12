'use client';
import { useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { api } from '@/lib/api';

const ic = 'mt-1 block w-full border border-gray-300 rounded-md shadow-sm py-2 px-3 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm';
const lc = 'block text-sm font-medium text-gray-700';

export default function RegisterPage() {
  const router = useRouter();
  const [fd, setFd] = useState({
    email: '',
    password: '',
    confirmPassword: '',
    full_name: '',
    company_name: '',
    phone: '',
    role: 'customer' as 'customer' | 'provider' | 'advertiser',
  });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const hc = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setFd(p => ({ ...p, [e.target.name]: e.target.value }));

  const hs = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    if (fd.password !== fd.confirmPassword) { setError('Passwords do not match'); return; }
    if (fd.password.length < 8) { setError('Password must be at least 8 characters'); return; }
    setLoading(true);
    try {
      const body: Record<string, unknown> = {
        email: fd.email,
        password: fd.password,
        roles: [fd.role],
      };
      if (fd.full_name.trim()) body.full_name = fd.full_name.trim();
      if (fd.company_name.trim()) body.company_name = fd.company_name.trim();
      if (fd.phone.trim()) body.phone = fd.phone.trim();

      await api.auth.register(body as any);
      router.push('/login?registered=1');
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { detail?: string } }; message?: string };
      const detail = axiosErr?.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : axiosErr?.message || 'Registration failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col justify-center py-12 sm:px-6 lg:px-8">
      <div className="sm:mx-auto sm:w-full sm:max-w-md">
        <h1 className="text-center text-2xl font-bold text-blue-700">ProReadyEngineer</h1>
        <h2 className="mt-4 text-center text-3xl font-extrabold text-gray-900">Create your account</h2>
        <p className="mt-2 text-center text-sm text-gray-600">
          Already have an account?{' '}
          <Link href="/login" className="font-medium text-blue-600 hover:text-blue-500">Sign in</Link>
        </p>
      </div>
      <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md">
        <div className="bg-white py-8 px-4 shadow sm:rounded-lg sm:px-10">
          {error && (
            <div className="mb-4 bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded text-sm">
              {error}
            </div>
          )}
          <form onSubmit={hs} className="space-y-5">
            <div>
              <label className={lc}>I am a</label>
              <select name="role" value={fd.role} onChange={hc} className={ic}>
                <option value="customer">Customer (seeking engineering services)</option>
                <option value="provider">Provider (engineering firm)</option>
                <option value="advertiser">Advertiser</option>
              </select>
            </div>
            <div>
              <label className={lc}>Full Name <span className="text-gray-400">(optional)</span></label>
              <input type="text" name="full_name" value={fd.full_name} onChange={hc} placeholder="Jane Smith" className={ic} />
            </div>
            <div>
              <label className={lc}>Company Name{fd.role === 'provider' ? '' : ' (optional)'}</label>
              <input type="text" name="company_name" value={fd.company_name} onChange={hc} placeholder="Acme Engineering LLC" className={ic} required={fd.role === 'provider'} />
            </div>
            <div>
              <label className={lc}>Phone <span className="text-gray-400">(optional)</span></label>
              <input type="tel" name="phone" value={fd.phone} onChange={hc} placeholder="+1 (555) 000-0000" className={ic} />
            </div>
            <div>
              <label className={lc}>Email address</label>
              <input type="email" name="email" value={fd.email} onChange={hc} required autoComplete="email" className={ic} />
            </div>
            <div>
              <label className={lc}>Password</label>
              <input type="password" name="password" value={fd.password} onChange={hc} required autoComplete="new-password" className={ic} />
              <p className="mt-1 text-xs text-gray-500">Minimum 8 characters</p>
            </div>
            <div>
              <label className={lc}>Confirm Password</label>
              <input type="password" name="confirmPassword" value={fd.confirmPassword} onChange={hc} required autoComplete="new-password" className={ic} />
            </div>
            <button
              type="submit"
              disabled={loading}
              className="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? 'Creating account...' : 'Create account'}
            </button>
          </form>
          <p className="mt-4 text-center text-xs text-gray-500">
            By registering you agree to our Terms of Service and Privacy Policy.
          </p>
        </div>
      </div>
    </div>
  );
}
