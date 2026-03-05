"""tests/test_models.py — T2 数据模型单元测试"""
import pytest
from datetime import datetime

from app.models.schemas import (
    ActionCommand,
    AgentSession,
    AgentState,
    ChunkMetadata,
    CommandStatus,
    HardwareInstruction,
    SensorType,
    SeverityLevel,
    SOPChunk,
    Telemetry,
    TelemetryBatch,
    ThoughtStep,
)


# ─────────────────────────────────────────────────────────────────
# SOPChunk 测试
# ─────────────────────────────────────────────────────────────────

class TestSOPChunk:
    def test_creates_with_required_fields(self):
        meta = ChunkMetadata(
            file_ref="06_异常货物处置标准操作程序.md",
            doc_title="异常货物处置标准操作程序",
            section_path="3. 标准处置流程 > 3.1 P0级处置",
            severity=SeverityLevel.HIGH,
            zone_ids=["ZONE-E"],
            tags=["危化品", "P0"],
        )
        chunk = SOPChunk(content="当发现危化品泄漏时，立即触发P0告警并封锁区域。" * 5, metadata=meta)
        assert chunk.chunk_id  # UUID 自动生成
        assert chunk.char_count == len(chunk.content)
        assert chunk.metadata.severity == SeverityLevel.HIGH

    def test_rejects_empty_content(self):
        with pytest.raises(Exception):
            SOPChunk(
                content="",  # 不满足 min_length=10
                metadata=ChunkMetadata(
                    file_ref="test.md",
                    doc_title="test",
                    section_path="1",
                ),
            )

    def test_char_count_auto_computed(self):
        text = "A" * 500
        meta = ChunkMetadata(file_ref="f.md", doc_title="t", section_path="1")
        chunk = SOPChunk(content=text, metadata=meta)
        assert chunk.char_count == 500

    def test_zone_ids_defaults_to_empty(self):
        meta = ChunkMetadata(file_ref="f.md", doc_title="t", section_path="1")
        chunk = SOPChunk(content="最小合法内容，长度满足约束。", metadata=meta)
        assert chunk.metadata.zone_ids == []


# ─────────────────────────────────────────────────────────────────
# Telemetry 测试
# ─────────────────────────────────────────────────────────────────

class TestTelemetry:
    def test_numeric_value(self):
        t = Telemetry(
            sensor_type=SensorType.SALT_SPRAY,
            value=18.5,
            unit="mg/m³",
            zone_id="ZONE-M",
        )
        assert t.value == 18.5
        assert t.is_anomaly is False
        assert isinstance(t.timestamp, datetime)

    def test_visual_string_value(self):
        t = Telemetry(
            sensor_type=SensorType.VISUAL,
            value="检测到液体泄漏，疑似香水，同时存在电路裸露风险",
            zone_id="ZONE-B",
        )
        assert isinstance(t.value, str)

    def test_invalid_value_type_rejected(self):
        with pytest.raises(Exception):
            Telemetry(
                sensor_type=SensorType.VOC,
                value={"nested": "dict"},  # 非法类型
                zone_id="ZONE-A",
            )

    def test_batch_contains_multiple_readings(self):
        readings = [
            Telemetry(sensor_type=SensorType.TEMP_HUMIDITY, value=38.5, unit="°C", zone_id="ZONE-C"),
            Telemetry(sensor_type=SensorType.SALT_SPRAY, value=20.0, unit="mg/m³", zone_id="ZONE-X"),
        ]
        batch = TelemetryBatch(scenario="salt_spray", readings=readings)
        assert len(batch.readings) == 2
        assert batch.scenario == "salt_spray"


# ─────────────────────────────────────────────────────────────────
# AgentSession 测试
# ─────────────────────────────────────────────────────────────────

class TestAgentSession:
    def test_default_state_is_idle(self):
        session = AgentSession()
        assert session.current_state == AgentState.IDLE
        assert session.is_emergency is False
        assert session.replan_count == 0
        assert session.history_logs == []

    def test_add_step_appends(self):
        session = AgentSession()
        step = ThoughtStep(
            step_index=0,
            thought="检测到盐雾浓度异常",
            action="调用 RAG 检索《高盐雾维护规程》",
            observation="召回3个相关 SOP 片段",
        )
        session.add_step(step)
        assert len(session.history_logs) == 1
        assert session.history_logs[0].thought == "检测到盐雾浓度异常"

    def test_multiple_steps(self):
        session = AgentSession()
        for i in range(5):
            session.add_step(ThoughtStep(step_index=i, thought=f"step_{i}"))
        assert len(session.history_logs) == 5

    def test_emergency_flag(self):
        session = AgentSession(is_emergency=True, risk_score=85.0)
        assert session.is_emergency
        assert session.risk_score == 85.0


# ─────────────────────────────────────────────────────────────────
# ActionCommand 测试
# ─────────────────────────────────────────────────────────────────

class TestActionCommand:
    def _make_instruction(self, seq: int = 1) -> HardwareInstruction:
        return HardwareInstruction(
            seq=seq,
            device="robot_main",
            action="move_to_location",
            params={"target": "DRY_ROOM_01", "speed": 0.5},
            sop_clause="第3.2节 STEP 2",
            legal_basis="《危化品安全管理条例》第69条",
        )

    def test_json_payload_auto_generated(self):
        cmd = ActionCommand(
            session_id="test-session-001",
            instructions=[self._make_instruction()],
            safety_verified=True,
        )
        assert "cmd_id" in cmd.json_payload
        assert "instructions" in cmd.json_payload
        assert len(cmd.json_payload["instructions"]) == 1

    def test_default_status_pending(self):
        cmd = ActionCommand(session_id="s-001", instructions=[])
        assert cmd.status == CommandStatus.PENDING

    def test_blocked_status(self):
        cmd = ActionCommand(
            session_id="s-002",
            instructions=[self._make_instruction()],
            status=CommandStatus.BLOCKED,
        )
        assert cmd.status == CommandStatus.BLOCKED

    def test_instruction_ordering(self):
        instructions = [self._make_instruction(seq=i) for i in [3, 1, 2]]
        cmd = ActionCommand(session_id="s-003", instructions=instructions)
        seqs = [instr.seq for instr in cmd.instructions]
        # 顺序由调用方决定，测试数量正确
        assert len(seqs) == 3
        assert set(seqs) == {1, 2, 3}
