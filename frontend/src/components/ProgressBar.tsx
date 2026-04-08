"use client";

interface Props {
  percent: number;
  message: string;
  productType: string;
}

const stages = [
  { key: "selecting", label: "Sélection des produits", icon: "🔍" },
  { key: "criteria", label: "Définition des critères", icon: "📋" },
  { key: "collecting", label: "Collecte des données", icon: "🌐" },
  { key: "done", label: "Terminé", icon: "✅" },
];

export default function ProgressBar({ percent, message, productType }: Props) {
  let activeStage = 0;
  if (percent > 20) activeStage = 1;
  if (percent > 30) activeStage = 2;
  if (percent >= 100) activeStage = 3;

  return (
    <div className="card p-8">
      <div className="text-center mb-8">
        <div className="inline-flex items-center gap-2 px-4 py-1.5 bg-brand-50 text-brand-500 rounded-full text-sm font-medium mb-4">
          <span className="w-2 h-2 bg-accent-500 rounded-full progress-animate" />
          Benchmark en cours
        </div>
        <h3 className="font-display font-bold text-xl text-brand-500">
          {productType}
        </h3>
      </div>

      {/* Étapes */}
      <div className="flex justify-between mb-8 relative">
        <div className="absolute top-5 left-[12%] right-[12%] h-0.5 bg-surface-200" />
        <div
          className="absolute top-5 left-[12%] h-0.5 bg-brand-500 transition-all duration-1000 ease-out"
          style={{ width: `${Math.min(activeStage / (stages.length - 1), 1) * 76}%` }}
        />
        {stages.map((stage, i) => (
          <div key={stage.key} className="flex flex-col items-center relative z-10">
            <div
              className={`w-10 h-10 rounded-full flex items-center justify-center text-lg
                transition-all duration-500
                ${i <= activeStage
                  ? "bg-brand-500 text-white shadow-lg shadow-brand-500/30"
                  : "bg-surface-100 text-surface-400 border-2 border-surface-200"
                }`}
            >
              {stage.icon}
            </div>
            <span
              className={`text-xs mt-2 font-medium text-center max-w-[100px]
                ${i <= activeStage ? "text-brand-500" : "text-surface-400"}`}
            >
              {stage.label}
            </span>
          </div>
        ))}
      </div>

      {/* Barre */}
      <div className="mb-4">
        <div className="flex justify-between items-center mb-2">
          <span className="text-sm font-medium text-surface-700">Progression</span>
          <span className="text-sm font-mono font-medium text-brand-500">{percent}%</span>
        </div>
        <div className="w-full h-3 bg-surface-100 rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-brand-500 to-brand-400 rounded-full 
                       transition-all duration-1000 ease-out"
            style={{ width: `${percent}%` }}
          />
        </div>
      </div>

      <p className="text-sm text-surface-500 text-center progress-animate">
        {message}
      </p>
    </div>
  );
}
