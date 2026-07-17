import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "US Importer Hunter · Prospect Analysis",
  description:
    "Qualify US importers and prepare human-reviewed outreach drafts for freight forwarders.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
