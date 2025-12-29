import { docs, meta } from '../../.source/server';

// Type definition for fumadocs-mdx doc entry
interface DocEntry {
  title: string;
  description?: string;
  body: React.ComponentType;
  info?: {
    path: string;
    fullPath: string;
  };
}

// Simple wrapper to match the expected API
export const source = {
  getPage(slug?: string[]) {
    const path = slug?.join('/') || 'index';
    const doc = docs.find((d: unknown) => {
      const entry = d as DocEntry;
      const filePath = entry.info?.path || '';
      const fileName = filePath.replace(/\.mdx?$/, '');
      return fileName === path;
    });
    if (!doc) return null;
    
    const entry = doc as DocEntry;
    return {
      data: {
        title: entry.title,
        description: entry.description,
        body: entry.body,
      },
      url: `/docs/${path}`,
    };
  },
  
  generateParams() {
    return docs.map((doc: unknown) => {
      const entry = doc as DocEntry;
      const filePath = entry.info?.path || '';
      const fileName = filePath.replace(/\.mdx?$/, '');
      
      if (fileName === 'index') {
        return { slug: [] };
      }
      return {
        slug: fileName.split('/'),
      };
    });
  },
};

export const pageTree = docs;
