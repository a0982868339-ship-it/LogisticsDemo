"use client";
import { useMemo } from "react";
import {
    LineChart, Line, XAxis, YAxis, Tooltip,
    ResponsiveContainer, CartesianGrid, ReferenceLine,
} from "recharts";
import type { TelemetryBatch, TelemetryReading } from "@/lib/types";

interface Props {
    latest: TelemetryBatch | null;
    batches: TelemetryBatch[];
}

type SensorKey = keyof typeof SENSOR_CONFIG;
type DataPoint = { time: string } & Partial<Record<SensorKey, number>>;

const SENSOR_CONFIG = {
    SALT_SPRAY: { label: "盐雾浓度 (mg/m³)", color: "#38bdf8", threshold: 15, unit: "mg/m³" },
    VOC: { label: "VOC (mg/m³)", color: "#f472b6", threshold: 1.0, unit: "mg/m³" },
    TEMP_HUMIDITY: { label: "温度 (°C)", color: "#fb923c", threshold: 40, unit: "°C" },
};

function SensorCard({ reading }: { reading: TelemetryReading }) {
    const cfg = SENSOR_CONFIG[reading.sensor_type as keyof typeof SENSOR_CONFIG];
    if (!cfg || typeof reading.value !== "number") return null;
    const pct = Math.min((reading.value / cfg.threshold) * 100, 200);
    const isOver = reading.is_anomaly;

    return (
        <div className="rounded-lg p-3 border" style={{
            background: isOver ? "rgba(239,68,68,0.06)" : "var(--bg-card)",
            borderColor: isOver ? "rgba(239,68,68,0.4)" : "var(--border)",
        }}>
            <div className="flex justify-between items-start mb-2">
                <span className="text-xs" style={{ color: "var(--text-muted)" }}>{cfg.label}</span>
                {isOver && <span className="badge badge-critical" style={{ fontSize: 9 }}>超标</span>}
            </div>
            <div className="flex items-end gap-1 mb-2">
                <span className="text-2xl font-mono font-bold" style={{ color: isOver ? "var(--color-critical)" : cfg.color }}>
                    {typeof reading.value === "number" ? reading.value.toFixed(1) : reading.value}
                </span>
                <span className="text-xs mb-1" style={{ color: "var(--text-muted)" }}>{cfg.unit}</span>
            </div>
            <div className="progress-bar">
                <div
                    className="progress-fill"
                    style={{
                        width: `${Math.min(pct, 100)}%`,
                        background: isOver
                            ? "linear-gradient(90deg, var(--color-critical), #ff6b6b)"
                            : `linear-gradient(90deg, ${cfg.color}88, ${cfg.color})`,
                    }}
                />
            </div>
            <div className="flex justify-between mt-1">
                <span className="text-xs" style={{ color: "var(--text-muted)" }}>阈值: {cfg.threshold}{cfg.unit}</span>
                <span className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>{reading.zone_id}</span>
            </div>
        </div>
    );
}

type TooltipPayloadItem = { dataKey?: string | number; value?: number | string; color?: string };
type CustomTooltipProps = { active?: boolean; payload?: TooltipPayloadItem[]; label?: string | number };

const CustomTooltip = ({ active, payload, label }: CustomTooltipProps) => {
    if (!active || !payload?.length) return null;
    return (
        <div className="rounded-lg p-3 border text-xs font-mono"
            style={{ background: "#0d1424", borderColor: "var(--border)", minWidth: 140 }}>
            <p style={{ color: "var(--text-muted)" }} className="mb-1">{label}</p>
            {payload.map((p) => {
                const value = typeof p.value === "number" ? p.value.toFixed(2) : p.value;
                return (
                    <p key={String(p.dataKey)} style={{ color: p.color }}>
                        {p.dataKey}: {value}
                    </p>
                );
            })}
        </div>
    );
};

export function SensorChart({ latest, batches }: Props) {
    const history = useMemo(() => {
        return batches
            .slice(0, 30)
            .reverse()
            .map((batch: TelemetryBatch) => {
                const point: DataPoint = {
                    time: new Date(batch.triggered_at).toLocaleTimeString("zh-CN"),
                };
                for (const r of batch.readings) {
                    const sensorKey = r.sensor_type as SensorKey;
                    if (typeof r.value === "number" && sensorKey in SENSOR_CONFIG) {
                        point[sensorKey] = r.value;
                    }
                }
                return point;
            });
    }, [batches]);

    const numericReadings = latest?.readings.filter(
        (r): r is TelemetryReading & { value: number } =>
            typeof r.value === "number" && r.sensor_type in SENSOR_CONFIG
    ) ?? [];

    return (
        <div className="card h-full flex flex-col" style={{ background: "var(--bg-panel)" }}>
            <div className="px-4 py-3 border-b" style={{ borderColor: "var(--border)" }}>
                <span className="panel-title">传感器数据流</span>
            </div>

            <div className="flex-1 flex flex-col p-3 gap-3 overflow-y-auto">
                {/* 传感器卡片 */}
                <div className="grid grid-cols-3 gap-2">
                    {numericReadings.map((r) => <SensorCard key={r.sensor_id} reading={r} />)}
                </div>

                {/* 趋势图 */}
                {history.length >= 2 && (
                    <div className="rounded-lg p-3 border" style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}>
                        <p className="text-xs mb-2 uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>历史趋势</p>
                        <ResponsiveContainer width="100%" height={140}>
                            <LineChart data={history} margin={{ top: 4, right: 8, bottom: 0, left: -20 }}>
                                <CartesianGrid strokeDasharray="3 3" stroke="#1e2d45" />
                                <XAxis dataKey="time" tick={{ fill: "#475569", fontSize: 9 }} interval="preserveStartEnd" />
                                <YAxis tick={{ fill: "#475569", fontSize: 9 }} />
                                <Tooltip content={<CustomTooltip />} />
                                <ReferenceLine y={15} stroke="rgba(239,68,68,0.4)" strokeDasharray="4 2" label={{ value: "盐雾阈值", fill: "#f87171", fontSize: 9 }} />
                                <Line type="monotone" dataKey="SALT_SPRAY" stroke="#38bdf8" dot={false} strokeWidth={2} />
                                <Line type="monotone" dataKey="TEMP_HUMIDITY" stroke="#fb923c" dot={false} strokeWidth={2} />
                                <Line type="monotone" dataKey="VOC" stroke="#f472b6" dot={false} strokeWidth={2} />
                            </LineChart>
                        </ResponsiveContainer>
                    </div>
                )}

                {!latest && (
                    <div className="flex items-center justify-center h-32 rounded-lg border" style={{ borderColor: "var(--border)", color: "var(--text-muted)" }}>
                        <p className="text-sm">触发任意场景以查看传感器数据</p>
                    </div>
                )}
            </div>
        </div>
    );
}
