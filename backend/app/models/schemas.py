"""
PRD 四大实体的 Pydantic 数据模型

- SOPChunk      : 知识库碎片
- AgentSession  : Agent 会话（思考轨迹）
- Telemetry     : 传感器遥测
- ActionCommand : 下发给硬件的最终指令
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


# ─────────────────────────────────────────────────────────────────
# 枚举
# ─────────────────────────────────────────────────────────────────

class SeverityLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class SensorType(str, Enum):
    TEMP_HUMIDITY = "TEMP_HUMIDITY"
    SALT_SPRAY = "SALT_SPRAY"
    VOC = "VOC"
    VISUAL = "VISUAL"


class AgentState(str, Enum):
    IDLE = "IDLE"
    OBSERVING = "OBSERVING"
    RETRIEVING = "RETRIEVING"
    PLANNING = "PLANNING"
    VERIFYING = "VERIFYING"
    EXECUTING = "EXECUTING"
    REPLANNING = "REPLANNING"
    DONE = "DONE"
    ABORTED = "ABORTED"


class CommandStatus(str, Enum):
    PENDING = "PENDING"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"   # Safety Guard 拦截


# ─────────────────────────────────────────────────────────────────
# SOPChunk — 知识库碎片
# ─────────────────────────────────────────────────────────────────

class ChunkMetadata(BaseModel):
    """嵌入到 ChromaDB 的元数据"""
    file_ref: str = Field(description="来源文件名，如 '06_异常货物处置标准操作程序.md'")
    doc_title: str = Field(description="文档标题")
    section_path: str = Field(description="章节路径，如 '3.1 > 极端气候自保护'")
    severity: SeverityLevel = SeverityLevel.MEDIUM
    zone_ids: list[str] = Field(default_factory=list, description="适用区域 ID，如 ['ZONE-E', 'ZONE-C']")
    tags: list[str] = Field(default_factory=list, description="关键词标签，如 ['盐雾', '高温', '危化品']")


class SOPChunk(BaseModel):
    """知识库碎片"""
    chunk_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    content: str = Field(min_length=10, description="碎片文本内容")
    metadata: ChunkMetadata
    char_count: int = 0

    def model_post_init(self, __context: Any) -> None:
        self.char_count = len(self.content)


# ─────────────────────────────────────────────────────────────────
# Telemetry — 传感器遥测
# ─────────────────────────────────────────────────────────────────

class Telemetry(BaseModel):
    """单条传感器遥测数据"""
    sensor_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    sensor_type: SensorType
    value: float | str = Field(description="数值（温湿度/浓度）或视觉描述字符串")
    unit: str = ""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    zone_id: str = Field(description="传感器所在区域，如 'ZONE-E'")
    is_anomaly: bool = False

    @field_validator("value")
    @classmethod
    def _check_value(cls, v: Any) -> Any:
        if not isinstance(v, (int, float, str)):
            raise ValueError("value must be a number or string")
        return v


class TelemetryBatch(BaseModel):
    """一次感知触发包含的所有传感器数据"""
    batch_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    scenario: str = "normal"
    readings: list[Telemetry]
    triggered_at: datetime = Field(default_factory=datetime.utcnow)


# ─────────────────────────────────────────────────────────────────
# AgentSession — 会话 & 思考轨迹
# ─────────────────────────────────────────────────────────────────

class ThoughtStep(BaseModel):
    """Agent 一步思考：Thought → Action → Observation"""
    step_index: int
    thought: str = ""
    action: str = ""
    observation: str = ""
    sop_references: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class AgentSession(BaseModel):
    """完整的 Agent 会话记录"""
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    current_state: AgentState = AgentState.IDLE
    is_emergency: bool = False
    replan_count: int = 0
    history_logs: list[ThoughtStep] = Field(default_factory=list)
    risk_score: float = 0.0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    def add_step(self, step: ThoughtStep) -> None:
        self.history_logs.append(step)
        self.updated_at = datetime.utcnow()


# ─────────────────────────────────────────────────────────────────
# ActionCommand — 最终硬件指令
# ─────────────────────────────────────────────────────────────────

class HardwareInstruction(BaseModel):
    """单条硬件指令（模拟 PLC/ROS 消息）"""
    seq: int = Field(description="执行顺序，从 1 开始")
    device: str = Field(description="目标设备，如 'robot_main', 'relay_01'")
    action: str = Field(description="动作标识，如 'move_to_location', 'cut_power'")
    params: dict[str, Any] = Field(default_factory=dict)
    sop_clause: str = Field(description="对应 SOP 条款，如 '第3.1节 STEP 1'")
    legal_basis: str = Field(default="", description="法律依据，如 '《危化品安全管理条例》第69条'")


class ActionCommand(BaseModel):
    """完整指令包（最终下发）"""
    cmd_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    instructions: list[HardwareInstruction]
    status: CommandStatus = CommandStatus.PENDING
    risk_score: float = 0.0
    safety_verified: bool = False
    json_payload: dict[str, Any] = Field(default_factory=dict)
    sop_reference: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)

    def model_post_init(self, __context: Any) -> None:
        """序列化完整 JSON payload"""
        self.json_payload = {
            "cmd_id": self.cmd_id,
            "session_id": self.session_id,
            "risk_score": self.risk_score,
            "safety_verified": self.safety_verified,
            "instructions": [inst.model_dump() for inst in self.instructions],
        }
