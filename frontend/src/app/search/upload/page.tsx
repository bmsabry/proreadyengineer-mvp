'use client';

import { useState, useCallback, useRef } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import {
  Upload,
  FileText,
  X,
  ArrowLeft,
  CheckCircle2,
  AlertTriangle,
  Home,
} from 'lucide-react';

const ACCEPTED_TYPES: Record<string, string> = {
  'application/pdf': 'PDF',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'DOCX',
  'application/msword': 'DOC',
  'application/octet-stream': 'DWG/STEP',
  'model/step': 'STEP',
  'model/iges': 'IGES',
};

const ACCEPTED_EXTENSIONS = ['.pdf', '.docx', '.doc', '.dwg', '.step', '.stp'];
const MAX_FILE_SIZE_MB = 25;
const MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024;

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function isAcceptedFile(file: File): boolean {
  if (ACCEPTED_TYPES[file.type]) return true;
  const ext = '.' + file.name.split('.').pop()?.toLowerCase();
  return ACCEPTED_EXTENSIONS.includes(ext);
}
export default function UploadPage() {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const [fileError, setFileError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const handleFile = useCallback((file: File) => {
    setFileError(null);
    if (!isAcceptedFile(file)) {
      setFileError('Unsupported file type. Please upload a PDF, DOCX, DWG, or STEP file.');
      return;
    }
    if (file.size > MAX_FILE_SIZE_BYTES) {
      setFileError(`File too large. Maximum size is ${MAX_FILE_SIZE_MB}MB (your file is ${formatFileSize(file.size)}).`);
      return;
    }
    setSelectedFile(file);
  }, []);

  const handleDragOver = (e: React.DragEvent) => { e.preventDefault(); setIsDragOver(true); };
  const handleDragLeave = (e: React.DragEvent) => { e.preventDefault(); setIsDragOver(false); };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
  };

  const handleClearFile = () => {
    setSelectedFile(null);
    setFileError(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const handleFindProviders = async () => {
    if (!selectedFile) return;
    setIsSubmitting(true);
    setSubmitted(true);
    await new Promise((resolve) => setTimeout(resolve, 1200));
    router.push('/search?uploaded=1');
  };

  const getFileIcon = (file: File) => {
    const ext = file.name.split('.').pop()?.toLowerCase();
    if (ext === 'pdf') return '📄';
    if (ext === 'docx' || ext === 'doc') return '📝';
    if (ext === 'dwg') return '📐';
    if (ext === 'step' || ext === 'stp') return '🔩';
    return '📎';
  };
  return (
    <div className="min-h-screen bg-background">
      <header className="sticky top-0 z-10 border-b bg-background/95 backdrop-blur">
        <div className="max-w-3xl mx-auto px-4 h-14 flex items-center justify-between gap-4">
          <Link href="/" className="flex items-center gap-2 text-foreground hover:opacity-80 transition-opacity shrink-0">
            <Home className="h-4 w-4" />
            <span className="font-semibold text-sm hidden sm:block">ProMechDirectory</span>
          </Link>
          <Link href="/search" className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors">
            <ArrowLeft className="h-4 w-4" />
            Back to Search
          </Link>
        </div>
      </header>
      <main className="max-w-3xl mx-auto px-4 py-12">
        <div className="text-center mb-10">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-gradient-to-br from-blue-500 to-indigo-600 shadow-lg mb-5">
            <Upload className="h-7 w-7 text-white" />
          </div>
          <h1 className="text-2xl font-bold text-foreground mb-2">Upload Your Project Document</h1>
          <p className="text-muted-foreground text-sm max-w-md mx-auto">
            Upload your project document and we&apos;ll find matching engineering providers.
            Accepted formats: PDF, DOCX, DWG, STEP &mdash; up to 25 MB.
          </p>
        </div>
        {submitted ? (
          <Card className="border-green-200 bg-green-50">
            <CardContent className="py-10 text-center">
              <CheckCircle2 className="h-12 w-12 text-green-500 mx-auto mb-4" />
              <h2 className="text-lg font-semibold text-green-900 mb-1">Document received!</h2>
              <p className="text-sm text-green-700 max-w-sm mx-auto">
                Please describe your project in the search bar for best results.
              </p>
              <p className="text-xs text-green-600 mt-1">Redirecting to search&hellip;</p>
            </CardContent>
          </Card>
        ) : (
          <>
            <div
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              onClick={() => !selectedFile && fileInputRef.current?.click()}
              className={['relative rounded-xl border-2 border-dashed transition-all duration-200 cursor-pointer', isDragOver ? 'border-blue-500 bg-blue-50' : selectedFile ? 'border-green-400 bg-green-50/50 cursor-default' : 'border-muted-foreground/25 hover:border-blue-400 hover:bg-blue-50/30'].join(' ')}
            >
              <input ref={fileInputRef} type="file" accept=".pdf,.docx,.doc,.dwg,.step,.stp" className="sr-only" onChange={handleInputChange} />
              {selectedFile ? (
                <div className="flex items-center gap-4 px-6 py-5">
                  <span className="text-3xl">{getFileIcon(selectedFile)}</span>
                  <div className="flex-1 min-w-0">
                    <p className="font-medium text-sm text-foreground truncate">{selectedFile.name}</p>
                    <p className="text-xs text-muted-foreground mt-0.5">{formatFileSize(selectedFile.size)}</p>
                  </div>
                  <button type="button" onClick={(e) => { e.stopPropagation(); handleClearFile(); }} className="shrink-0 rounded-full p-1 hover:bg-muted transition-colors text-muted-foreground hover:text-foreground" aria-label="Remove file">
                    <X className="h-4 w-4" />
                  </button>
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center gap-3 px-6 py-14 text-center">
                  <FileText className="h-10 w-10 text-muted-foreground/40" />
                  <div>
                    <p className="font-medium text-sm text-foreground">{isDragOver ? 'Drop your file here' : 'Drag & drop your file here'}</p>
                    <p className="text-xs text-muted-foreground mt-1">or <span className="text-blue-600 underline underline-offset-2">browse to upload</span></p>
                  </div>
                  <div className="flex gap-2 flex-wrap justify-center mt-1">
                    {['PDF', 'DOCX', 'DWG', 'STEP'].map((fmt) => (
                      <span key={fmt} className="inline-block rounded px-2 py-0.5 text-xs font-medium bg-muted text-muted-foreground border">{fmt}</span>
                    ))}
                  </div>
                  <p className="text-xs text-muted-foreground">Max 25 MB</p>
                </div>
              )}
            </div>
            {fileError && (
              <div className="mt-3 flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2.5">
                <AlertTriangle className="h-4 w-4 text-destructive mt-0.5 shrink-0" />
                <p className="text-xs text-destructive">{fileError}</p>
              </div>
            )}
            <div className="mt-6 flex flex-col sm:flex-row gap-3 justify-center">
              {selectedFile && (
                <Button onClick={handleFindProviders} disabled={isSubmitting} className="bg-blue-600 hover:bg-blue-700 text-white font-semibold px-8" size="lg">
                  {isSubmitting ? (
                    <>
                      <svg className="animate-spin -ml-1 mr-2 h-4 w-4 text-white" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
                      </svg>
                      Processing&hellip;
                    </>
                  ) : ('Find Providers')}
                </Button>
              )}
              <Link href="/search">
                <Button variant="outline" size="lg" className="w-full sm:w-auto">
                  <ArrowLeft className="h-4 w-4 mr-1.5" />
                  Back to Search
                </Button>
              </Link>
            </div>
            <p className="text-center text-xs text-muted-foreground mt-6">
              Tip: For the most accurate matches, include project specifications, required tolerances,
              materials, or relevant engineering standards in your document.
            </p>
          </>
        )}
      </main>
    </div>
  );
}
