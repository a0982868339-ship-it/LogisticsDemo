"use client";
import type { ActionCommand } from "@/lib/types";

interface Props {
    command: ActionCommand | null;
}

const STATUS_META: Record<string, { label: string; color: string }> = {
    PENDING: { label: "待执行", color: "#64748b" },
    EXECUTING: { label: "执行中", color: "#22c55e" },
    COMPLETED: { label: "已完成", color: "#60a5fa" },
    BLOCKED: { label: "已拦截 ⛔", color: "#ef4444" },
};

export function CommandConsole({ command }: Props) {
    if (!command) {
        return (
            <div className="card h-full flex items-center justify-center" style={{ background: "var(--bg-panel)" }}>
                <div className="text-center" style={{ color: "var(--text-muted)" }}>
                    <div className="text-3xl mb-2">⚡</div>
                    <p className="text-sm">推理完成后，硬件指令将显示在此</p>
                </div>
            </div>
        );
    }

    const statusMeta = STATUS_META[command.status] ?? STATUS_META.PENDING;
    const isBlocked = command.status === "BLOCKED";

    return (
        <div className="card h-full flex flex-col overflow-hidden"
            style={{
                background: "var(--bg-panel)",
                borderColor: isBlocked ? "rgba(239,68,68,0.5)" : command.safety_verified ? "rgba(34,197,94,0.3)" : "var(--border)",
            }}>
            {/* 头部 */}
            <div className="px-4 py-3 border-b" style={{ borderColor: isBlocked ? "rgba(239,68,68,0.3)" : "var(--border)" }}>
                <div className="flex items-center justify-between">
                    <span className="panel-title">指令执行控制台</span>
                    <span className="badge" style={{ color: statusMeta.color, borderColor: statusMeta.color, background: `${statusMeta.color}18` }}>
                        {statusMeta.label}
                    </span>
                </div>
                <div className="flex items-center gap-3 mt-2">
                    <span className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>
                        CMD: <span style={{ color: "var(--text-accent)" }}>{command.cmd_id.slice(0, 8)}</span>
                    </span>
                    <span className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>
                        风险: <span style={{ color: command.risk_score >= 50 ? "var(--color-critical)" : "var(--color-medium)" }}>
                            {command.risk_score.toFixed(1)}
                        </span>
                    </span>
                    <span className="text-xs" style={{ color: command.safety_verified ? "var(--color-low)" : "var(--color-critical)" }}>
                        {command.safety_verified ? "✅ 安全校验通过" : "❌ 安全校验未通过"}
                    </span>
                </div>
            </div>

            {/* 指令列表 */}
            <div className="flex-1 overflow-y-auto p-3 space-y-2">
                {command.instructions.length === 0 && (
                    <div className="flex items-center justify-center h-24 rounded"
                        style={{ background: "rgba(239,68,68,0.06)", border: "1px solid rgba(239,68,68,0.2)" }}>
                        <p className="text-sm" style={{ color: "var(--color-critical)" }}>
                            ⛔ 所有指令已被安全栅栏拦截 — 禁止下发
                        </p>
                    </div>
                )}

                {command.instructions.map((instr) => (
                    <div key={instr.seq} className="rounded-lg p-3 border"
                        style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}>
                        {/* SEQ & Device */}
                        <div className="flex items-center gap-2 mb-2">
                            <span className="w-5 h-5 rounded-full flex items-center justify-center text-xs font-bold"
                                style={{ background: "rgba(59,130,246,0.2)", color: "var(--color-info)", border: "1px solid rgba(59,130,246,0.3)" }}>
                                {instr.seq}
                            </span>
                            <span className="text-xs font-mono" style={{ color: "var(--text-accent)" }}>{instr.device}</span>
                            <span className="ml-auto text-xs font-mono font-semibold" style={{ color: "#a78bfa" }}>{instr.action}</span>
                        </div>

                        {/* Params */}
                        {Object.keys(instr.params).length > 0 && (
                            <pre className="text-xs rounded p-2 mb-2 overflow-x-auto font-mono leading-relaxed"
                                style={{ background: "rgba(0,0,0,0.3)", color: "#94a3b8" }}>
                                {JSON.stringify(instr.params, null, 2)}
                            </pre>
                        )}

                        {/* SOP 条款 */}
                        <div className="flex flex-col gap-1">
                            {instr.sop_clause && (
                                <div className="flex items-start gap-2">
                                    <span className="text-xs" style={{ color: "var(--text-muted)" }}>📋 SOP:</span>
                                    <span className="text-xs" style={{ color: "var(--text-secondary)" }}>{instr.sop_clause}</span>
                                </div>
                            )}
                            {instr.legal_basis && (
                                <div className="flex items-start gap-2">
                                    <span className="text-xs" style={{ color: "var(--text-muted)" }}>⚖️ 法律:</span>
                                    <span className="text-xs" style={{ color: "#fbbf24" }}>{instr.legal_basis}</span>
                                </div>
                            )}
                        </div>
                    </div>
                ))}

                {/* SOP 来源 */}
                {command.sop_reference && (
                    <div className="rounded p-2 text-xs" style={{ background: "rgba(59,130,246,0.06)", border: "1px solid rgba(59,130,246,0.2)", color: "var(--text-secondary)" }}>
                        📄 知识来源: {command.sop_reference}
                    </div>
                )}
            </div>

            {/* JSON 原始 payload */}
            <details className="border-t" style={{ borderColor: "var(--border)" }}>
                <summary className="px-4 py-2 text-xs cursor-pointer select-none"
                    style={{ color: "var(--text-muted)" }}>
                    查看原始 JSON Payload
                </summary>
                <pre className="px-4 pb-3 text-xs font-mono overflow-x-auto" style={{ color: "#60a5fa", maxHeight: 200, background: "rgba(0,0,0,0.2)" }}>
                    {JSON.stringify(command, null, 2)}
                </pre>
            </details>
        </div>
    );
}
