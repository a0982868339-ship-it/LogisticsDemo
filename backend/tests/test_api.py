"""tests/test_api.py — T6 FastAPI 路由单元测试"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app, raise_server_exceptions=True)


# ─────────────────────────────────────────────────────────────────
# 健康检查
# ─────────────────────────────────────────────────────────────────

class TestHealthCheck:
    def test_health_returns_ok(self):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


# ─────────────────────────────────────────────────────────────────
# 会话管理
# ─────────────────────────────────────────────────────────────────

class TestSessionRoutes:
    def test_create_session_returns_session_id(self):
        resp = client.post("/sessions")
        assert resp.status_code == 200
        data = resp.json()
        assert "session_id" in data
        assert len(data["session_id"]) == 36  # UUID格式

    def test_get_existing_session(self):
        create_resp = client.post("/sessions")
        sid = create_resp.json()["session_id"]

        get_resp = client.get(f"/sessions/{sid}")
        assert get_resp.status_code == 200
        session_data = get_resp.json()
        assert session_data["session_id"] == sid
        assert "current_state" in session_data

    def test_get_nonexistent_session_returns_404(self):
        resp = client.get("/sessions/nonexistent-session-id")
        assert resp.status_code == 404

    def test_create_multiple_sessions_unique_ids(self):
        ids = [client.post("/sessions").json()["session_id"] for _ in range(3)]
        assert len(set(ids)) == 3, "每个会话ID应唯一"


# ─────────────────────────────────────────────────────────────────
# 传感器触发
# ─────────────────────────────────────────────────────────────────

class TestTelemetryRoutes:
    def test_trigger_normal_scenario(self):
        resp = client.post("/telemetry/trigger", json={"scenario": "normal"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["scenario"] == "normal"
        assert len(data["readings"]) >= 1

    def test_trigger_salt_spray_exceeds_threshold(self):
        # 多次触发确保场景A盐雾值稳定超阈值
        for _ in range(5):
            resp = client.post("/telemetry/trigger", json={"scenario": "salt_spray"})
            assert resp.status_code == 200
            data = resp.json()
            salt_readings = [r for r in data["readings"] if r["sensor_type"] == "SALT_SPRAY"]
            assert len(salt_readings) >= 1
            assert salt_readings[0]["value"] > 15.0

    def test_trigger_hazmat_scenario_has_visual(self):
        resp = client.post("/telemetry/trigger", json={"scenario": "hazmat"})
        assert resp.status_code == 200
        data = resp.json()
        visual = next((r for r in data["readings"] if r["sensor_type"] == "VISUAL"), None)
        assert visual is not None
        assert "泄漏" in str(visual["value"])

    def test_trigger_unknown_scenario_falls_back_to_normal(self):
        """未知场景回退到 normal"""
        resp = client.post("/telemetry/trigger", json={"scenario": "unknown_xyz"})
        assert resp.status_code == 200  # 不报错，回退正常场景

    def test_trigger_response_has_batch_id(self):
        resp = client.post("/telemetry/trigger", json={"scenario": "normal"})
        assert "batch_id" in resp.json()


# ─────────────────────────────────────────────────────────────────
# 推理路由（不实际调用LLM，验证路由可访问性）
# ─────────────────────────────────────────────────────────────────

class TestInferenceRoute:
    def test_inference_endpoint_exists(self):
        """验证推理接口存在（Mock LangGraph 避免调用 LLM）"""
        from fastapi.testclient import TestClient
        with TestClient(app) as c:
            # patch app.core.agent_graph 中的 build_agent_graph
            with patch("app.core.agent_graph.build_agent_graph") as mock_build:
                from app.models.schemas import AgentSession
                import asyncio

                async def _fake_astream(state, stream_mode):
                    from app.core.agent_graph import observe_node
                    state_out = observe_node(state)
                    state_out["action_plan"] = []
                    state_out["safety_verdict"] = "PASS"
                    state_out["final_command"] = None
                    yield state_out

                mock_compiled = MagicMock()
                mock_compiled.astream = _fake_astream
                mock_build.return_value = mock_compiled

                # 重置全局单例，让新 build 生效
                import app.core.agent_graph as _ag
                _ag._compiled_graph = None

                resp = c.post("/inference", json={"scenario": "normal"})
                assert resp.status_code == 200

