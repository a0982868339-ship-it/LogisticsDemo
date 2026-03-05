"""会话管理路由"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.models.schemas import AgentSession

router = APIRouter()

# 内存 KV（Demo 用，生产换 Redis/DB）
_sessions: dict[str, AgentSession] = {}


class CreateSessionResponse(BaseModel):
    session_id: str
    message: str


@router.post("", response_model=CreateSessionResponse)
def create_session():
    """创建新的 Agent 会话"""
    session = AgentSession()
    _sessions[session.session_id] = session
    return CreateSessionResponse(
        session_id=session.session_id,
        message="会话创建成功",
    )


@router.get("/{session_id}")
def get_session(session_id: str):
    """获取会话详情（包含思考轨迹）"""
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="会话不存在")
    return _sessions[session_id].model_dump()
