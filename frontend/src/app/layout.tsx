import type { Metadata } from "next";
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
    <html lang="en" className="h-full">
      <body className="antialiased h-full">{children}</body>
    </html>
  );
}
