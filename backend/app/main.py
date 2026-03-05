"""
FastAPI 应用入口

路由：
  GET  /health                     健康检查
  POST /sessions                   创建 Agent 会话
  GET  /sessions/{id}              获取会话详情
  POST /telemetry/trigger          触发指定场景传感器数据
  GET  /telemetry/stream           SSE 实时传感器数据流
  POST /inference                  运行 Agent 推理（SSE 流式输出）
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import sessions, telemetry, inference

app = FastAPI(
    title="Zhuoshi-OmniGuard API",
    description="智巡护航具身智能决策中枢 API",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sessions.router,   prefix="/sessions",   tags=["会话管理"])
app.include_router(telemetry.router,  prefix="/telemetry",  tags=["传感器模拟"])
app.include_router(inference.router,  prefix="/inference",  tags=["Agent推理"])


@app.get("/health", tags=["系统"])
def health():
    return {"status": "ok", "service": "Zhuoshi-OmniGuard"}
