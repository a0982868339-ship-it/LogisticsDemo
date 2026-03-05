"use client";
import type { Scenario } from "@/lib/types";
import { SCENARIO_META } from "@/lib/types";

interface Props {
    running: boolean;
    onTrigger: (scenario: Scenario) => void;
    onStop: () => void;
}

export function ScenarioTrigger({ running, onTrigger, onStop }: Props) {
    const scenarios = Object.entries(SCENARIO_META) as [Scenario, typeof SCENARIO_META[Scenario]][];

    return (
        <div className="card" style={{ background: "var(--bg-panel)" }}>
            <div className="px-4 py-3 border-b" style={{ borderColor: "var(--border)" }}>
                <span className="panel-title">场景触发控制台</span>
            </div>
            <div className="p-3 grid grid-cols-2 gap-2">
                {scenarios.map(([key, meta]) => (
                    <button
                        key={key}
                        onClick={() => onTrigger(key)}
                        disabled={running}
                        className={`${meta.btnClass} text-left p-3 rounded-lg transition-all`}
                        style={{ opacity: running ? 0.5 : 1, cursor: running ? "not-allowed" : "pointer" }}
                    >
                        <div className="flex items-center gap-2 mb-1">
                            <span>{meta.icon}</span>
                            <span className="text-sm font-semibold">{meta.label}</span>
                        </div>
                        <p className="text-xs leading-snug" style={{ color: "rgba(255,255,255,0.55)" }}>
                            {meta.desc}
                        </p>
                    </button>
                ))}
            </div>

            {running && (
                <div className="px-3 pb-3">
                    <button
                        onClick={onStop}
                        className="w-full py-2 rounded-lg text-sm font-semibold transition-all"
                        style={{ background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.4)", color: "#fca5a5" }}>
                        ⏹ 中止推理
                    </button>
                </div>
            )}
        </div>
    );
}
