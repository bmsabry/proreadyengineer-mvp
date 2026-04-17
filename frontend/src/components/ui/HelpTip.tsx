"use client";

/**
 * HelpTip — a tiny `?` icon that opens a popover with short help text.
 *
 * Usage:
 *   <HelpTip id="rfq.tollgate" />          // looks up text from help-registry.ts
 *   <HelpTip title="..." body="..." />     // inline override
 *
 * - Click or hover to open (mobile-friendly: tap toggles)
 * - Closes on outside click or Escape
 * - Optional "Learn more" link to /help#anchor
 */

import { useEffect, useRef, useState } from "react";
import { getHelp, HelpEntry } from "@/lib/help-registry";

type Props = {
  id?: string;
  title?: string;
  body?: string;
  learnMore?: string;
  className?: string;
  /** Size of the icon in px (default 16) */
  size?: number;
};

export default function HelpTip({
  id,
  title,
  body,
  learnMore,
  className = "",
  size = 16,
}: Props) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLSpanElement | null>(null);

  const entry: HelpEntry | null = id ? getHelp(id) : null;
  const effTitle = title ?? entry?.title ?? "Help";
  const effBody = body ?? entry?.body ?? "";
  const effLearn = learnMore ?? entry?.learnMore;

  useEffect(() => {
    if (!open) return;
    function onDocClick(e: MouseEvent) {
      if (!wrapRef.current) return;
      if (!wrapRef.current.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  if (!effBody) {
    // Registry miss — render nothing rather than a broken icon.
    return null;
  }

  return (
    <span
      ref={wrapRef}
      className={`relative inline-flex align-middle ${className}`}
    >
      <button
        type="button"
        aria-label={`Help: ${effTitle}`}
        aria-expanded={open}
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          setOpen((v) => !v);
        }}
        onMouseEnter={() => setOpen(true)}
        onFocus={() => setOpen(true)}
        onBlur={(e) => {
          // Only close on blur if focus is leaving the wrapper entirely
          if (
            wrapRef.current &&
            !wrapRef.current.contains(e.relatedTarget as Node)
          ) {
            setOpen(false);
          }
        }}
        className="inline-flex items-center justify-center rounded-full border border-slate-300 bg-slate-50 text-slate-600 hover:bg-slate-100 hover:text-slate-800 focus:outline-none focus:ring-2 focus:ring-emerald-500 cursor-help"
        style={{ width: size, height: size, fontSize: Math.round(size * 0.7) }}
      >
        <span aria-hidden="true" className="font-semibold leading-none">?</span>
      </button>
      {open && (
        <span
          role="tooltip"
          className="absolute z-50 left-1/2 -translate-x-1/2 top-full mt-2 w-64 rounded-lg border border-slate-200 bg-white p-3 text-left shadow-lg"
          // Keep focus inside while interacting with the Learn more link
          onMouseLeave={() => setOpen(false)}
        >
          <span className="block text-[13px] font-semibold text-slate-900">
            {effTitle}
          </span>
          <span className="mt-1 block text-[12px] leading-snug text-slate-600">
            {effBody}
          </span>
          {effLearn && (
            <a
              href={effLearn}
              target="_blank"
              rel="noreferrer"
              className="mt-2 inline-block text-[12px] font-medium text-emerald-700 hover:text-emerald-800 hover:underline"
              onClick={(e) => e.stopPropagation()}
            >
              Learn more →
            </a>
          )}
        </span>
      )}
    </span>
  );
}
