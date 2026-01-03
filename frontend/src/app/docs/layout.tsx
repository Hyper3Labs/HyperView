import Link from 'next/link';
import type { ReactNode } from 'react';

export default function Layout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="sticky top-0 z-50 w-full border-b border-border bg-surface/95 backdrop-blur supports-[backdrop-filter]:bg-surface/60">
        <div className="container mx-auto flex h-16 items-center px-4">
          <Link href="/" className="flex items-center space-x-2 mr-6">
            <span className="text-xl font-bold bg-gradient-to-r from-primary to-primary-light bg-clip-text text-transparent">
              HyperView
            </span>
          </Link>
          <nav className="flex items-center space-x-6 text-sm font-medium ml-auto">
            <Link href="/docs" className="text-text-muted hover:text-text transition-colors">
              Documentation
            </Link>
            <a 
              href="https://github.com/HackerRoomAI/HyperView" 
              target="_blank"
              rel="noopener noreferrer"
              className="text-text-muted hover:text-text transition-colors"
            >
              GitHub
            </a>
          </nav>
        </div>
      </header>

      <div className="container mx-auto px-4 py-8 flex gap-12 max-w-7xl">
        {/* Sidebar */}
        <aside className="w-64 flex-shrink-0 hidden md:block">
          <nav className="sticky top-24 space-y-1">
            <div className="pb-4">
              <p className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-3">
                Getting Started
              </p>
              <div className="space-y-1">
                <Link 
                  href="/docs" 
                  className="block px-3 py-2 rounded-md text-sm text-text-muted hover:text-text hover:bg-surface-light transition-colors"
                >
                  Welcome
                </Link>
                <Link 
                  href="/docs/getting-started" 
                  className="block px-3 py-2 rounded-md text-sm text-text-muted hover:text-text hover:bg-surface-light transition-colors"
                >
                  Getting Started
                </Link>
              </div>
            </div>
            
            <div className="pb-4 pt-4 border-t border-border">
              <p className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-3">
                Core Concepts
              </p>
              <div className="space-y-1">
                <Link 
                  href="/docs/architecture" 
                  className="block px-3 py-2 rounded-md text-sm text-text-muted hover:text-text hover:bg-surface-light transition-colors"
                >
                  Architecture
                </Link>
                <Link 
                  href="/docs/datasets" 
                  className="block px-3 py-2 rounded-md text-sm text-text-muted hover:text-text hover:bg-surface-light transition-colors"
                >
                  Datasets
                </Link>
              </div>
            </div>
            
            <div className="pb-4 pt-4 border-t border-border">
              <p className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-3">
                API
              </p>
              <div className="space-y-1">
                <Link 
                  href="/docs/api-reference" 
                  className="block px-3 py-2 rounded-md text-sm text-text-muted hover:text-text hover:bg-surface-light transition-colors"
                >
                  API Reference
                </Link>
              </div>
            </div>
          </nav>
        </aside>

        {/* Main content */}
        <main className="flex-1 min-w-0 max-w-4xl">
          <article className="pb-12">
            {children}
          </article>
        </main>
      </div>
    </div>
  );
}
