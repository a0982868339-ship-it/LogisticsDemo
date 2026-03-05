"use client";
import { useState, useCallback } from "react";
import { useInference, useTelemetry } from "@/hooks/useApi";
import { ThoughtChainPanel } from "@/components/dashboard/ThoughtChainPanel";
import { SensorChart } from "@/components/dashboard/SensorChart";
import { CommandConsole } from "@/components/dashboard/CommandConsole";
import { ScenarioTrigger } from "@/components/dashboard/ScenarioTrigger";
import { RISK_LEVEL, STATE_LABEL } from "@/lib/utils";
import type { Scenario } from "@/lib/types";

export default function MissionDashboard() {
    const inference = useInference();
    const telemetry = useTelemetry();
    const [activeScenario, setActiveScenario] = useState<Scenario | null>(null);

    const handleTrigger = useCallback(
        async (scenario: Scenario) => {
            setActiveScenario(scenario);
            await telemetry.trigger(scenario);
            inference.runInference(scenario);
        },
        [telemetry, inference]
    );

    const risk = RISK_LEVEL(inference.riskScore);

    return (
        <div className="min-h-screen flex flex-col" style={{ background: "var(--bg-base)" }}>
            {/* 扫描线 */}
            <div className="scan-line" />

            {/* ── 顶部导航栏 ── */}
            <header className="border-b px-6 py-3 flex items-center gap-4"
                style={{ background: "var(--bg-surface)", borderColor: "var(--border)" }}>
                {/* Logo */}
                <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-lg flex items-center justify-center"
                        style={{ background: "linear-gradient(135deg, #1e3a8a, #3b82f6)" }}>
                        <span className="text-white text-sm font-bold">NX</span>
                    </div>
                    <div>
                        <h1 className="text-sm font-bold leading-none" style={{ color: "var(--text-primary)" }}>
                            NEXUS-OMNIGUARD
                        </h1>
                        <p className="text-xs leading-none mt-0.5" style={{ color: "var(--text-muted)" }}>
                            智巡护航 · 具身智能决策中枢
                        </p>
                    </div>
                </div>

                <div className="w-px h-8 mx-2" style={{ background: "var(--border)" }} />

                {/* 系统状态指标 */}
                <div className="flex items-center gap-6">
                    <div className="flex items-center gap-2">
                        <span className="w-2 h-2 rounded-full pulse-dot" style={{ background: "var(--color-low)" }} />
                        <span className="text-xs" style={{ color: "var(--text-secondary)" }}>系统在线</span>
                    </div>
                    <div className="text-xs font-mono" style={{ color: "var(--text-secondary)" }}>
                        Agent: <span style={{ color: "var(--text-accent)" }}>{STATE_LABEL[inference.currentState] ?? "空闲"}</span>
                    </div>
                    {inference.riskScore > 0 && (
                        <span className={`badge ${risk.cls}`}>
                            风险 {risk.label} {inference.riskScore.toFixed(0)}分
                        </span>
                    )}
                    {activeScenario && (
                        <span className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>
                            场景: <span style={{ color: "#f59e0b" }}>{activeScenario}</span>
                        </span>
                    )}
                </div>

                <div className="ml-auto text-xs font-mono" style={{ color: "var(--text-muted)" }}>
                    三亚综合保税区 · EMIS v4.1
                </div>
            </header>

            {/* ── 主体三栏布局 ── */}
            <main className="flex-1 grid gap-3 p-3 overflow-hidden"
                style={{ gridTemplateColumns: "300px 1fr 340px", gridTemplateRows: "1fr" }}>

                {/* 左列：场景触发 + 传感器图表 */}
                <div className="flex flex-col gap-3 min-h-0">
                    <ScenarioTrigger
                        running={inference.running}
                        onTrigger={handleTrigger}
                        onStop={inference.stop}
                    />
                    <div className="flex-1 min-h-0">
                        <SensorChart latest={telemetry.latest} batches={telemetry.batches} />
                    </div>
                </div>

                {/* 中列：推理轨迹（最大） */}
                <div className="min-h-0">
                    <ThoughtChainPanel
                        steps={inference.steps}
                        running={inference.running}
                        currentState={inference.currentState}
                        riskScore={inference.riskScore}
                    />
                </div>

                {/* 右列：指令控制台 */}
                <div className="min-h-0">
                    <CommandConsole command={inference.command} />
                </div>
            </main>

            {/* ── 底部状态栏 ── */}
            <footer className="border-t px-6 py-2 flex items-center gap-6"
                style={{ background: "var(--bg-surface)", borderColor: "var(--border)" }}>
                <span className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>
                    推理步骤: <span style={{ color: "var(--text-accent)" }}>{inference.steps.length}</span>
                </span>
                <span className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>
                    知识库: <span style={{ color: "var(--color-low)" }}>就绪 (20份手册)</span>
                </span>
                <span className="text-xs font-mono ml-auto" style={{ color: "var(--text-muted)" }}>
                    端对端延迟目标: &lt; 2000ms · Safety Guard: 激活
                </span>
            </footer>
        </div>
    );
}
