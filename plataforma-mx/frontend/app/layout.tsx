import "./globals.css";
import type { Metadata } from "next";
import Shell from "@/components/Shell";
import { AssetProvider } from "@/lib/asset";

export const metadata: Metadata = {
  title: "Plataforma MX — Análisis y coberturas",
  description: "Análisis financiero, valuación, derivados y estrategias de cobertura para el mercado mexicano.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es-MX" suppressHydrationWarning>
      <body>
        <AssetProvider>
          <Shell>{children}</Shell>
        </AssetProvider>
      </body>
    </html>
  );
}
