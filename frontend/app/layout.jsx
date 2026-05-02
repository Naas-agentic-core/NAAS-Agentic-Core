import "./globals.css";
import "./legacy-style.css";
import 'katex/dist/katex.min.css';

export const metadata = {
  title: "CogniForge Next Gateway",
  description: "Next.js shell for the CogniForge legacy UI."
};

export default function RootLayout({ children }) {
  return (
    <html lang="ar" dir="rtl" suppressHydrationWarning>
      <body suppressHydrationWarning>{children}</body>
    </html>
  );
}
