"use client";
import { useEffect, useRef } from "react";
import { STATE_COLOR, STATE_LABEL } from "@/lib/utils";
import type { ThoughtStep } from "@/lib/types";

interface Props {
    steps: ThoughtStep[];
    running: boolean;
    currentState: string;
    riskScore: number;
}

const STEP_LABELS: Record<string, { emoji: string; label: string; color: string }> = {
    "感知": { emoji: "👁️", label: "感知", color: "#60a5fa" },
    "检索": { emoji: "🔍", label: "检索", color: "#a78bfa" },
    "规划": { emoji: "🧠", label: "规划", color: "#f59e0b" },
    "验证": { emoji: "🛡️", label: "验证", color: "#f97316" },
    "输出": { emoji: "⚡", label: "输出", color: "#22c55e" },
};

function getStepMeta(thought: string) {
    for (const [key, meta] of Object.entries(STEP_LABELS)) {
        if (thought.includes(`[${key}]`)) return meta;
    }
    return { emoji: "💭", label: "思考", color: "#64748b" };
}

function TypewriterText({ text, speed = 12 }: { text: string; speed?: number }) {
    const spanRef = useRef<HTMLSpanElement>(null);
    useEffect(() => {
        if (!spanRef.current) return;
        const el = spanRef.current;
        el.textContent = "";
        let i = 0;
        const timer = setInterval(() => {
            if (i < text.length) {
                el.textContent += text[i++];
            } else {
                clearInterval(timer);
            }
        }, 1000 / speed);
        return () => clearInterval(timer);
    }, [text, speed]);
    return <span ref={spanRef} />;
}

export function ThoughtChainPanel({ steps, running, currentState, riskScore }: Props) {
    const bottomRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [steps]);

    return (
        <div className="card h-full flex flex-col" style={{ background: "var(--bg-panel)" }}>
            {/* 头部 */}
            <div className="flex items-center justify-between px-4 py-3 border-b" style={{ borderColor: "var(--border)" }}>
                <div className="flex items-center gap-2">
                    <span className="panel-title">推理轨迹</span>
                    {running && (
                        <span className="pulse-dot w-2 h-2 rounded-full" style={{ background: "var(--color-info)" }} />
                    )}
                </div>
                <div className="flex items-center gap-3">
                    <span className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>
                        RiskScore:
                        <span className="ml-1 font-bold" style={{ color: riskScore >= 50 ? "var(--color-critical)" : riskScore >= 20 ? "var(--color-medium)" : "var(--color-low)" }}>
                            {riskScore.toFixed(1)}
                        </span>
                    </span>
                    <span
                        className="badge badge-info text-xs"
                        style={{ color: STATE_COLOR[currentState] ?? "#64748b", borderColor: STATE_COLOR[currentState] ?? "#64748b" }}
                    >
                        {STATE_LABEL[currentState] ?? currentState}
                    </span>
                </div>
            </div>

            {/* 轨迹区域 */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
                {steps.length === 0 && !running && (
                    <div className="flex flex-col items-center justify-center h-full gap-3" style={{ color: "var(--text-muted)" }}>
                        <div className="text-4xl">🤖</div>
                        <p className="text-sm">选择场景并触发推理，Agent 思考轨迹将在此实时展示</p>
                    </div>
                )}

                {steps.map((step, idx) => {
                    const meta = getStepMeta(step.thought);
                    const stateClass = `state-${step.state.toLowerCase()}`;
                    return (
                        <div key={idx} className={`thought-step ${stateClass}`}>
                            {/* 头部行 */}
                            <div className="flex items-center gap-2 mb-1">
                                <span className="text-base">{meta.emoji}</span>
                                <span className="text-xs font-semibold uppercase tracking-wider" style={{ color: meta.color }}>
                                    {meta.label}
                                </span>
                                <span className="text-xs ml-auto font-mono" style={{ color: "var(--text-muted)" }}>
                                    #{step.step_index + 1}
                                </span>
                            </div>

                            {/* Thought */}
                            <p className="text-sm mb-1 leading-relaxed" style={{ color: "var(--text-primary)" }}>
                                {idx === steps.length - 1 && running
                                    ? <TypewriterText text={step.thought} />
                                    : step.thought}
                            </p>

                            {/* Action */}
                            {step.action && (
                                <div className="rounded px-2 py-1 mb-1 font-mono text-xs"
                                    style={{ background: "rgba(59,130,246,0.08)", color: "var(--text-accent)", borderLeft: "2px solid rgba(59,130,246,0.4)" }}>
                                    → {step.action}
                                </div>
                            )}

                            {/* Observation */}
                            {step.observation && (
                                <p className="text-xs mt-1 leading-relaxed" style={{ color: "var(--text-secondary)" }}>
                                    <span className="font-semibold" style={{ color: "#6ee7b7" }}>观察: </span>
                                    {step.observation}
                                </p>
                            )}

                            {/* SOP references */}
                            {step.sop_references?.length > 0 && (
                                <div className="flex flex-wrap gap-1 mt-1">
                                    {step.sop_references.map((ref, i) => (
                                        <span key={i} className="badge badge-info" style={{ fontSize: 10 }}>📄 {ref}</span>
                                    ))}
                                </div>
                            )}
                        </div>
                    );
                })}

                {running && steps.length === 0 && (
                    <div className="thought-step">
                        <p className="text-sm cursor-blink" style={{ color: "var(--text-secondary)" }}>
                            正在初始化 Agent 推理
                        </p>
                    </div>
                )}

                <div ref={bottomRef} />
            </div>
        </div>
    );
}
