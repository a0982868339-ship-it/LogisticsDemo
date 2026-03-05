"""tests/test_agent_graph.py — T5 Agent 决策图单元测试（全 Mock LLM）"""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from app.core.agent_graph import (
    observe_node,
    plan_node,
    retrieve_node,
    route_after_safety,
    safety_guard_node,
    output_node,
)
from app.models.schemas import (
    AgentSession,
    AgentState,
    ChunkMetadata,
    CommandStatus,
    SensorType,
    SeverityLevel,
    SOPChunk,
    Telemetry,
)
from app.simulator.sensor_simulator import TelemetryBatch, generate_sensor_event


# ─────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────

def _make_state(scenario: str = "salt_spray") -> dict:
    return {
        "session": AgentSession(),
        "telemetry_batch": generate_sensor_event(scenario),
        "risk_score": 0.0,
        "retrieved_chunks": [],
        "action_plan": [],
        "safety_verdict": "PASS",
        "safety_reason": "",
        "final_command": None,
        "replan_count": 0,
        "llm_client": None,
        "rag_engine": None,
    }


def _mock_sop_chunks() -> list[SOPChunk]:
    return [
        SOPChunk(
            content=(
                "当盐雾浓度超过15mg/m³时，立即暂停所有室外及敞开式区域作业，"
                "机器人收回至1号干燥仓进行表面清理，并启动N₂吹扫保护模式。"
            ),
            metadata=ChunkMetadata(
                file_ref="12_维护保养手册.md",
                doc_title="巡检机器人维护保养手册",
                section_path="3 > 高盐雾环境维护",
                severity=SeverityLevel.HIGH,
                tags=["盐雾", "高温"],
            ),
        ),
    ]


def _mock_llm(action_list: list[dict]) -> MagicMock:
    """返回固定 JSON 的 Mock LLM"""
    mock = MagicMock()
    mock.invoke.return_value.content = json.dumps(action_list, ensure_ascii=False)
    return mock


def _mock_rag(chunks: list[SOPChunk]) -> MagicMock:
    mock = MagicMock()
    mock.semantic_search.return_value = chunks
    return mock


# ─────────────────────────────────────────────────────────────────
# observe_node 测试
# ─────────────────────────────────────────────────────────────────

class TestObserveNode:
    def test_risk_score_is_computed(self):
        state = _make_state("salt_spray")
        out = observe_node(state)
        assert out["risk_score"] > 0, "盐雾场景风险评分应>0"

    def test_emergency_flag_triggered_for_hazmat(self):
        state = _make_state("hazmat")
        out = observe_node(state)
        assert out["session"].is_emergency is True

    def test_observe_adds_thought_step(self):
        state = _make_state("normal")
        out = observe_node(state)
        assert len(out["session"].history_logs) == 1
        assert "[感知]" in out["session"].history_logs[0].thought

    def test_normal_scenario_no_emergency(self):
        """正常场景风险评分低，不触发紧急模式"""
        state = _make_state("normal")
        out = observe_node(state)
        # 正常场景所有值均在阈值以内，is_anomaly=False → risk_score 很低
        assert out["session"].is_emergency is False

    def test_risk_score_formula(self):
        """手动构造已知输入，验证分数大小（仅范围检验）"""
        state = _make_state("salt_spray")
        out = observe_node(state)
        # salt_spray(异常): 40×0.9=36; visual(异常): 60×0.8=48; anomaly_coeff=2×5=10 → at least 36
        assert out["risk_score"] >= 36.0


# ─────────────────────────────────────────────────────────────────
# retrieve_node 测试
# ─────────────────────────────────────────────────────────────────

class TestRetrieveNode:
    def test_calls_rag_search(self):
        state = _make_state("salt_spray")
        state = observe_node(state)
        chunks = _mock_sop_chunks()
        state["rag_engine"] = _mock_rag(chunks)

        out = retrieve_node(state)
        assert len(out["retrieved_chunks"]) == 1
        state["rag_engine"].semantic_search.assert_called_once()

    def test_adds_retrieval_step(self):
        state = _make_state("salt_spray")
        state = observe_node(state)
        state["rag_engine"] = _mock_rag(_mock_sop_chunks())
        out = retrieve_node(state)
        last_step = out["session"].history_logs[-1]
        assert "[检索]" in last_step.thought


# ─────────────────────────────────────────────────────────────────
# safety_guard_node 测试
# ─────────────────────────────────────────────────────────────────

class TestSafetyGuardNode:
    def test_blocks_prohibited_action_wipe_first(self):
        """场景B：'先擦拭液体' 应被拒绝"""
        state = _make_state("hazmat")
        state = observe_node(state)
        state["retrieved_chunks"] = _mock_sop_chunks()
        state["action_plan"] = [
            {"seq": 1, "device": "robot_main", "action": "先擦拭液体", "params": {}, "sop_clause": "wrong"},
            {"seq": 2, "device": "robot_main", "action": "cut_power", "params": {}, "sop_clause": "correct"},
        ]
        state["llm_client"] = _mock_llm(state["action_plan"])

        out = safety_guard_node(state)
        assert out["safety_verdict"] == "FAIL"
        assert "先擦拭" in out["safety_reason"]

    def test_passes_valid_action_plan(self):
        """合法指令应通过安全栅栏"""
        state = _make_state("salt_spray")
        state = observe_node(state)
        state["retrieved_chunks"] = _mock_sop_chunks()
        state["action_plan"] = [
            {"seq": 1, "device": "robot_main", "action": "suspend_outdoor_operations", "params": {}, "sop_clause": "P3.1"},
            {"seq": 2, "device": "robot_main", "action": "move_to_location", "params": {"target": "DRY_ROOM_01"}, "sop_clause": "P3.2"},
        ]
        out = safety_guard_node(state)
        assert out["safety_verdict"] == "PASS"

    def test_blocks_disable_safety_action(self):
        state = _make_state("hazmat")
        state = observe_node(state)
        state["action_plan"] = [
            {"seq": 1, "device": "sensor_01", "action": "disable_safety", "params": {}, "sop_clause": ""},
        ]
        out = safety_guard_node(state)
        assert out["safety_verdict"] == "FAIL"

    def test_guard_adds_thought_step(self):
        state = _make_state("normal")
        state = observe_node(state)
        state["action_plan"] = []
        out = safety_guard_node(state)
        last = out["session"].history_logs[-1]
        assert "[验证]" in last.thought


# ─────────────────────────────────────────────────────────────────
# output_node 测试
# ─────────────────────────────────────────────────────────────────

class TestOutputNode:
    def test_output_produces_action_command(self):
        state = _make_state("salt_spray")
        state = observe_node(state)
        state["retrieved_chunks"] = _mock_sop_chunks()
        state["action_plan"] = [
            {"seq": 1, "device": "robot_main", "action": "suspend_outdoor_operations", "params": {}, "sop_clause": "P3.1"},
        ]
        state["safety_verdict"] = "PASS"

        out = output_node(state)
        cmd = out["final_command"]
        assert cmd is not None
        assert cmd.safety_verified is True
        assert cmd.status == CommandStatus.EXECUTING
        assert len(cmd.instructions) == 1

    def test_session_state_is_done_after_output(self):
        state = _make_state("salt_spray")
        state = observe_node(state)
        state["action_plan"] = []
        state["retrieved_chunks"] = []
        state["safety_verdict"] = "PASS"
        out = output_node(state)
        assert out["session"].current_state == AgentState.DONE


# ─────────────────────────────────────────────────────────────────
# route_after_safety 测试
# ─────────────────────────────────────────────────────────────────

class TestRouteAfterSafety:
    def test_pass_routes_to_output(self):
        state = _make_state()
        state["safety_verdict"] = "PASS"
        state["replan_count"] = 0
        assert route_after_safety(state) == "output_node"

    def test_fail_routes_to_replan_if_under_limit(self):
        state = _make_state()
        state["safety_verdict"] = "FAIL"
        state["replan_count"] = 0
        route = route_after_safety(state)
        assert route == "plan_node"
        assert state["replan_count"] == 1  # 计数器递增

    def test_fail_routes_to_end_if_over_limit(self):
        from langgraph.graph import END
        state = _make_state()
        state["safety_verdict"] = "FAIL"
        state["replan_count"] = 3  # 已达 max_replan_count
        route = route_after_safety(state)
        assert route == END
        assert state["final_command"].status == CommandStatus.BLOCKED

    def test_replanning_increments_counter(self):
        state = _make_state()
        state["safety_verdict"] = "FAIL"
        state["replan_count"] = 1
        route_after_safety(state)
        assert state["replan_count"] == 2
