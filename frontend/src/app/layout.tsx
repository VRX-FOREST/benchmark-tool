import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Benchmark Produits — Comparateur intelligent",
  description: "Générez automatiquement un tableau comparatif fiable et exhaustif pour n'importe quel type de produit.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr">
      <body>{children}</body>
    </html>
  );
}
