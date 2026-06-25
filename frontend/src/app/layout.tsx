import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import { Navbar } from "@/components/layout/Navbar";
import { Footer } from "@/components/layout/Footer";
import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
  display: "swap",
  weight: ["300", "400", "500", "600", "700", "800", "900"],
});

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-jetbrains",
  subsets: ["latin"],
  display: "swap",
  weight: ["400", "500", "600", "700"],
});

export const metadata: Metadata = {
  title: "HarveySpecter | AI-Powered Companies Act 2013 Compliance",
  description:
    "AI-powered legal compliance tool for Chartered Accountants and Company Secretaries in India. Analyze documents against the Companies Act 2013 with exact section, page, and line references.",
  keywords: [
    "Companies Act 2013",
    "legal compliance",
    "chartered accountant",
    "company secretary",
    "AI compliance",
    "India",
    "document analysis",
  ],
  authors: [{ name: "HarveySpecter" }],
  openGraph: {
    title: "HarveySpecter | AI-Powered Companies Act 2013 Compliance",
    description:
      "Analyze documents against the Companies Act 2013 with exact section, page, and line references.",
    type: "website",
    siteName: "HarveySpecter",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${inter.variable} ${jetbrainsMono.variable}`}
      data-theme="dark"
    >
      <body>
        <Navbar />
        <main>{children}</main>
        <Footer />
      </body>
    </html>
  );
}
