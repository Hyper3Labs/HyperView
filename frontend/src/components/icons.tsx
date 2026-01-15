"use client";

/**
 * Shared icons for HyperView UI.
 * Using inline SVGs for simplicity (no extra icon library dependency).
 */

export const GridIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-4 h-4">
    <rect x="3" y="3" width="7" height="7" />
    <rect x="14" y="3" width="7" height="7" />
    <rect x="3" y="14" width="7" height="7" />
    <rect x="14" y="14" width="7" height="7" />
  </svg>
);

export const ScatterIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-4 h-4">
    <circle cx="8" cy="8" r="2" />
    <circle cx="16" cy="16" r="2" />
    <circle cx="18" cy="8" r="2" />
    <circle cx="6" cy="16" r="2" />
    <circle cx="12" cy="12" r="2" />
  </svg>
);

export const HyperViewLogo = () => (
  <svg viewBox="0 0 24 24" fill="none" className="w-5 h-5">
    <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="1.5" />
    <circle cx="12" cy="12" r="6" stroke="currentColor" strokeWidth="1.5" opacity="0.6" />
    <circle cx="12" cy="12" r="2" fill="currentColor" />
  </svg>
);

export const CheckIcon = () => (
  <svg className="w-3 h-3 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
  </svg>
);
