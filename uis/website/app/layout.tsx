import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Brasaland — Al Carbón · Desde 2008",
  description:
    "Grilled food restaurant chain with 14 locations across Colombia and Florida. Consistent food, warm service, fast kitchen — since 2008.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="bg-white text-stone-900 antialiased">{children}</body>
    </html>
  );
}
