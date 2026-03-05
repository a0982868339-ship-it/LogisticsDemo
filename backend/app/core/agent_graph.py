"""
LangGraph Agent 决策图 — Agentic Orchestrator

状态流: START → observe → retrieve → plan → safety_guard → output → END
              ↑                              ↓(FAIL, ≤max_replan)
              └──────────── replan ──────────┘

每个节点都更新 AgentState 并写入 ThoughtStep，完整保留推理轨迹。
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Literal

from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, StateGraph
from langgraph.checkpoint.memory import MemorySaver

from app.config import settings
from app.models.schemas import (
    ActionCommand,
    AgentSession,
    AgentState,
    CommandStatus,
    HardwareInstruction,
    SOPChunk,
    ThoughtStep,
)
from app.simulator.sensor_simulator import TelemetryBatch, get_risk_score_from_batch


# ─────────────────────────────────────────────────────────────────
# 图状态（TypedDict）
# ─────────────────────────────────────────────────────────────────

from typing import TypedDict


class GraphState(TypedDict, total=False):
    session: AgentSession
    telemetry_batch: TelemetryBatch
    risk_score: float
    retrieved_chunks: list[SOPChunk]
    action_plan: list[dict[str, Any]]        # LLM 生成的初步行动列表
    safety_verdict: Literal["PASS", "FAIL"]
    safety_reason: str
    final_command: ActionCommand | None
    replan_count: int
    llm_client: Any                           # 测试时注入 Mock LLM


# ─────────────────────────────────────────────────────────────────
# 5 个节点
# ─────────────────────────────────────────────────────────────────

def observe_node(state: GraphState) -> GraphState:
    """
    感知节点：解析遥测批次，计算风险评分，判断是否进入紧急模式。
    """
    batch: TelemetryBatch = state["telemetry_batch"]
    session: AgentSession = state["session"]

    risk = get_risk_score_from_batch(batch)
    is_emergency = risk >= 50.0

    # 生成感知摘要
    anomalies = [t for t in batch.readings if t.is_anomaly]
    anomaly_desc = "; ".join(
        f"{t.sensor_type.value}={t.value}{t.unit}" for t in anomalies
    )
    normal_count = len(batch.readings) - len(anomalies)

    thought = (
        f"[感知] 场景：{batch.scenario}  "
        f"读取 {len(batch.readings)} 个传感器，"
        f"发现 {len(anomalies)} 个异常读数：{anomaly_desc or '无'}"
    )
    observation = f"RiskScore={risk:.1f}" + ("（紧急模式激活）" if is_emergency else "")

    session.current_state = AgentState.OBSERVING
    session.is_emergency = is_emergency
    session.risk_score = risk
    session.add_step(ThoughtStep(
        step_index=len(session.history_logs),
        thought=thought,
        action="计算 RiskScore = Σ(Significance×Weight) + AnomalyCoeff",
        observation=observation,
    ))

    return {
        **state,
        "risk_score": risk,
        "session": session,
    }


def retrieve_node(state: GraphState) -> GraphState:
    """
    检索节点：根据遥测数据向量检索相关 SOP chunks。
    """
    from app.core.rag_engine import RAGEngine

    batch: TelemetryBatch = state["telemetry_batch"]
    session: AgentSession = state["session"]
    session.current_state = AgentState.RETRIEVING

    # 构造查询：将异常读数拼接成自然语言
    anomalies = [t for t in batch.readings if t.is_anomaly]
    query_parts = []
    for t in anomalies:
        if t.sensor_type.value == "VISUAL":
            query_parts.append(str(t.value))
        else:
            query_parts.append(f"{t.sensor_type.value}={t.value}{t.unit}")
    query = f"处置：{', '.join(query_parts)}" if query_parts else batch.scenario

    # 调用 RAG（允许测试时传入 mock_rag）
    rag: RAGEngine = state.get("rag_engine")  # type: ignore[assignment]
    if rag is None:
        rag = RAGEngine()

    chunks = rag.semantic_search(query, top_k=5)

    chunk_summary = "\n".join(
        f"  [{i+1}] {c.metadata.section_path} ({c.metadata.file_ref})"
        for i, c in enumerate(chunks)
    )
    session.add_step(ThoughtStep(
        step_index=len(session.history_logs),
        thought=f"[检索] 查询：「{query}」",
        action=f"semantic_search({query!r}, top_k=5)",
        observation=f"召回 {len(chunks)} 个 SOP 片段：\n{chunk_summary}",
        sop_references=[c.metadata.file_ref for c in chunks],
    ))

    return {**state, "retrieved_chunks": chunks, "session": session}


def plan_node(state: GraphState) -> GraphState:
    """
    规划节点：调用 LLM，基于 SOP 生成 ActionPlan（JSON 列表）。
    """
    session: AgentSession = state["session"]
    session.current_state = AgentState.PLANNING

    chunks: list[SOPChunk] = state.get("retrieved_chunks", [])
    batch: TelemetryBatch = state["telemetry_batch"]
    risk = state.get("risk_score", 0.0)
    replan_count = state.get("replan_count", 0)

    # 构造 Prompt
    sop_context = "\n\n".join(
        f"--- SOP [{i+1}] 来源：{c.metadata.section_path} ---\n{c.content[:600]}"
        for i, c in enumerate(chunks)
    )
    replan_hint = f"\n注意：这是第 {replan_count+1} 次规划，需避免之前被安全栅栏拒绝的操作。" if replan_count > 0 else ""

    prompt = f"""你是三亚跨境仓储具身智能机器人的决策大脑。

当前感知数据（场景：{batch.scenario}，风险评分：{risk:.1f}）：
{", ".join(f"{t.sensor_type.value}={t.value}{t.unit}" for t in batch.readings)}

参考 SOP 知识库：
{sop_context}
{replan_hint}

请严格依据上述 SOP，生成一个 JSON 数组格式的行动계划。每项格式如下：
[
  {{
    "seq": 1,
    "device": "robot_main",
    "action": "动作标识",
    "params": {{}},
    "sop_clause": "对应SOP条款",
    "legal_basis": "法律依据（可选）"
  }}
]

只输出 JSON，不要任何解释。"""

    # 调用 LLM（测试时注入 Mock）
    llm = state.get("llm_client")
    if llm is None:
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(
            model=settings.openai_model_name,
            base_url=settings.openai_base_url,
            api_key=settings.openai_api_key,
            temperature=0.1,
        )

    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        raw = response.content.strip()
        # 提取 JSON 数组
        start = raw.find("[")
        end = raw.rfind("]") + 1
        action_plan = json.loads(raw[start:end]) if start >= 0 else []
    except Exception as e:
        action_plan = [
            {
                "seq": 1,
                "device": "robot_main",
                "action": "report_anomaly",
                "params": {"error": str(e)},
                "sop_clause": "fallback",
                "legal_basis": "",
            }
        ]

    session.add_step(ThoughtStep(
        step_index=len(session.history_logs),
        thought=f"[规划] 基于 {len(chunks)} 个SOP片段生成行动计划（第{replan_count+1}次）",
        action=f"LLM.plan({batch.scenario})",
        observation=f"生成 {len(action_plan)} 条指令",
    ))

    return {**state, "action_plan": action_plan, "session": session}


# 安全栅栏禁令关键词（所有语言）
_PROHIBITED_ACTIONS = [
    "先擦拭", "忽略警报", "关闭告警", "先灭火后断电", "用水扑灭危化品",
    "ignore_alarm", "wipe_first", "disable_safety", "bypass_guard",
    "擦拭液体", "先清洁",
]

def safety_guard_node(state: GraphState) -> GraphState:
    """
    安全栅栏节点：检验 ActionPlan 中是否有违反 SOP 禁令的操作。
    """
    session: AgentSession = state["session"]
    session.current_state = AgentState.VERIFYING

    action_plan: list[dict] = state.get("action_plan", [])
    violations: list[str] = []

    for act in action_plan:
        action_str = f"{act.get('action', '')} {json.dumps(act.get('params', {}))}"
        for prohibited in _PROHIBITED_ACTIONS:
            if prohibited.lower() in action_str.lower():
                violations.append(f"指令[{act.get('seq')}] '{act.get('action')}' 触犯禁令：{prohibited}")

    verdict: Literal["PASS", "FAIL"] = "FAIL" if violations else "PASS"
    reason = "; ".join(violations) if violations else "所有指令符合SOP安全规范"

    session.add_step(ThoughtStep(
        step_index=len(session.history_logs),
        thought=f"[验证] 对 {len(action_plan)} 条指令进行安全校验",
        action="safety_guard.verify(action_plan)",
        observation=f"结论：{verdict} — {reason}",
    ))

    return {
        **state,
        "safety_verdict": verdict,
        "safety_reason": reason,
        "session": session,
    }


def output_node(state: GraphState) -> GraphState:
    """
    输出节点：将行动计划封装为 ActionCommand JSON。
    """
    session: AgentSession = state["session"]
    session.current_state = AgentState.EXECUTING

    action_plan: list[dict] = state.get("action_plan", [])
    chunks: list[SOPChunk] = state.get("retrieved_chunks", [])

    instructions = []
    for act in action_plan:
        try:
            instr = HardwareInstruction(
                seq=act.get("seq", 1),
                device=act.get("device", "robot_main"),
                action=act.get("action", "noop"),
                params=act.get("params", {}),
                sop_clause=act.get("sop_clause", ""),
                legal_basis=act.get("legal_basis", ""),
            )
            instructions.append(instr)
        except Exception:
            pass

    sop_ref = "; ".join({c.metadata.file_ref for c in chunks})
    cmd = ActionCommand(
        session_id=session.session_id,
        instructions=instructions,
        status=CommandStatus.EXECUTING,
        risk_score=state.get("risk_score", 0.0),
        safety_verified=True,
        sop_reference=sop_ref,
    )

    session.current_state = AgentState.DONE
    session.add_step(ThoughtStep(
        step_index=len(session.history_logs),
        thought="[输出] 安全校验通过，封装硬件指令包",
        action=f"output_command(cmd_id={cmd.cmd_id[:8]})",
        observation=f"下发 {len(instructions)} 条指令，关联 SOP：{sop_ref}",
    ))

    return {**state, "final_command": cmd, "session": session}


# ─────────────────────────────────────────────────────────────────
# 路由函数
# ─────────────────────────────────────────────────────────────────

def route_after_safety(state: GraphState) -> str:
    """safety_guard 通过 → output；失败且未超限 → plan（重规划）；超限 → aborted"""
    verdict = state.get("safety_verdict", "FAIL")
    replan_count = state.get("replan_count", 0)

    if verdict == "PASS":
        return "output_node"

    if replan_count < settings.max_replan_count:
        # 增加重规划计数
        state["replan_count"] = replan_count + 1
        state["session"].current_state = AgentState.REPLANNING
        return "plan_node"

    # 超过最大重规划次数，强制中止
    state["session"].current_state = AgentState.ABORTED
    state["final_command"] = ActionCommand(
        session_id=state["session"].session_id,
        instructions=[],
        status=CommandStatus.BLOCKED,
        safety_verified=False,
        sop_reference="ABORTED: max replan exceeded",
    )
    return END


# ─────────────────────────────────────────────────────────────────
# 图构建
# ─────────────────────────────────────────────────────────────────

def build_agent_graph():
    """构建并编译 LangGraph 状态图"""
    g = StateGraph(GraphState)

    g.add_node("observe_node",       observe_node)
    g.add_node("retrieve_node",      retrieve_node)
    g.add_node("plan_node",          plan_node)
    g.add_node("safety_guard_node",  safety_guard_node)
    g.add_node("output_node",        output_node)

    g.add_edge(START,                "observe_node")
    g.add_edge("observe_node",       "retrieve_node")
    g.add_edge("retrieve_node",      "plan_node")
    g.add_edge("plan_node",          "safety_guard_node")
    g.add_conditional_edges(
        "safety_guard_node",
        route_after_safety,
        {
            "output_node": "output_node",
            "plan_node":   "plan_node",
            END:           END,
        },
    )
    g.add_edge("output_node", END)

    memory = MemorySaver()
    return g.compile(checkpointer=memory)


# 单例（应用启动时调用）
_compiled_graph = None


def get_agent_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_agent_graph()
    return _compiled_graph
