"use client";
import { useAsset } from "@/lib/asset";
import { Notice } from "./ui";

export default function RequireAsset({ children }: { children: (a: { ticker: string; series: string }) => React.ReactNode }) {
  const { asset } = useAsset();
  if (!asset) return <Notice tone="warn">Seleccione una emisora y serie en el selector superior. Si el catálogo está vacío, impórtelo en «Emisoras».</Notice>;
  return <>{children(asset)}</>;
}
