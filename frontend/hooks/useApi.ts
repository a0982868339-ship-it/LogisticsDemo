"use client";
import { useCallback, useRef, useState } from "react";
import type { ThoughtStep, ActionCommand, TelemetryBatch, Scenario } from "@/lib/types";

const API = "/api/backend";

// ── 推理 SSE 钩子 ─────────────────────────────────────────────

export function useInference() {
    const [steps, setSteps] = useState<ThoughtStep[]>([]);
    const [command, setCommand] = useState<ActionCommand | null>(null);
    const [running, setRunning] = useState(false);
    const [currentState, setCurrentState] = useState("IDLE");
    const [riskScore, setRiskScore] = useState(0);
    const controllerRef = useRef<AbortController | null>(null);

    const runInference = useCallback(async (scenario: Scenario) => {
        if (controllerRef.current) controllerRef.current.abort();
        const controller = new AbortController();
        controllerRef.current = controller;

        setSteps([]);
        setCommand(null);
        setRunning(true);
        setCurrentState("OBSERVING");

        try {
            const res = await fetch(`${API}/inference`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ scenario }),
                signal: controller.signal,
            });

            const reader = res.body!.getReader();
            const decoder = new TextDecoder();
            let buf = "";

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                buf += decoder.decode(value, { stream: true });
                const lines = buf.split("\n");
                buf = lines.pop() ?? "";

                for (const line of lines) {
                    if (!line.startsWith("data: ")) continue;
                    const raw = line.slice(6);
                    try {
                        const evt = JSON.parse(raw);
                        if (evt.type === "thought_step") {
                            const step = evt as ThoughtStep & { type: string };
                            setCurrentState(step.state);
                            setRiskScore(step.risk_score);
                            setSteps((prev) => [...prev, step]);
                        } else if (evt.type === "final_command") {
                            setCommand(evt.command as ActionCommand);
                        } else if (evt.type === "done") {
                            setRunning(false);
                        }
                    } catch { /* ignore parse errors */ }
                }
            }
        } catch (e: unknown) {
            if (e instanceof Error && e.name !== "AbortError") console.error(e);
        } finally {
            setRunning(false);
        }
    }, []);

    const stop = useCallback(() => {
        controllerRef.current?.abort();
        setRunning(false);
    }, []);

    return { steps, command, running, currentState, riskScore, runInference, stop };
}

// ── 传感器触发钩子 ────────────────────────────────────────────

export function useTelemetry() {
    const [batches, setBatches] = useState<TelemetryBatch[]>([]);
    const [latest, setLatest] = useState<TelemetryBatch | null>(null);

    const trigger = useCallback(async (scenario: Scenario) => {
        const res = await fetch(`${API}/telemetry/trigger`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ scenario }),
        });
        const batch: TelemetryBatch = await res.json();
        setLatest(batch);
        setBatches((prev) => [batch, ...prev].slice(0, 50));
        return batch;
    }, []);

    return { latest, batches, trigger };
}
