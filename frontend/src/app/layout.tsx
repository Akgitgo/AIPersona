import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

const personaName = process.env.NEXT_PUBLIC_PERSONA_NAME || "AI Persona";

export const metadata: Metadata = {
  title: `${personaName} — AI Representative`,
  description: `Chat with ${personaName}'s AI representative. Ask about their background, experience, and schedule an interview.`,
  openGraph: {
    title: `${personaName} — AI Representative`,
    description: `Ask me anything about ${personaName}'s background, skills, and projects.`,
    type: "website",
  },
  robots: { index: false, follow: false },   // don't index during eval period
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#0a0a0f",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className={`${geistSans.variable} ${geistMono.variable} antialiased`}>
        {children}
      </body>
    </html>
  );
}
