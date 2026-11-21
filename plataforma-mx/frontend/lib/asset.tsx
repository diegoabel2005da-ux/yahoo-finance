"use client";
import { createContext, useContext, useEffect, useState } from "react";

export type Asset = { ticker: string; series: string; issuer_name?: string } | null;
const Ctx = createContext<{ asset: Asset; setAsset: (a: Asset) => void }>({ asset: null, setAsset: () => {} });

export function AssetProvider({ children }: { children: React.ReactNode }) {
  const [asset, setA] = useState<Asset>(null);
  useEffect(() => {
    try {
      const raw = localStorage.getItem("asset");
      if (raw) setA(JSON.parse(raw));
    } catch {}
  }, []);
  const setAsset = (a: Asset) => {
    setA(a);
    try {
      localStorage.setItem("asset", JSON.stringify(a));
    } catch {}
  };
  return <Ctx.Provider value={{ asset, setAsset }}>{children}</Ctx.Provider>;
}
export const useAsset = () => useContext(Ctx);
