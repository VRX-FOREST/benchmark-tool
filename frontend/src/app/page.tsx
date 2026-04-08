"use client";

import { useState, useCallback } from "react";
import SearchForm from "@/components/SearchForm";
import ProgressBar from "@/components/ProgressBar";
import ProductSelector from "@/components/ProductSelector";
import ProductTable from "@/components/ProductTable";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface Benchmark {
  id: string;
  product_type: string;
  status: string;
  progress_message: string;
  progress_percent: number;
  criteria: any[];
  products: any[];
  candidates: any[];
}

export default function Home() {
  const [benchmark, setBenchmark] = useState<Benchmark | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const pollStatus = useCallback(async (benchmarkId: string) => {
    try {
      const res = await fetch(`${API_URL}/api/benchmarks/${benchmarkId}`);
      if (!res.ok) throw new Error("Erreur serveur");
      const data = await res.json();
      setBenchmark(data);

      // Continuer le polling si pas terminé et pas en attente de sélection
      if (data.status !== "done" && data.status !== "error" && data.status !== "selection") {
        setTimeout(() => pollStatus(benchmarkId), 4000);
      } else {
        setLoading(false);
      }
    } catch (e: any) {
      // Ne pas arrêter sur une erreur réseau temporaire
      console.error("Erreur polling:", e.message);
      setTimeout(() => pollStatus(benchmarkId), 6000);
    }
  }, []);

  // Phase 1 : Lancer la découverte des produits
  const handleSubmit = async (formData: any) => {
    setLoading(true);
    setError("");
    setBenchmark(null);

    try {
      const res = await fetch(`${API_URL}/api/benchmarks/discover`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(formData),
      });

      if (!res.ok) throw new Error("Erreur lors du lancement");
      const data = await res.json();

      setBenchmark({
        id: data.id,
        product_type: formData.product_type,
        status: "discovering",
        progress_message: "Recherche des produits candidats...",
        progress_percent: 0,
        criteria: [],
        products: [],
        candidates: [],
      });

      setTimeout(() => pollStatus(data.id), 3000);
    } catch (e: any) {
      setError(e.message);
      setLoading(false);
    }
  };

  // Phase 2 : Lancer le benchmark sur les produits sélectionnés
  const handleLaunchBenchmark = async (selectedProducts: any[]) => {
    if (!benchmark) return;
    setLoading(true);
    setError("");

    try {
      const res = await fetch(`${API_URL}/api/benchmarks/launch`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          benchmark_id: benchmark.id,
          selected_products: selectedProducts.map((p) => ({
            name: p.name,
            brand: p.brand,
            image_url: p.image_url,
            source_url: p.source_url,
            estimated_price: p.estimated_price,
          })),
        }),
      });

      if (!res.ok) throw new Error("Erreur lors du lancement du benchmark");

      setBenchmark((prev) =>
        prev
          ? {
              ...prev,
              status: "collecting",
              progress_message: "Deep research en cours...",
              progress_percent: 0,
              candidates: [],
            }
          : null
      );

      setTimeout(() => pollStatus(benchmark.id), 3000);
    } catch (e: any) {
      setError(e.message);
      setLoading(false);
    }
  };

  const handleReset = () => {
    setBenchmark(null);
    setLoading(false);
    setError("");
  };

  // Déterminer l'état de l'interface
  const isDiscovering = benchmark && ["discovering", "pending"].includes(benchmark.status);
  const isSelecting = benchmark && benchmark.status === "selection" && benchmark.candidates?.length > 0;
  const isCollecting = benchmark && ["collecting", "criteria", "selecting"].includes(benchmark.status) && !isDiscovering;
  const isDone = benchmark && benchmark.status === "done";
  const isError = benchmark && benchmark.status === "error";

  return (
    <div className="min-h-screen">
      {/* Header */}
      <header className="border-b border-surface-200 bg-surface-0/80 backdrop-blur-md sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-brand-600 rounded-xl flex items-center justify-center">
              <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M3 6l3 1m0 0l-3 9a5.002 5.002 0 006.001 0M6 7l3 9M6 7l6-2m6 2l3-1m-3 1l-3 9a5.002 5.002 0 006.001 0M18 7l3 9m-3-9l-6-2m0-2v2m0 16V5m0 16H9m3 0h3" />
              </svg>
            </div>
            <div>
              <h1 className="font-display font-bold text-lg text-surface-900 tracking-tight">
                Benchmark Produits
              </h1>
              <p className="text-xs text-surface-500">Comparateur intelligent V2</p>
            </div>
          </div>
          {benchmark && (
            <button onClick={handleReset} className="btn-secondary text-sm">
              Nouveau benchmark
            </button>
          )}
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-8">
        {/* Formulaire de recherche */}
        {!benchmark && !loading && (
          <div className="max-w-2xl mx-auto pt-12">
            <div className="text-center mb-10">
              <h2 className="font-display font-bold text-4xl text-surface-900 mb-3 tracking-tight">
                Comparez n&apos;importe quel produit
              </h2>
              <p className="text-surface-600 text-lg">
                Tapez un type de produit. L&apos;IA recherche les candidats, vous sélectionnez, puis la deep research commence.
              </p>
            </div>
            <SearchForm onSubmit={handleSubmit} />
          </div>
        )}

        {/* Erreur */}
        {error && (
          <div className="max-w-2xl mx-auto mt-6 p-4 bg-red-50 border border-red-200 rounded-xl text-red-700">
            <p className="font-medium">Erreur</p>
            <p className="text-sm mt-1">{error}</p>
          </div>
        )}

        {/* Phase 1 : Découverte en cours */}
        {isDiscovering && (
          <div className="max-w-2xl mx-auto pt-12">
            <ProgressBar
              percent={benchmark!.progress_percent}
              message={benchmark!.progress_message}
              productType={benchmark!.product_type}
            />
          </div>
        )}

        {/* Phase 2 : Sélection des produits */}
        {isSelecting && (
          <div className="pt-4">
            <ProductSelector
              candidates={benchmark!.candidates}
              onLaunch={handleLaunchBenchmark}
              productType={benchmark!.product_type}
            />
          </div>
        )}

        {/* Phase 3 : Deep research en cours */}
        {isCollecting && !isDiscovering && (
          <div className="max-w-2xl mx-auto pt-12">
            <ProgressBar
              percent={benchmark!.progress_percent}
              message={benchmark!.progress_message}
              productType={benchmark!.product_type}
            />
          </div>
        )}

        {/* Erreur benchmark */}
        {isError && (
          <div className="max-w-2xl mx-auto pt-12">
            <div className="card p-8 text-center">
              <div className="w-16 h-16 bg-red-100 rounded-full flex items-center justify-center mx-auto mb-4">
                <svg className="w-8 h-8 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
              <h3 className="font-display font-bold text-xl mb-2">Une erreur est survenue</h3>
              <p className="text-surface-600 mb-6">{benchmark!.progress_message}</p>
              <button onClick={handleReset} className="btn-primary">Réessayer</button>
            </div>
          </div>
        )}

        {/* Résultats */}
        {isDone && (
          <div>
            <div className="mb-8">
              <h2 className="font-display font-bold text-2xl text-surface-900 mb-1">
                Benchmark : {benchmark!.product_type}
              </h2>
              <p className="text-surface-600">
                {benchmark!.products?.length || 0} produits comparés —{" "}
                {benchmark!.criteria?.reduce((acc: number, cat: any) => acc + (cat.fields?.length || 0), 0) || 0} critères analysés
              </p>
            </div>
            <ProductTable
              products={benchmark!.products || []}
              criteria={benchmark!.criteria || []}
            />
          </div>
        )}
      </main>
    </div>
  );
}
