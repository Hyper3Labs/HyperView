import Link from 'next/link';
import type { ReactNode } from 'react';

export default function Layout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="border-b border-border bg-surface">
        <div className="container mx-auto px-4 py-4 flex items-center justify-between">
          <Link href="/" className="text-xl font-bold text-primary hover:text-primary-light">
            HyperView
          </Link>
          <nav className="flex gap-6">
            <Link href="/docs" className="text-text-muted hover:text-text">
              Documentation
            </Link>
            <a 
              href="https://github.com/HackerRoomAI/HyperView" 
              target="_blank"
              rel="noopener noreferrer"
              className="text-text-muted hover:text-text"
            >
              GitHub
            </a>
          </nav>
        </div>
      </header>

      <div className="container mx-auto px-4 py-8 flex gap-8">
        {/* Sidebar */}
        <aside className="w-64 flex-shrink-0">
          <nav className="sticky top-8 space-y-1">
            <Link 
              href="/docs" 
              className="block px-3 py-2 rounded text-text-muted hover:text-text hover:bg-surface-light"
            >
              Welcome
            </Link>
            <Link 
              href="/docs/getting-started" 
              className="block px-3 py-2 rounded text-text-muted hover:text-text hover:bg-surface-light"
            >
              Getting Started
            </Link>
            <Link 
              href="/docs/architecture" 
              className="block px-3 py-2 rounded text-text-muted hover:text-text hover:bg-surface-light"
            >
              Architecture
            </Link>
            <Link 
              href="/docs/datasets" 
              className="block px-3 py-2 rounded text-text-muted hover:text-text hover:bg-surface-light"
            >
              Datasets
            </Link>
            <Link 
              href="/docs/api-reference" 
              className="block px-3 py-2 rounded text-text-muted hover:text-text hover:bg-surface-light"
            >
              API Reference
            </Link>
          </nav>
        </aside>

        {/* Main content */}
        <main className="flex-1 max-w-4xl">
          <article className="prose prose-invert prose-slate max-w-none">
            {children}
          </article>
        </main>
      </div>
    </div>
  );
}
