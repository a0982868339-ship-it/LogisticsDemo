"""
tests/test_integration.py — Step 2: 完整 Agent 链路集成测试
=============================================================
真实调用：
  - 传感器模拟器（无 Mock）
  - ChromaDB + ONNX 向量检索（复用已建好的索引）
  - GPT-4o-mini（真实 LLM 规划）
  - LangGraph 完整状态图执行

标记: @pytest.mark.integration
运行方式（需提前执行 build_index）：
  /opt/anaconda3/envs/crypto_bot/bin/python -m pytest tests/test_integration.py -v -m integration --tb=short -s
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

# 真实集成测试 marker
pytestmark = pytest.mark.integration


# ─────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def real_rag(tmp_path_factory):
    """真实 RAG 引擎，复用 ONNX embedding，构建临时索引"""
    from app.core.rag_engine import RAGEngine
    chroma_dir = tmp_path_factory.mktemp("chroma_integration")
    docs_dir = Path(__file__).parent.parent.parent / "docs" / "巡检手册"
    engine = RAGEngine(docs_dir=docs_dir, chroma_dir=chroma_dir)
    print(f"\n⏳ 构建向量索引...")
    n = engine.build_index(force_rebuild=True)
    print(f"✅ 索引完成: {n} 个 chunk")
    return engine


@pytest.fixture(scope="module")
def real_llm():
    """真实 GPT-4o-mini 客户端（从 .env 读取配置）"""
    from app.config import settings
    from langchain_openai import ChatOpenAI
    print(f"\n🤖 LLM: {settings.openai_model_name} @ {settings.openai_base_url}")
    return ChatOpenAI(
        model=settings.openai_model_name,
        base_url=settings.openai_base_url,
        api_key=settings.openai_api_key,
        temperature=0.1,
        timeout=30,
    )


# ─────────────────────────────────────────────────────────────────
# 单节点验证（有 RAG 无 LLM）
# ─────────────────────────────────────────────────────────────────

class TestObserveAndRetrieve:
    """验证 observe + retrieve 节点在真实 RAG 下正常运作"""

    def test_observe_node_with_real_telemetry(self):
        """observe_node 应正确计算盐雾场景风险评分"""
        from app.core.agent_graph import observe_node
        from app.models.schemas import AgentSession
        from app.simulator.sensor_simulator import generate_sensor_event

        batch = generate_sensor_event("salt_spray")
        state = {
            "session": AgentSession(),
            "telemetry_batch": batch,
        }
        out = observe_node(state)
        print(f"\n  盐雾场景 RiskScore = {out['risk_score']:.1f}")
        assert out["risk_score"] >= 30.0

    def test_retrieve_node_with_real_rag(self, real_rag):
        """retrieve_node 应通过真实 ChromaDB 召回相关 SOP"""
        from app.core.agent_graph import observe_node, retrieve_node
        from app.models.schemas import AgentSession
        from app.simulator.sensor_simulator import generate_sensor_event

        batch = generate_sensor_event("hazmat")
        state = {
            "session": AgentSession(),
            "telemetry_batch": batch,
            "rag_engine": real_rag,
        }
        state = observe_node(state)
        out = retrieve_node(state)
        chunks = out["retrieved_chunks"]
        print(f"\n  危化品场景召回 {len(chunks)} 个 chunk:")
        for c in chunks:
            print(f"    [{c.metadata.severity.value}] {c.metadata.file_ref}")
        assert len(chunks) >= 1, "至少应召回1个 SOP chunk"


# ─────────────────────────────────────────────────────────────────
# 完整链路测试（真实 LLM）
# ─────────────────────────────────────────────────────────────────

class TestFullPipeline:
    """真实 LLM + 真实 RAG 的完整 Agent 链路测试"""

    def _run_full_pipeline(self, scenario: str, real_rag, real_llm) -> dict:
        """运行完整状态图，返回最终 state"""
        from app.core.agent_graph import build_agent_graph
        from app.models.schemas import AgentSession
        from app.simulator.sensor_simulator import generate_sensor_event

        graph = build_agent_graph()
        session = AgentSession()
        batch = generate_sensor_event(scenario)

        initial_state = {
            "session": session,
            "telemetry_batch": batch,
            "risk_score": 0.0,
            "retrieved_chunks": [],
            "action_plan": [],
            "safety_verdict": "PASS",
            "safety_reason": "",
            "final_command": None,
            "replan_count": 0,
            "llm_client": real_llm,
            "rag_engine": real_rag,
        }

        result = graph.invoke(initial_state)
        return result

    def test_normal_scenario_completes(self, real_rag, real_llm):
        """正常场景应顺利完成，产出 ActionCommand"""
        from app.models.schemas import CommandStatus
        result = self._run_full_pipeline("normal", real_rag, real_llm)
        cmd = result["final_command"]
        session = result["session"]

        print(f"\n  [正常场景] 推理步骤: {len(session.history_logs)}")
        print(f"  [正常场景] 指令状态: {cmd.status if cmd else 'None'}")

        assert cmd is not None, "正常场景应产出指令"
        assert cmd.status in (CommandStatus.EXECUTING, CommandStatus.PENDING, CommandStatus.BLOCKED)
        assert len(session.history_logs) >= 3, "应至少有 observe/retrieve/plan 三步"

    def test_salt_spray_scenario_detects_emergency(self, real_rag, real_llm):
        """盐雾场景应触发紧急模式，Agent 推理到高危状态"""
        from app.models.schemas import AgentState
        result = self._run_full_pipeline("salt_spray", real_rag, real_llm)
        session = result["session"]

        print(f"\n  [盐雾场景] is_emergency: {session.is_emergency}")
        print(f"  [盐雾场景] RiskScore: {session.risk_score:.1f}")
        print(f"  [盐雾场景] 最终状态: {session.current_state.value}")

        assert session.is_emergency is True, "盐雾场景应触发紧急模式"
        assert session.risk_score >= 30.0

    def test_hazmat_scenario_produces_safety_focused_plan(self, real_rag, real_llm):
        """危化品场景应产出包含安全措施的行动计划"""
        result = self._run_full_pipeline("hazmat", real_rag, real_llm)
        session = result["session"]
        cmd = result["final_command"]

        print(f"\n  [危化品场景] 推理步骤: {len(session.history_logs)}")
        if cmd:
            print(f"  [危化品场景] 指令数量: {len(cmd.instructions)}")
            for instr in cmd.instructions[:3]:
                print(f"    - {instr.action} ({instr.sop_clause})")

        # 验证推理过程经历了安全校验节点
        thoughts = " ".join(s.thought for s in session.history_logs)
        assert "[验证]" in thoughts, "应经过安全栅栏验证节点"

    def test_llm_generates_valid_json_plan(self, real_rag, real_llm):
        """plan_node 应从 LLM 获取有效的 JSON 指令列表"""
        from app.core.agent_graph import observe_node, retrieve_node, plan_node
        from app.models.schemas import AgentSession
        from app.simulator.sensor_simulator import generate_sensor_event

        batch = generate_sensor_event("salt_spray")
        state = {
            "session": AgentSession(),
            "telemetry_batch": batch,
            "retrieved_chunks": [],
            "action_plan": [],
            "replan_count": 0,
            "llm_client": real_llm,
            "rag_engine": real_rag,
        }
        state = observe_node(state)
        state = retrieve_node(state)
        out = plan_node(state)

        plan = out["action_plan"]
        print(f"\n  [plan_node] LLM 生成 {len(plan)} 条指令:")
        for act in plan[:5]:
            print(f"    [{act.get('seq')}] {act.get('device')} → {act.get('action')}")

        assert isinstance(plan, list), "action_plan 应为 list"
        assert len(plan) >= 1, "LLM 应至少生成1条指令"
        for act in plan:
            assert "seq" in act or "action" in act, f"指令格式异常: {act}"

    def test_safety_guard_works_with_real_llm_output(self, real_rag, real_llm):
        """验证安全栅栏能正确处理 LLM 真实输出（允许 PASS 或 FAIL，但不崩溃）"""
        from app.core.agent_graph import observe_node, retrieve_node, plan_node, safety_guard_node
        from app.models.schemas import AgentSession
        from app.simulator.sensor_simulator import generate_sensor_event

        state = {
            "session": AgentSession(),
            "telemetry_batch": generate_sensor_event("hazmat"),
            "retrieved_chunks": [],
            "action_plan": [],
            "replan_count": 0,
            "llm_client": real_llm,
            "rag_engine": real_rag,
        }
        state = observe_node(state)
        state = retrieve_node(state)
        state = plan_node(state)
        out = safety_guard_node(state)

        verdict = out["safety_verdict"]
        reason = out["safety_reason"]
        print(f"\n  [safety_guard] 裁定: {verdict}")
        print(f"  [safety_guard] 原因: {reason[:80]}")

        assert verdict in ("PASS", "FAIL"), f"裁定值异常: {verdict}"
        assert isinstance(reason, str) and len(reason) > 0


# ─────────────────────────────────────────────────────────────────
# 思考轨迹验证
# ─────────────────────────────────────────────────────────────────

class TestThoughtChainIntegrity:
    def test_full_thought_chain_has_all_stages(self, real_rag, real_llm):
        """完整推理轨迹应包含所有节点的 ThoughtStep"""
        from app.core.agent_graph import build_agent_graph
        from app.models.schemas import AgentSession
        from app.simulator.sensor_simulator import generate_sensor_event

        graph = build_agent_graph()
        result = graph.invoke({
            "session":           AgentSession(),
            "telemetry_batch":   generate_sensor_event("salt_spray"),
            "risk_score":        0.0,
            "retrieved_chunks":  [],
            "action_plan":       [],
            "safety_verdict":    "PASS",
            "safety_reason":     "",
            "final_command":     None,
            "replan_count":      0,
            "llm_client":        real_llm,
            "rag_engine":        real_rag,
        })
        session = result["session"]
        thoughts = [s.thought for s in session.history_logs]
        print(f"\n  推理步骤 ({len(thoughts)} 步):")
        for t in thoughts:
            print(f"    {t[:60]}")

        stage_markers = ["[感知]", "[检索]", "[规划]", "[验证]", "[输出]"]
        found = [m for m in stage_markers if any(m in t for t in thoughts)]
        print(f"  覆盖阶段: {found}")
        assert len(found) >= 4, f"应覆盖至少4个推理阶段，实际: {found}"
