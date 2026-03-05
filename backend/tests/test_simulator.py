"""tests/test_simulator.py — T4 传感器模拟器单元测试"""
from __future__ import annotations

import pytest

from app.models.schemas import SensorType, TelemetryBatch
from app.simulator.sensor_simulator import (
    generate_sensor_event,
    get_risk_score_from_batch,
)


class TestNormalScenario:
    def test_returns_telemetry_batch(self):
        batch = generate_sensor_event("normal")
        assert isinstance(batch, TelemetryBatch)

    def test_normal_scenario_conforms_to_schema(self):
        batch = generate_sensor_event("normal")
        assert batch.scenario == "normal"
        assert len(batch.readings) >= 1
        for t in batch.readings:
            assert t.sensor_type in SensorType
            assert t.zone_id

    def test_normal_no_anomalies(self):
        """正常场景下，所有传感器读数应在合规区间内"""
        for _ in range(10):  # 多次随机抽样
            batch = generate_sensor_event("normal")
            salt_readings = [t for t in batch.readings if t.sensor_type == SensorType.SALT_SPRAY]
            for t in salt_readings:
                assert isinstance(t.value, float)
                assert t.value <= 15.0, f"正常场景盐雾不应超阈值: {t.value}"


class TestSaltSprayScenario:
    def test_salt_spray_value_exceeds_threshold(self):
        """场景A：盐雾浓度必须 > 15 mg/m³"""
        for _ in range(10):
            batch = generate_sensor_event("salt_spray")
            salt = next(t for t in batch.readings if t.sensor_type == SensorType.SALT_SPRAY)
            assert salt.value > 15.0, f"场景A盐雾必须>15，实际: {salt.value}"

    def test_salt_spray_is_flagged_anomaly(self):
        for _ in range(5):
            batch = generate_sensor_event("salt_spray")
            salt = next(t for t in batch.readings if t.sensor_type == SensorType.SALT_SPRAY)
            assert salt.is_anomaly is True

    def test_salt_spray_has_visual_description(self):
        batch = generate_sensor_event("salt_spray")
        visual = next((t for t in batch.readings if t.sensor_type == SensorType.VISUAL), None)
        assert visual is not None
        assert isinstance(visual.value, str)
        assert "盐雾" in visual.value or "结晶" in visual.value

    def test_salt_spray_scenario_label(self):
        batch = generate_sensor_event("salt_spray")
        assert batch.scenario == "salt_spray"


class TestHazmatScenario:
    def test_voc_exceeds_threshold(self):
        """场景B：VOC 必须 > 1.0 mg/m³"""
        for _ in range(10):
            batch = generate_sensor_event("hazmat")
            voc = next(t for t in batch.readings if t.sensor_type == SensorType.VOC)
            assert float(voc.value) > 1.0, f"场景B VOC必须>1.0，实际: {voc.value}"

    def test_visual_contains_liquid_leak_and_circuit(self):
        batch = generate_sensor_event("hazmat")
        visual = next((t for t in batch.readings if t.sensor_type == SensorType.VISUAL), None)
        assert visual is not None, "场景B应有视觉传感器"
        text = str(visual.value)
        assert "液体泄漏" in text or "泄漏" in text
        assert "电路" in text or "电" in text

    def test_hazmat_batch_has_multiple_sensors(self):
        batch = generate_sensor_event("hazmat")
        assert len(batch.readings) >= 2


class TestRiskScoreCalculation:
    def test_normal_scenario_low_risk(self):
        batch = generate_sensor_event("normal")
        score = get_risk_score_from_batch(batch)
        # 正常场景无异常，score 应接近 0
        assert score <= 20.0, f"正常场景风险评分过高: {score}"

    def test_salt_spray_scenario_elevated_risk(self):
        score_sum = 0.0
        trials = 5
        for _ in range(trials):
            batch = generate_sensor_event("salt_spray")
            score_sum += get_risk_score_from_batch(batch)
        avg = score_sum / trials
        assert avg > 20.0, f"场景A平均风险评分应>20，实际: {avg}"

    def test_hazmat_scenario_highest_risk(self):
        score_sum = 0.0
        trials = 5
        for _ in range(trials):
            batch = generate_sensor_event("hazmat")
            score_sum += get_risk_score_from_batch(batch)
        avg = score_sum / trials
        # VOC异常(50×1.0) + VISUAL异常(60×0.8) + anomaly_coeff = 50+48+10 = 108
        assert avg >= 50.0, f"场景B平均风险评分应≥50，实际: {avg}"

    def test_risk_score_formula_manual(self):
        """手动构造已知异常批次，验证公式结果"""
        from app.models.schemas import Telemetry
        from datetime import datetime

        batch = TelemetryBatch(
            scenario="test",
            readings=[
                Telemetry(
                    sensor_type=SensorType.SALT_SPRAY,
                    value=20.0,
                    unit="mg/m³",
                    zone_id="ZONE-M",
                    is_anomaly=True,        # significance=40, weight=0.9 → 36
                ),
                Telemetry(
                    sensor_type=SensorType.VOC,
                    value=2.0,
                    unit="mg/m³",
                    zone_id="ZONE-M",
                    is_anomaly=True,        # significance=50, weight=1.0 → 50
                ),
            ],
        )
        # Expected: (40×0.9) + (50×1.0) + 2×5 = 36 + 50 + 10 = 96.0
        score = get_risk_score_from_batch(batch)
        assert score == pytest.approx(96.0, abs=0.1)
