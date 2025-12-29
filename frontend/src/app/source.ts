import { docs, meta } from '../../.source/server';

// Simple wrapper to match the expected API
export const source = {
  getPage(slug?: string[]) {
    const path = slug?.join('/') || 'index';
    const doc = docs.find((d: any) => d.path === path);
    if (!doc) return null;
    
    return {
      data: {
        title: (doc as any).title,
        description: (doc as any).description,
        body: (doc as any).body,
      },
      url: `/docs/${path}`,
    };
  },
  
  generateParams() {
    return docs.map((doc: any) => {
      const path = doc.path || 'index';
      console.log('Doc path:', path, 'Type:', typeof path);
      if (path === 'index') {
        return { slug: [] };
      }
      return {
        slug: path.split('/'),
      };
    });
  },
};

export const pageTree = docs;
