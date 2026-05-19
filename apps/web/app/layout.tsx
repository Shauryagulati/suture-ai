import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Suture",
  description: "AI command center for cardiology practices",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}): React.ReactElement {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>{children}</body>
    </html>
  );
}
