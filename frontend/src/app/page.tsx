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

      if (data.status !== "done" && data.status !== "error" && data.status !== "selection") {
        setTimeout(() => pollStatus(benchmarkId), 4000);
      } else {
        setLoading(false);
      }
    } catch (e: any) {
      console.error("Erreur polling:", e.message);
      setTimeout(() => pollStatus(benchmarkId), 6000);
    }
  }, []);

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

  const isDiscovering = benchmark && ["discovering", "pending"].includes(benchmark.status);
  const isSelecting = benchmark && benchmark.status === "selection" && benchmark.candidates?.length > 0;
  const isCollecting = benchmark && ["collecting", "criteria", "selecting"].includes(benchmark.status) && !isDiscovering;
  const isDone = benchmark && benchmark.status === "done";
  const isError = benchmark && benchmark.status === "error";

  return (
    <div className="min-h-screen">
      {/* Header */}
      <header className="border-b border-surface-200 bg-brand-500 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-6 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            {/* Logo */}
            <img
              src="/logo.png"
              alt="PCA"
              className="w-10 h-10 rounded-full"
            />
            <div>
              <h1
                className="font-bold text-lg text-white tracking-wide"
                style={{ fontFamily: "Georgia, 'Times New Roman', serif" }}
              >
                PCA
              </h1>
              <p className="text-[11px] text-brand-200 tracking-wider uppercase">
                Product Conception Assistant
              </p>
            </div>
          </div>
          {benchmark && (
            <button
              onClick={handleReset}
              className="inline-flex items-center px-4 py-2 bg-white/10 text-white text-sm 
                         font-medium rounded-lg hover:bg-white/20 transition-colors border border-white/20"
            >
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
              <h2
                className="font-bold text-4xl text-brand-500 mb-3 tracking-tight"
                style={{ fontFamily: "Georgia, 'Times New Roman', serif" }}
              >
                Benchmark Produits
              </h2>
              <p className="text-surface-500 text-lg">
                Tapez un type de produit. L&apos;IA recherche les candidats, vous sélectionnez, puis la deep research commence.
              </p>
            </div>
            <SearchForm onSubmit={handleSubmit} />
          </div>
        )}

        {/* Erreur */}
        {error && (
          <div className="max-w-2xl mx-auto mt-6 p-4 bg-accent-50 border border-accent-200 rounded-xl text-accent-700">
            <p className="font-medium">Erreur</p>
            <p className="text-sm mt-1">{error}</p>
          </div>
        )}

        {/* Découverte en cours */}
        {isDiscovering && (
          <div className="max-w-2xl mx-auto pt-12">
            <ProgressBar
              percent={benchmark!.progress_percent}
              message={benchmark!.progress_message}
              productType={benchmark!.product_type}
            />
          </div>
        )}

        {/* Sélection des produits */}
        {isSelecting && (
          <div className="pt-4">
            <ProductSelector
              candidates={benchmark!.candidates}
              onLaunch={handleLaunchBenchmark}
              productType={benchmark!.product_type}
            />
          </div>
        )}

        {/* Deep research en cours */}
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
              <div className="w-16 h-16 bg-accent-50 rounded-full flex items-center justify-center mx-auto mb-4">
                <svg className="w-8 h-8 text-accent-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
              <h3
                className="font-bold text-xl mb-2 text-brand-500"
                style={{ fontFamily: "Georgia, 'Times New Roman', serif" }}
              >
                Une erreur est survenue
              </h3>
              <p className="text-surface-500 mb-6">{benchmark!.progress_message}</p>
              <button onClick={handleReset} className="btn-primary">Réessayer</button>
            </div>
          </div>
        )}

        {/* Résultats */}
        {isDone && (
          <div>
            <div className="mb-8">
              <h2
                className="font-bold text-2xl text-brand-500 mb-1"
                style={{ fontFamily: "Georgia, 'Times New Roman', serif" }}
              >
                Benchmark : {benchmark!.product_type}
              </h2>
              <p className="text-surface-500">
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

      {/* Footer */}
      <footer className="border-t border-surface-200 bg-brand-500 mt-16">
        <div className="max-w-7xl mx-auto px-6 py-6 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <img src="/logo.png" alt="PCA" className="w-6 h-6 rounded-full opacity-80" />
            <span
              className="text-sm text-white/80"
              style={{ fontFamily: "Georgia, 'Times New Roman', serif" }}
            >
              PCA — Product Conception Assistant
            </span>
          </div>
          <span className="text-xs text-white/50">v2.0</span>
        </div>
      </footer>
    </div>
  );
}
