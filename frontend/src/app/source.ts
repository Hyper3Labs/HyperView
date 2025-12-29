import { docs, meta } from '../../.source/server';

// Simple wrapper to match the expected API
export const source = {
  getPage(slug?: string[]) {
    const path = slug?.join('/') || 'index';
    const doc = docs.find((d: any) => {
      const filePath = d.info?.path || '';
      const fileName = filePath.replace(/\.mdx?$/, '');
      return fileName === path;
    });
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
      const filePath = doc.info?.path || '';
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
