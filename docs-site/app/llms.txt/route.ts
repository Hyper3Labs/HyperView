import { source } from '@/lib/source';

export const revalidate = false;

export async function GET() {
  const pages = source.getPages();
  
  const entries = pages.map((page) => {
    return `- [${page.data.title}](${page.url}): ${page.data.description || 'Documentation page'}`;
  });

  const content = `# HyperView Documentation
> Open-source dataset curation with hyperbolic embeddings visualization

## Documentation

${entries.join('\n')}

## Links
- GitHub: https://github.com/HackerRoomAI/HyperView
- Full Documentation: /llms-full.txt

Last updated: ${new Date().toISOString().split('T')[0]}
`;

  return new Response(content, {
    headers: {
      'Content-Type': 'text/plain; charset=utf-8',
    },
  });
}

