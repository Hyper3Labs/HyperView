"use client";

/**
 * Shared icons for HyperView UI.
 * Using inline SVGs for simplicity (no extra icon library dependency).
 */

export const HyperViewLogo = ({ className = "w-5 h-5" }: { className?: string }) => (
  <svg viewBox="0 0 32 32" fill="none" className={className} aria-hidden="true">
    <circle cx="16" cy="16" r="11" stroke="currentColor" strokeWidth="1.75" />
    <path
      d="M11.3 6.25C14.1 11.9 14.1 20.1 11.3 25.75"
      stroke="currentColor"
      strokeWidth="1.9"
      strokeLinecap="round"
    />
    <path
      d="M20.7 6.25C17.9 11.9 17.9 20.1 20.7 25.75"
      stroke="currentColor"
      strokeWidth="1.9"
      strokeLinecap="round"
    />
    <path
      d="M5.4 16H26.6"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
    />
    <circle cx="16" cy="16" r="2.15" fill="currentColor" />
  </svg>
);

export const CheckIcon = () => (
  <svg className="w-3 h-3 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
  </svg>
);
