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

export const HyperViewLogo = ({ className = "w-5 h-5" }: { className?: string }) => (
  <svg viewBox="0 0 24 24" fill="none" className={className}>
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

/** Euclidean geometry icon - flat grid */
export const EuclideanIcon = () => (
  <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.25" className="w-3.5 h-3.5">
    <rect x="2" y="2" width="12" height="12" rx="1" />
    <line x1="2" y1="8" x2="14" y2="8" />
    <line x1="8" y1="2" x2="8" y2="14" />
  </svg>
);

/** Poincaré disk icon - hyperbolic geometry */
export const PoincareIcon = () => (
  <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.25" className="w-3.5 h-3.5">
    <circle cx="8" cy="8" r="6" />
    <ellipse cx="8" cy="8" rx="3" ry="5.5" />
    <ellipse cx="8" cy="8" rx="5.5" ry="3" />
  </svg>
);

/** Spherical geometry icon - for future use */
export const SphericalIcon = () => (
  <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.25" className="w-3.5 h-3.5">
    <circle cx="8" cy="8" r="6" />
    <ellipse cx="8" cy="8" rx="6" ry="2.5" />
    <path d="M8 2 Q12 8 8 14" />
  </svg>
);

/** Discord icon - official simplified logo */
export const DiscordIcon = ({ className = "w-4 h-4" }: { className?: string }) => (
  <svg viewBox="0 0 24 24" fill="currentColor" className={className}>
    <path d="M19.27 5.33C17.94 4.71 16.5 4.26 15 4a.09.09 0 0 0-.07.03c-.18.33-.39.76-.53 1.09a16.09 16.09 0 0 0-4.8 0c-.14-.34-.35-.76-.54-1.09c-.01-.02-.04-.03-.07-.03c-1.5.26-2.93.71-4.27 1.33c-.01 0-.02.01-.03.02c-2.72 4.07-3.47 8.03-3.1 11.95c0 .02.01.04.03.05c1.8 1.32 3.53 2.12 5.24 2.65c.03.01.06 0 .07-.02c.4-.55.76-1.13 1.07-1.74c.02-.04 0-.08-.04-.09c-.57-.22-1.11-.48-1.64-.78c-.04-.02-.04-.08-.01-.11c.11-.08.22-.17.33-.25c.02-.02.05-.02.07-.01c3.44 1.57 7.15 1.57 10.55 0c.02-.01.05-.01.07.01c.11.09.22.17.33.26c.04.03.04.09-.01.11c-.52.31-1.07.56-1.64.78c-.04.01-.05.06-.04.09c.32.61.68 1.19 1.07 1.74c.03.01.06.02.09.01c1.72-.53 3.45-1.33 5.25-2.65c.02-.01.03-.03.03-.05c.44-4.53-.73-8.46-3.1-11.95c-.01-.01-.02-.02-.04-.02zM8.52 14.91c-1.03 0-1.89-.95-1.89-2.12s.84-2.12 1.89-2.12c1.06 0 1.9.96 1.89 2.12c0 1.17-.84 2.12-1.89 2.12zm6.97 0c-1.03 0-1.89-.95-1.89-2.12s.84-2.12 1.89-2.12c1.06 0 1.9.96 1.89 2.12c0 1.17-.83 2.12-1.89 2.12z"/>
  </svg>
);
