'use client';

import { useState, useCallback, useRef } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import {
  Upload,
  FileText,
  X,
  ArrowLeft,
  AlertTriangle,
  Home,
} from 'lucide-react';

const ACCEPTED_TYPES: Record<string, string> = {
  'application/pdf': 'PDF',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'DOCX',
  'application/msword': 'DOC',
  'application/octet-stream': 'DWG/STEP/CAD',
  'model/step': 'STEP',
  'model/iges': 'IGES',
  'model/stl': 'STL',
};

const ACCEPTED_EXTENSIONS = [
  '.pdf', '.docx', '.doc', '.txt',
  '.dwg', '.dxf',
  '.step', '.stp', '.iges', '.igs',
  '.sldprt', '.sldasm',
  '.catpart', '.catproduct',
  '.stl', '.x_t', '.x_b',
  '.prt', '.asm',
];
const MAX_FILE_SIZE_MB = 25;
const MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024;
const MAX_FILES = 5;

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

function getFileIcon(file: File): string {
  const ext = file.name.split('.').pop()?.toLowerCase();
  if (ext === 'pdf') return '📄';
  if (ext === 'docx' || ext === 'doc') return '📝';
  if (ext === 'dwg' || ext === 'dxf') return '📐';
  if (ext === 'step' || ext === 'stp' || ext === 'iges' || ext === 'igs') return '🔩';
  if (ext === 'sldprt' || ext === 'sldasm') return '⚙️';
  if (ext === 'stl') return '🧊';
  if (ext === 'catpart' || ext === 'catproduct') return '🔧';
  return '📎';
}

function getFileCategory(file: File): string {
  const ext = file.name.split('.').pop()?.toLowerCase() || '';
  const cadExts = ['dwg','dxf','step','stp','iges','igs','sldprt','sldasm','catpart','catproduct','stl','x_t','x_b','prt','asm'];
  if (cadExts.includes(ext)) return 'CAD/Engineering';
  return 'Document';
}

export default function UploadPage() {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [isDragOver, setIsDragOver] = useState(false);
  const [fileError, setFileError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const addFiles = useCallback((newFiles: File[]) => {
    setFileError(null);
    const validFiles: File[] = [];
    for (const file of newFiles) {
      if (!isAcceptedFile(file)) {
        setFileError(`Unsupported file type: ${file.name}. Accepted: PDF, DOCX, DWG, STEP, IGES, SolidWorks, CATIA, STL.`);
        return;
      }
      if (file.size > MAX_FILE_SIZE_BYTES) {
        setFileError(`${file.name} is too large (${formatFileSize(file.size)}). Maximum ${MAX_FILE_SIZE_MB}MB per file.`);
        return;
      }
      validFiles.push(file);
    }
    setSelectedFiles(prev => {
      const combined = [...prev, ...validFiles];
      if (combined.length > MAX_FILES) {
        setFileError(`Maximum ${MAX_FILES} files allowed. You have ${prev.length} and tried to add ${validFiles.length}.`);
        return prev;
      }
      return combined;
    });
  }, []);

  const handleDragOver = (e: React.DragEvent) => { e.preventDefault(); setIsDragOver(true); };
  const handleDragLeave = (e: React.DragEvent) => { e.preventDefault(); setIsDragOver(false); };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    const files = Array.from(e.dataTransfer.files);
    if (files.length > 0) addFiles(files);
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    if (files.length > 0) addFiles(files);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const removeFile = (index: number) => {
    setSelectedFiles(prev => prev.filter((_, i) => i !== index));
    setFileError(null);
  };

  const handleClearAll = () => {
    setSelectedFiles([]);
    setFileError(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const handleFindProviders = async () => {
    if (selectedFiles.length === 0) return;
    setIsSubmitting(true);
    try {
      const formData = new FormData();
      for (const file of selectedFiles) {
        formData.append('files', file);
      }
      const response = await fetch('/api/upload-doc', {
        method: 'POST',
        body: formData,
      });
      if (!response.ok) {
        const err = await response.json().catch(() => ({ detail: 'Unknown error' }));
        throw new Error(err.detail || 'Failed to analyze documents');
      }
      const data = await response.json();
      sessionStorage.setItem('docSearchQuery', data.query);
      // Store multi-file data
      if (data.files && data.files.length > 0) {
        sessionStorage.setItem('docSearchFiles', JSON.stringify(data.files));
      }
      if (data.s3_key) sessionStorage.setItem('docSearchS3Key', data.s3_key);
      if (data.extracted_text) sessionStorage.setItem('docSearchExtractedText', data.extracted_text);
      router.push('/search');
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to analyze documents';
      setFileError(message);
      setIsSubmitting(false);
    }
  };

  const docCount = selectedFiles.filter(f => getFileCategory(f) === 'Document').length;
  const cadCount = selectedFiles.filter(f => getFileCategory(f) === 'CAD/Engineering').length;

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
          <h1 className="text-2xl font-bold text-foreground mb-2">Upload Your Project Documents</h1>
          <p className="text-muted-foreground text-sm max-w-md mx-auto">
            Upload up to {MAX_FILES} project files and we&apos;ll find matching engineering providers.
            Accepted: PDF, DOCX, DWG, STEP, IGES, SolidWorks, CATIA, STL &mdash; up to {MAX_FILE_SIZE_MB} MB each.
          </p>
        </div>

        {/* Drop zone */}
        <div
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          onClick={() => selectedFiles.length < MAX_FILES && fileInputRef.current?.click()}
          className={[
            'relative rounded-xl border-2 border-dashed transition-all duration-200',
            selectedFiles.length >= MAX_FILES ? 'cursor-not-allowed opacity-60' : 'cursor-pointer',
            isDragOver ? 'border-blue-500 bg-blue-50' :
            selectedFiles.length > 0 ? 'border-slate-300 bg-slate-50/50' :
            'border-muted-foreground/25 hover:border-blue-400 hover:bg-blue-50/30',
          ].join(' ')}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept={ACCEPTED_EXTENSIONS.join(',')}
            className="sr-only"
            onChange={handleInputChange}
            multiple
          />
          <div className="flex flex-col items-center justify-center gap-3 px-6 py-10 text-center">
            <FileText className="h-10 w-10 text-muted-foreground/40" />
            <div>
              <p className="font-medium text-sm text-foreground">
                {isDragOver ? 'Drop your files here' : selectedFiles.length > 0 ? 'Drop more files or click to add' : 'Drag & drop your files here'}
              </p>
              <p className="text-xs text-muted-foreground mt-1">or <span className="text-blue-600 underline underline-offset-2">browse to upload</span></p>
            </div>
            <div className="flex gap-2 flex-wrap justify-center mt-1">
              {['PDF', 'DOCX', 'DWG', 'STEP', 'IGES', 'SolidWorks', 'STL'].map((fmt) => (
                <span key={fmt} className="inline-block rounded px-2 py-0.5 text-xs font-medium bg-muted text-muted-foreground border">{fmt}</span>
              ))}
            </div>
            <p className="text-xs text-muted-foreground">Up to {MAX_FILES} files, {MAX_FILE_SIZE_MB} MB each</p>
          </div>
        </div>

        {/* File list */}
        {selectedFiles.length > 0 && (
          <div className="mt-4 space-y-2">
            <div className="flex items-center justify-between">
              <p className="text-sm text-muted-foreground">
                {selectedFiles.length} file{selectedFiles.length > 1 ? 's' : ''} selected
                {docCount > 0 && cadCount > 0 && (
                  <span className="ml-1">({docCount} document{docCount > 1 ? 's' : ''}, {cadCount} CAD file{cadCount > 1 ? 's' : ''})</span>
                )}
              </p>
              <button type="button" onClick={handleClearAll} className="text-xs text-muted-foreground hover:text-foreground transition-colors underline">
                Clear all
              </button>
            </div>
            {selectedFiles.map((file, index) => (
              <div key={`${file.name}-${index}`} className="flex items-center gap-3 px-4 py-3 rounded-lg border border-slate-200 bg-white">
                <span className="text-2xl">{getFileIcon(file)}</span>
                <div className="flex-1 min-w-0">
                  <p className="font-medium text-sm text-foreground truncate">{file.name}</p>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    {formatFileSize(file.size)}
                    <span className="ml-2 px-1.5 py-0.5 rounded text-xs bg-slate-100 text-slate-600">{getFileCategory(file)}</span>
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => removeFile(index)}
                  className="shrink-0 rounded-full p-1 hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
                  aria-label="Remove file"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            ))}
          </div>
        )}

        {fileError && (
          <div className="mt-3 flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2.5">
            <AlertTriangle className="h-4 w-4 text-destructive mt-0.5 shrink-0" />
            <p className="text-xs text-destructive">{fileError}</p>
          </div>
        )}

        <div className="mt-6 flex flex-col sm:flex-row gap-3 justify-center">
          {selectedFiles.length > 0 && (
            <Button onClick={handleFindProviders} disabled={isSubmitting} className="bg-blue-600 hover:bg-blue-700 text-white font-semibold px-8" size="lg">
              {isSubmitting ? (
                <>
                  <svg className="animate-spin -ml-1 mr-2 h-4 w-4 text-white" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
                  </svg>
                  Analyzing with AI&hellip;
                </>
              ) : (
                `Find Providers${selectedFiles.length > 1 ? ` (${selectedFiles.length} files)` : ''}`
              )}
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
          Tip: Upload your scope of work alongside CAD files (STEP, DWG) for the most accurate matches.
          Include project specifications, required tolerances, materials, or relevant engineering standards.
        </p>
      </main>
    </div>
  );
}
