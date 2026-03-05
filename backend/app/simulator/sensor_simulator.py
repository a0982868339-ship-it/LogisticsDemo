"""
传感器模拟器 — Environment Simulator

提供两种使用方式：
1. generate_sensor_event(scenario)  → 一次性生成 TelemetryBatch
2. SensorStreamSimulator             → 异步生成器，用于 SSE 实时推流
"""
from __future__ import annotations

import asyncio
import random
from datetime import datetime

from app.config import settings
from app.models.schemas import SensorType, Telemetry, TelemetryBatch


# ─────────────────────────────────────────────────────────────────
# 场景定义
# ─────────────────────────────────────────────────────────────────

# 每个 scenario 包含若干传感器的参数区间
_SCENARIO_CONFIG: dict[str, list[dict]] = {
    "normal": [
        {"sensor_type": SensorType.TEMP_HUMIDITY, "value_range": (22.0, 28.0), "unit": "°C", "zone_id": "ZONE-A"},
        {"sensor_type": SensorType.SALT_SPRAY,    "value_range": (1.0, 5.0),   "unit": "mg/m³", "zone_id": "ZONE-M"},
        {"sensor_type": SensorType.VOC,           "value_range": (0.1, 0.5),   "unit": "mg/m³", "zone_id": "ZONE-A"},
    ],
    # ── 场景A：三亚高盐雾 ───────────────────────────────────────
    "salt_spray": [
        {"sensor_type": SensorType.TEMP_HUMIDITY, "value_range": (35.0, 40.0), "unit": "°C",    "zone_id": "ZONE-M"},
        {"sensor_type": SensorType.SALT_SPRAY,    "value_range": (16.0, 28.0), "unit": "mg/m³", "zone_id": "ZONE-M"},   # > 15 阈值
        {"sensor_type": SensorType.VOC,           "value_range": (0.2, 0.6),   "unit": "mg/m³", "zone_id": "ZONE-M"},
        {
            "sensor_type": SensorType.VISUAL,
            "value_static": "室外机器人表面检测到盐雾积累，电气接头区域有白色结晶析出，湿度偏高",
            "zone_id": "ZONE-M",
        },
    ],
    # ── 场景B：美妆仓液体泄漏 + 裸露电路 ──────────────────────
    "hazmat": [
        {"sensor_type": SensorType.VOC,           "value_range": (1.5, 3.0),   "unit": "mg/m³", "zone_id": "ZONE-B"},   # > 1.0 阈值
        {"sensor_type": SensorType.TEMP_HUMIDITY, "value_range": (28.0, 32.0), "unit": "°C",    "zone_id": "ZONE-B"},
        {
            "sensor_type": SensorType.VISUAL,
            "value_static": (
                "视觉识别到货架底部存在液体泄漏，疑似香水（酒精基成分），"
                "半径2m内存在电路裸露风险，变压器外壳有焦糊气味"
            ),
            "zone_id": "ZONE-B",
        },
    ],
    # ── 冷链超温 ────────────────────────────────────────────────
    "cold_chain_alarm": [
        {"sensor_type": SensorType.TEMP_HUMIDITY, "value_range": (12.0, 16.0), "unit": "°C", "zone_id": "ZONE-C"},  # > 8°C 告警
        {"sensor_type": SensorType.VOC,           "value_range": (0.1, 0.3),   "unit": "mg/m³", "zone_id": "ZONE-C"},
        {
            "sensor_type": SensorType.VISUAL,
            "value_static": "冷藏区CK-C03门封破损，冷链货物表面有霜融现象",
            "zone_id": "ZONE-C",
        },
    ],
}


# ─────────────────────────────────────────────────────────────────
# 核心函数
# ─────────────────────────────────────────────────────────────────

def generate_sensor_event(
    scenario: str = "normal",
    zone_override: str | None = None,
) -> TelemetryBatch:
    """
    生成一批模拟传感器数据。

    Args:
        scenario: "normal" | "salt_spray" | "hazmat" | "cold_chain_alarm"
        zone_override: 若指定，覆盖所有传感器的 zone_id

    Returns:
        TelemetryBatch
    """
    config = _SCENARIO_CONFIG.get(scenario, _SCENARIO_CONFIG["normal"])
    readings: list[Telemetry] = []

    for sensor_cfg in config:
        zone = zone_override or sensor_cfg["zone_id"]

        # 静态字符串值（视觉传感器）
        if "value_static" in sensor_cfg:
            readings.append(
                Telemetry(
                    sensor_type=sensor_cfg["sensor_type"],
                    value=sensor_cfg["value_static"],
                    unit="",
                    zone_id=zone,
                    is_anomaly=True,
                )
            )
        else:
            lo, hi = sensor_cfg["value_range"]
            val = round(random.uniform(lo, hi), 2)
            is_anomaly = _check_anomaly(sensor_cfg["sensor_type"], val)
            readings.append(
                Telemetry(
                    sensor_type=sensor_cfg["sensor_type"],
                    value=val,
                    unit=sensor_cfg.get("unit", ""),
                    zone_id=zone,
                    is_anomaly=is_anomaly,
                )
            )

    return TelemetryBatch(
        scenario=scenario,
        readings=readings,
        triggered_at=datetime.utcnow(),
    )


def _check_anomaly(sensor_type: SensorType, value: float) -> bool:
    """基于阈值判断是否为异常读数"""
    if sensor_type == SensorType.SALT_SPRAY:
        return value > settings.salt_spray_threshold
    if sensor_type == SensorType.VOC:
        return value > settings.voc_threshold
    if sensor_type == SensorType.TEMP_HUMIDITY:
        return value > settings.temp_max or value > settings.humidity_max
    return False


def get_risk_score_from_batch(batch: TelemetryBatch) -> float:
    """
    计算 PRD 定义的风险评分：
        RiskScore = Σ(Significance_i × Weight_i) + Anomaly_Coefficient

    权重定义：
        SALT_SPRAY  → significance=40, weight=0.9
        VOC         → significance=50, weight=1.0
        TEMP        → significance=30, weight=0.7
        VISUAL      → significance=60, weight=0.8 (异常时)
        Anomaly_Coefficient = 异常传感器数量 × 5
    """
    _weights: dict[SensorType, tuple[float, float]] = {
        SensorType.SALT_SPRAY:    (40.0, 0.9),
        SensorType.VOC:           (50.0, 1.0),
        SensorType.TEMP_HUMIDITY: (30.0, 0.7),
        SensorType.VISUAL:        (60.0, 0.8),
    }

    score = 0.0
    anomaly_count = 0

    for t in batch.readings:
        sig, weight = _weights.get(t.sensor_type, (20.0, 0.5))
        if t.is_anomaly:
            score += sig * weight
            anomaly_count += 1

    # Anomaly Coefficient
    score += anomaly_count * 5.0
    return round(score, 2)


# ─────────────────────────────────────────────────────────────────
# 异步流生成器（SSE 用）
# ─────────────────────────────────────────────────────────────────

class SensorStreamSimulator:
    """异步传感器数据流，用于 SSE 实时推送"""

    def __init__(self, scenario: str = "normal", interval_seconds: float = 2.0):
        self.scenario = scenario
        self.interval = interval_seconds
        self._running = False

    async def stream(self):
        """异步生成器，周期性产出 TelemetryBatch"""
        self._running = True
        while self._running:
            yield generate_sensor_event(self.scenario)
            await asyncio.sleep(self.interval)

    def stop(self):
        self._running = False
