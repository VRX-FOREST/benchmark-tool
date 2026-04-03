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
  ColumnFiltersState,
} from "@tanstack/react-table";

interface Props {
  products: any[];
  criteria: any[];
}

export default function ProductTable({ products, criteria }: Props) {
  const [sorting, setSorting] = useState<SortingState>([]);
  const [globalFilter, setGlobalFilter] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("all");
  const [expandedProduct, setExpandedProduct] = useState<string | null>(null);

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

    // Colonnes dynamiques par critère
    for (const category of criteria) {
      if (selectedCategory !== "all" && category.category !== selectedCategory) continue;

      for (const field of category.fields || []) {
        const fieldKey = field.name;
        cols.push(
          columnHelper.accessor(
            (row) => {
              const val = row.data?.[fieldKey];
              return val !== null && val !== undefined ? val : null;
            },
            {
              id: `${category.category}__${fieldKey}`,
              header: () => (
                <div>
                  <div className="text-xs font-semibold">{fieldKey}</div>
                  {field.unit && (
                    <div className="text-[10px] text-surface-400 font-normal">{field.unit}</div>
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
                    <span className="text-green-600 font-medium">Oui</span>
                  ) : (
                    <span className="text-red-500">Non</span>
                  );
                }
                return (
                  <span className="text-sm text-surface-800">
                    {String(val)}
                    {field.unit && <span className="text-surface-400 ml-0.5">{field.unit}</span>}
                  </span>
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
