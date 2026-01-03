import type { Metadata } from "next";
import { RootProvider } from 'fumadocs-ui/provider';
import "./globals.css";

export const metadata: Metadata = {
  title: "HyperView",
  description: "Dataset visualization with hyperbolic embeddings",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="antialiased">
        <RootProvider>
          {children}
        </RootProvider>
      </body>
    </html>
  );
}
