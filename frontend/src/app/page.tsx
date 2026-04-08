"use client";

import { useState } from "react";

interface Candidate {
  id: string;
  name: string;
  brand: string;
  segment: string;
  estimated_price: number | null;
  why_selected: string;
  image_url: string;
  source_url: string;
  selected: boolean;
}

interface Props {
  candidates: Candidate[];
  onLaunch: (selected: Candidate[]) => void;
  productType: string;
}

export default function ProductSelector({ candidates, onLaunch, productType }: Props) {
  const [selection, setSelection] = useState<Record<string, boolean>>(() => {
    const initial: Record<string, boolean> = {};
    candidates.forEach((c) => (initial[c.id] = c.selected !== false));
    return initial;
  });

  const toggleProduct = (id: string) => {
    setSelection((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const selectAll = () => {
    const all: Record<string, boolean> = {};
    candidates.forEach((c) => (all[c.id] = true));
    setSelection(all);
  };

  const selectNone = () => {
    const none: Record<string, boolean> = {};
    candidates.forEach((c) => (none[c.id] = false));
    setSelection(none);
  };

  const selectedCount = Object.values(selection).filter(Boolean).length;

  const handleLaunch = () => {
    const selected = candidates.filter((c) => selection[c.id]);
    onLaunch(selected);
  };

  return (
    <div>
      {/* Header */}
      <div className="mb-6">
        <h2 className="font-display font-bold text-2xl text-surface-900 mb-1">
          Produits trouvés : {productType}
        </h2>
        <p className="text-surface-600">
          {candidates.length} produits identifiés — cochez ceux que vous souhaitez inclure dans le benchmark.
        </p>
      </div>

      {/* Contrôles de sélection */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex gap-2">
          <button onClick={selectAll} className="btn-secondary text-xs">
            Tout sélectionner
          </button>
          <button onClick={selectNone} className="btn-secondary text-xs">
            Tout désélectionner
          </button>
        </div>
        <span className="text-sm text-surface-600">
          {selectedCount} / {candidates.length} sélectionnés
        </span>
      </div>

      {/* Grille de produits */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-8">
        {candidates.map((candidate) => {
          const isSelected = selection[candidate.id];
          return (
            <div
              key={candidate.id}
              onClick={() => toggleProduct(candidate.id)}
              className={`card p-4 cursor-pointer transition-all duration-200
                ${isSelected
                  ? "ring-2 ring-brand-500 bg-brand-50/30"
                  : "opacity-60 hover:opacity-80"
                }`}
            >
              {/* Checkbox + Image */}
              <div className="flex gap-3 mb-3">
                <div className="flex-shrink-0 pt-0.5">
                  <div
                    className={`w-5 h-5 rounded-md border-2 flex items-center justify-center transition-all
                      ${isSelected
                        ? "bg-brand-600 border-brand-600"
                        : "border-surface-300 bg-surface-0"
                      }`}
                  >
                    {isSelected && (
                      <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                      </svg>
                    )}
                  </div>
                </div>

                <div className="w-16 h-16 rounded-lg bg-surface-100 overflow-hidden flex-shrink-0 border border-surface-200">
                  {candidate.image_url ? (
                    <img
                      src={candidate.image_url}
                      alt={candidate.name}
                      className="w-full h-full object-cover"
                      onError={(e) => {
                        (e.target as HTMLImageElement).style.display = "none";
                      }}
                    />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center text-surface-400 text-[10px]">
                      Pas de photo
                    </div>
                  )}
                </div>

                <div className="flex-1 min-w-0">
                  <h3 className="font-semibold text-sm text-surface-900 leading-tight truncate">
                    {candidate.name}
                  </h3>
                  <p className="text-xs text-surface-500 mt-0.5">{candidate.brand}</p>
                  {candidate.estimated_price && (
                    <p className="text-sm font-semibold text-brand-700 mt-1">
                      {candidate.estimated_price.toFixed(0)} €
                    </p>
                  )}
                </div>
              </div>

              {/* Infos supplémentaires */}
              <div className="flex items-center gap-2 flex-wrap">
                {candidate.segment && (
                  <span className="text-[10px] px-2 py-0.5 bg-surface-100 text-surface-600 rounded-full">
                    {candidate.segment}
                  </span>
                )}
                {candidate.source_url && (
                  <a
                    href={candidate.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    onClick={(e) => e.stopPropagation()}
                    className="text-[10px] text-brand-600 hover:underline"
                  >
                    Voir la fiche ↗
                  </a>
                )}
              </div>

              {candidate.why_selected && (
                <p className="text-[11px] text-surface-500 mt-2 leading-snug">
                  {candidate.why_selected}
                </p>
              )}
            </div>
          );
        })}
      </div>

      {/* Bouton lancer */}
      <div className="flex justify-center">
        <button
          onClick={handleLaunch}
          disabled={selectedCount === 0}
          className="btn-primary text-lg px-10 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          <svg className="w-5 h-5 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
          </svg>
          Lancer le benchmark ({selectedCount} produits)
        </button>
      </div>
    </div>
  );
}
