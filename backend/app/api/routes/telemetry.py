"""传感器模拟路由"""
import asyncio
import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.simulator.sensor_simulator import generate_sensor_event

router = APIRouter()


class TriggerRequest(BaseModel):
    scenario: str = "normal"
    zone_override: str | None = None


@router.post("/trigger")
def trigger_scenario(req: TriggerRequest):
    """手动触发指定场景的传感器数据（一次性）"""
    batch = generate_sensor_event(req.scenario, req.zone_override)
    return batch.model_dump(mode="json")


@router.get("/stream")
async def stream_telemetry(scenario: str = "normal", interval: float = 2.0):
    """SSE: 实时推送模拟传感器数据流"""
    async def _event_generator():
        from app.simulator.sensor_simulator import SensorStreamSimulator
        sim = SensorStreamSimulator(scenario=scenario, interval_seconds=interval)
        async for batch in sim.stream():
            data = json.dumps(batch.model_dump(mode="json"), ensure_ascii=False)
            yield f"data: {data}\n\n"

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
