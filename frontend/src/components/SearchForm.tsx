"use client";

import { useState } from "react";

interface Props {
  onSubmit: (data: any) => void;
}

export default function SearchForm({ onSubmit }: Props) {
  const [productType, setProductType] = useState("");
  const [showOptions, setShowOptions] = useState(false);
  const [market, setMarket] = useState("France");
  const [segment, setSegment] = useState("tous");
  const [maxProducts, setMaxProducts] = useState(10);
  const [priceMin, setPriceMin] = useState("");
  const [priceMax, setPriceMax] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!productType.trim()) return;

    onSubmit({
      product_type: productType.trim(),
      market,
      segment,
      max_products: maxProducts,
      price_min: priceMin ? parseFloat(priceMin) : null,
      price_max: priceMax ? parseFloat(priceMax) : null,
    });
  };

  const examples = [
    "Casques audio à réduction de bruit",
    "Aspirateurs robots",
    "Machines à café automatiques",
    "Trottinettes électriques adulte",
    "Moniteurs 27 pouces 4K",
  ];

  return (
    <div className="card p-8">
      <form onSubmit={handleSubmit}>
        {/* Champ principal */}
        <div className="mb-6">
          <label className="block text-sm font-semibold text-surface-700 mb-2">
            Quel produit souhaitez-vous comparer ?
          </label>
          <input
            type="text"
            value={productType}
            onChange={(e) => setProductType(e.target.value)}
            placeholder="Ex : casques audio à réduction de bruit active"
            className="input-field text-lg"
            autoFocus
          />
        </div>

        {/* Exemples cliquables */}
        <div className="mb-6">
          <p className="text-xs text-surface-500 mb-2">Exemples :</p>
          <div className="flex flex-wrap gap-2">
            {examples.map((ex) => (
              <button
                key={ex}
                type="button"
                onClick={() => setProductType(ex)}
                className="text-xs px-3 py-1.5 bg-brand-50 text-brand-700 rounded-lg 
                           hover:bg-brand-100 transition-colors cursor-pointer"
              >
                {ex}
              </button>
            ))}
          </div>
        </div>

        {/* Options avancées (collapsible) */}
        <div className="mb-6">
          <button
            type="button"
            onClick={() => setShowOptions(!showOptions)}
            className="text-sm text-surface-600 hover:text-surface-800 flex items-center gap-1"
          >
            <svg
              className={`w-4 h-4 transition-transform ${showOptions ? "rotate-90" : ""}`}
              fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
            </svg>
            Options avancées
          </button>

          {showOptions && (
            <div className="mt-4 grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium text-surface-600 mb-1">Marché</label>
                <select
                  value={market}
                  onChange={(e) => setMarket(e.target.value)}
                  className="input-field text-sm"
                >
                  <option value="France">France</option>
                  <option value="Europe">Europe</option>
                  <option value="mondial">Mondial</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-medium text-surface-600 mb-1">Segment</label>
                <select
                  value={segment}
                  onChange={(e) => setSegment(e.target.value)}
                  className="input-field text-sm"
                >
                  <option value="tous">Tous segments</option>
                  <option value="entrée de gamme">Entrée de gamme</option>
                  <option value="milieu de gamme">Milieu de gamme</option>
                  <option value="premium">Premium</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-medium text-surface-600 mb-1">Prix min (€)</label>
                <input
                  type="number"
                  value={priceMin}
                  onChange={(e) => setPriceMin(e.target.value)}
                  placeholder="Aucun"
                  className="input-field text-sm"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-surface-600 mb-1">Prix max (€)</label>
                <input
                  type="number"
                  value={priceMax}
                  onChange={(e) => setPriceMax(e.target.value)}
                  placeholder="Aucun"
                  className="input-field text-sm"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-surface-600 mb-1">Nombre de produits</label>
                <input
                  type="number"
                  min={3}
                  max={20}
                  value={maxProducts}
                  onChange={(e) => setMaxProducts(parseInt(e.target.value) || 10)}
                  className="input-field text-sm"
                />
              </div>
            </div>
          )}
        </div>

        {/* Bouton de lancement */}
        <button
          type="submit"
          disabled={!productType.trim()}
          className="btn-primary w-full text-lg disabled:opacity-40 disabled:cursor-not-allowed 
                     disabled:hover:translate-y-0 disabled:hover:shadow-lg"
        >
          <svg className="w-5 h-5 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          Lancer le benchmark
        </button>
      </form>
    </div>
  );
}
