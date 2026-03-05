"""Agent 推理路由（SSE 流式输出思考链）"""
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.models.schemas import AgentSession, AgentState

router = APIRouter()

_sessions: dict[str, AgentSession] = {}


class InferenceRequest(BaseModel):
    session_id: str | None = None
    scenario: str = "normal"
    zone_override: str | None = None


@router.post("")
async def run_inference(req: InferenceRequest):
    """
    运行 Agent 推理，SSE 流式输出推理轨迹（Thought→Action→Observation）。
    """
    from app.simulator.sensor_simulator import generate_sensor_event
    from app.core.agent_graph import get_agent_graph

    # 创建或复用会话
    session = AgentSession()
    if req.session_id and req.session_id in _sessions:
        session = _sessions[req.session_id]
    else:
        _sessions[session.session_id] = session

    telemetry_batch = generate_sensor_event(req.scenario, req.zone_override)

    async def _stream():
        graph = get_agent_graph()

        initial_state = {
            "session": session,
            "telemetry_batch": telemetry_batch,
            "risk_score": 0.0,
            "retrieved_chunks": [],
            "action_plan": [],
            "safety_verdict": "PASS",
            "safety_reason": "",
            "final_command": None,
            "replan_count": 0,
        }

        prev_step_count = 0

        # 流式执行图，每个节点执行后输出新产生的 ThoughtStep
        async for event in graph.astream(initial_state, stream_mode="values"):
            current_session: AgentSession = event.get("session", session)
            steps = current_session.history_logs

            # 输出新增的 step
            for step in steps[prev_step_count:]:
                payload = {
                    "type": "thought_step",
                    "step_index": step.step_index,
                    "thought": step.thought,
                    "action": step.action,
                    "observation": step.observation,
                    "sop_references": step.sop_references,
                    "state": current_session.current_state.value,
                    "risk_score": current_session.risk_score,
                }
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            prev_step_count = len(steps)

        # 最终发送指令输出
        final_state = event if event else {}
        cmd = final_state.get("final_command")
        if cmd:
            yield f"data: {json.dumps({'type': 'final_command', 'command': cmd.model_dump(mode='json')}, ensure_ascii=False)}\n\n"

        yield "data: {\"type\": \"done\"}\n\n"

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
