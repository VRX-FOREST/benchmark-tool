"use client";

import { useState, useMemo } from "react";
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  getFilteredRowModel,
  flexRender,
  createColumnHelper,
  SortingState,
} from "@tanstack/react-table";

interface Props {
  products: any[];
  criteria: any[];
}

/**
 * Cherche une valeur dans product.data en essayant plusieurs formats de clé.
 * L'IA peut retourner les clés sous différentes formes :
 *   - "Généralités > Prix (€)"
 *   - "Prix (€)"
 *   - "Prix"
 * Cette fonction essaie toutes les variantes.
 */
function findValue(data: Record<string, any>, category: string, fieldName: string, unit: string): any {
  if (!data) return null;

  // Format 1 : "Catégorie > Nom (unité)" — le format actuel de l'IA
  const keyWithCatAndUnit = unit
    ? `${category} > ${fieldName} (${unit})`
    : `${category} > ${fieldName}`;
  if (data[keyWithCatAndUnit] !== undefined) return data[keyWithCatAndUnit];

  // Format 2 : "Nom (unité)" — sans catégorie
  const keyWithUnit = unit ? `${fieldName} (${unit})` : fieldName;
  if (data[keyWithUnit] !== undefined) return data[keyWithUnit];

  // Format 3 : "Nom" — juste le nom du champ
  if (data[fieldName] !== undefined) return data[fieldName];

  // Format 4 : "Catégorie > Nom" — avec catégorie mais sans unité
  const keyWithCat = `${category} > ${fieldName}`;
  if (data[keyWithCat] !== undefined) return data[keyWithCat];

  // Format 5 : recherche partielle (dernier recours)
  for (const key of Object.keys(data)) {
    if (key.includes(fieldName)) return data[key];
  }

  return null;
}

export default function ProductTable({ products, criteria }: Props) {
  const [sorting, setSorting] = useState<SortingState>([]);
  const [globalFilter, setGlobalFilter] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("all");

  // Construire la liste des catégories pour le filtre
  const categories = useMemo(() => {
    const cats = criteria.map((c: any) => c.category);
    return ["all", ...cats];
  }, [criteria]);

  // Construire les colonnes dynamiquement à partir des critères
  const columns = useMemo(() => {
    const columnHelper = createColumnHelper<any>();
    const cols: any[] = [];

    // Colonne image + nom (toujours visible)
    cols.push(
      columnHelper.accessor("name", {
        header: "Produit",
        cell: (info) => {
          const product = info.row.original;
          return (
            <div className="flex items-center gap-3 min-w-[220px]">
              <div className="w-14 h-14 rounded-xl bg-surface-100 overflow-hidden flex-shrink-0 border border-surface-200">
                {product.image_url ? (
                  <img
                    src={product.image_url}
                    alt={product.name}
                    className="w-full h-full object-cover"
                    onError={(e) => {
                      (e.target as HTMLImageElement).style.display = "none";
                    }}
                  />
                ) : (
                  <div className="w-full h-full flex items-center justify-center text-surface-400 text-xs">
                    N/A
                  </div>
                )}
              </div>
              <div>
                <div className="font-semibold text-surface-900 text-sm leading-tight">
                  {product.name}
                </div>
                <div className="text-xs text-surface-500 mt-0.5">{product.brand}</div>
                {product.source_url && (
                  <a
                    href={product.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-xs text-brand-600 hover:text-brand-700 hover:underline mt-0.5 inline-block"
                  >
                    Voir la source ↗
                  </a>
                )}
              </div>
            </div>
          );
        },
        enableSorting: true,
      })
    );

    // Colonne prix
    cols.push(
      columnHelper.accessor("price_min", {
        header: "Prix",
        cell: (info) => {
          const product = info.row.original;
          if (!product.price_min && !product.price_max) {
            return <span className="text-surface-400 text-sm">—</span>;
          }
          if (product.price_min === product.price_max || !product.price_max) {
            return (
              <span className="font-semibold text-surface-900">
                {product.price_min?.toFixed(0)} €
              </span>
            );
          }
          return (
            <span className="font-semibold text-surface-900">
              {product.price_min?.toFixed(0)} – {product.price_max?.toFixed(0)} €
            </span>
          );
        },
        enableSorting: true,
      })
    );

    // Colonne complétude
    cols.push(
      columnHelper.accessor("completeness", {
        header: "Données",
        cell: (info) => {
          const pct = Math.round((info.getValue() || 0) * 100);
          let color = "bg-red-500";
          if (pct >= 70) color = "bg-green-500";
          else if (pct >= 40) color = "bg-yellow-500";
          return (
            <div className="flex items-center gap-2 min-w-[80px]">
              <div className="w-12 h-1.5 bg-surface-200 rounded-full overflow-hidden">
                <div className={`h-full ${color} rounded-full`} style={{ width: `${pct}%` }} />
              </div>
              <span className="text-xs text-surface-600 font-mono">{pct}%</span>
            </div>
          );
        },
        enableSorting: true,
      })
    );

    // Colonnes dynamiques par critère — CORRIGÉ : utilise findValue()
    for (const category of criteria) {
      if (selectedCategory !== "all" && category.category !== selectedCategory) continue;

      for (const field of category.fields || []) {
        const fieldName = field.name;
        const fieldUnit = field.unit || "";
        const categoryName = category.category;

        cols.push(
          columnHelper.accessor(
            (row) => findValue(row.data, categoryName, fieldName, fieldUnit),
            {
              id: `${categoryName}__${fieldName}`,
              header: () => (
                <div>
                  <div className="text-xs font-semibold">{fieldName}</div>
                  {fieldUnit && (
                    <div className="text-[10px] text-surface-400 font-normal">{fieldUnit}</div>
                  )}
                </div>
              ),
              cell: (info) => {
                const val = info.getValue();
                if (val === null || val === undefined) {
                  return <span className="text-surface-300">—</span>;
                }
                if (typeof val === "boolean") {
                  return val ? (
                    <span className="text-green-600 font-medium">✓ Oui</span>
                  ) : (
                    <span className="text-red-500">✗ Non</span>
                  );
                }
                if (typeof val === "number") {
                  return (
                    <span className="text-sm text-surface-800 font-mono">
                      {val.toLocaleString("fr-FR")}
                      {fieldUnit && <span className="text-surface-400 ml-1 font-sans text-xs">{fieldUnit}</span>}
                    </span>
                  );
                }
                return (
                  <span className="text-sm text-surface-800">{String(val)}</span>
                );
              },
              enableSorting: true,
            }
          )
        );
      }
    }

    return cols;
  }, [criteria, selectedCategory]);

  const table = useReactTable({
    data: products,
    columns,
    state: { sorting, globalFilter },
    onSortingChange: setSorting,
    onGlobalFilterChange: setGlobalFilter,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
  });

  if (!products.length) {
    return (
      <div className="card p-12 text-center">
        <p className="text-surface-500">Aucun produit collecté.</p>
      </div>
    );
  }

  return (
    <div>
      {/* Barre de contrôles */}
      <div className="flex flex-wrap items-center gap-4 mb-6">
        {/* Recherche globale */}
        <div className="relative flex-1 min-w-[200px]">
          <svg
            className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-surface-400"
            fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <input
            type="text"
            placeholder="Filtrer les produits..."
            value={globalFilter}
            onChange={(e) => setGlobalFilter(e.target.value)}
            className="input-field pl-10 text-sm"
          />
        </div>

        {/* Filtre par catégorie */}
        <div className="flex gap-1.5 flex-wrap">
          {categories.map((cat) => (
            <button
              key={cat}
              onClick={() => setSelectedCategory(cat)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all
                ${selectedCategory === cat
                  ? "bg-brand-600 text-white shadow-sm"
                  : "bg-surface-100 text-surface-600 hover:bg-surface-200"
                }`}
            >
              {cat === "all" ? "Tous les critères" : cat}
            </button>
          ))}
        </div>
      </div>

      {/* Tableau */}
      <div className="card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              {table.getHeaderGroups().map((headerGroup) => (
                <tr key={headerGroup.id} className="border-b border-surface-200 bg-surface-50">
                  {headerGroup.headers.map((header) => (
                    <th
                      key={header.id}
                      className="px-4 py-3 text-left text-xs font-semibold text-surface-600 
                                 uppercase tracking-wider whitespace-nowrap cursor-pointer
                                 hover:bg-surface-100 transition-colors select-none"
                      onClick={header.column.getToggleSortingHandler()}
                    >
                      <div className="flex items-center gap-1">
                        {flexRender(header.column.columnDef.header, header.getContext())}
                        {header.column.getIsSorted() === "asc" && (
                          <span className="text-brand-500">↑</span>
                        )}
                        {header.column.getIsSorted() === "desc" && (
                          <span className="text-brand-500">↓</span>
                        )}
                      </div>
                    </th>
                  ))}
                </tr>
              ))}
            </thead>
            <tbody>
              {table.getRowModel().rows.map((row, i) => (
                <tr
                  key={row.id}
                  className={`border-b border-surface-100 hover:bg-brand-50/30 transition-colors
                    ${i % 2 === 0 ? "bg-surface-0" : "bg-surface-50/50"}`}
                >
                  {row.getVisibleCells().map((cell) => (
                    <td key={cell.id} className="px-4 py-3 whitespace-nowrap">
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Footer avec stats */}
        <div className="px-4 py-3 bg-surface-50 border-t border-surface-200 
                        flex items-center justify-between text-xs text-surface-500">
          <span>{products.length} produits</span>
          <span>
            Complétude moyenne :{" "}
            {Math.round(
              (products.reduce((acc: number, p: any) => acc + (p.completeness || 0), 0) /
                Math.max(products.length, 1)) *
                100
            )}
            %
          </span>
        </div>
      </div>
    </div>
  );
}
