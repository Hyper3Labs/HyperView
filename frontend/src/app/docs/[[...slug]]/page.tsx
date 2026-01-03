import { source } from '@/app/source';
import type { Metadata } from 'next';
import { notFound } from 'next/navigation';

export default async function Page(props: {
  params: Promise<{ slug?: string[] }>;
}) {
  const params = await props.params;
  const page = source.getPage(params.slug);
  if (!page) notFound();

  const MDX = page.data.body;

  return (
    <div className="prose prose-invert max-w-none">
      <div className="not-prose mb-8">
        <h1 className="text-4xl md:text-5xl font-bold text-text mb-4 leading-tight">
          {page.data.title}
        </h1>
        {page.data.description && (
          <p className="text-lg md:text-xl text-text-muted leading-relaxed">
            {page.data.description}
          </p>
        )}
      </div>
      <MDX />
    </div>
  );
}

export async function generateStaticParams() {
  return source.generateParams();
}

export async function generateMetadata(props: {
  params: Promise<{ slug?: string[] }>;
}): Promise<Metadata> {
  const params = await props.params;
  const page = source.getPage(params.slug);
  if (!page) notFound();

  return {
    title: page.data.title,
    description: page.data.description,
  };
}
