import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "PCA — Product Conception Assistant",
  description: "Benchmark intelligent de produits physiques. Comparez n'importe quel produit avec une analyse approfondie du marché.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr">
      <body>{children}</body>
    </html>
  );
}
