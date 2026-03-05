<div align="center">
  <h1>🛡️ NEXUS-OMNIGUARD</h1>
  <h3>工业级具身智能巡检决策中枢</h3>

  <p>
    <b>基于 LangGraph 与 RAG 构建的可落地的 LLM 智能体架构编排框架</b>
  </p>

  [![Python Space](https://img.shields.io/badge/Python-3.11-blue.svg?style=flat-square&logo=python)]()
  [![TypeScript](https://img.shields.io/badge/TypeScript-5.0-blue.svg?style=flat-square&logo=typescript)]()
  [![FastAPI](https://img.shields.io/badge/FastAPI-0.109-009688.svg?style=flat-square&logo=fastapi)]()
  [![Next.js](https://img.shields.io/badge/Next.js-14.1-black.svg?style=flat-square&logo=next.js)]()
  [![LangGraph](https://img.shields.io/badge/LangGraph-Stateful_Agents-orange.svg?style=flat-square)]()
  [![ChromaDB](https://img.shields.io/badge/ChromaDB-Vector_Search-FF6F00.svg?style=flat-square)]()
  [![Tests](https://img.shields.io/badge/E2E_Tests-Playwright-2EAD33.svg?style=flat-square&logo=playwright)]()

</div>

---

## 📖 项目简介

**NEXUS-OMNIGUARD（智巡护航）** 是一个专为高级具身智能（如：重型仓储巡检机器人、化工厂四足机器狗）设计的**工业级决策中枢**。本项目彻底摒弃了传统的 `if-else` 硬编码业务逻辑，利用大语言模型（LLM）强大的零样本推理（Zero-Shot Reasoning）能力，构建了一套完整的边缘智能体架构。

系统能够实时订阅底层物联网（IoT）的遥测异常，动态结合企业真实的《安全作业指导书(SOP)》进行离线向量检索（RAG），并在绝对可靠的**安全防线（Safety Guard）**拦截机制下，为底层硬件生成合规的排障动作指令（JSON Payload）。哪怕应对高盐雾腐蚀、危化品泄漏等极限长尾场景，系统依然能保持毫秒级的稳健响应。

### 🌟 核心技术亮点 (架构优势)

1. **状态机驱动的高可靠 Agent 编排 (Powered by LangGraph)**：
   物理世界的排障容不得大模型出现“一次性赌博”式的幻觉。我们利用 LangGraph 将核心 Agent 抽象为严格的图结构状态机：`[感知 -> 检索 -> 规划 -> 验证 -> 输出]`。这不仅使得复杂的 LLM 的思维链路（Thought Chain）变得**可持久化、可观测、可审计**，还原生实现了指令被拦截后的**闭环重规划 (Re-plan)**。
   
2. **深度定制的工业级 RAG (ChromaDB + 离线 Embedding)**：
   通用大模型不懂单家企业的独家厂规，**本项目通过 RAG 架构完美解决了工业级应用最重要的“长尾知识”和“数据隐私”痛点：**
   - **结构感知切片 (Structure-Aware Chunking)**：针对 Markdown 版真实的《巡检手册》按标题/段落语义进行智能切片。
   - **完全离线的隐私保护**：采用 `sentence-transformers` 进行本地 Embedding 编码并写入离线 `ChromaDB`，确保核心 SOP 数据不出内网。
   - **语义动态植入 (Dynamic Grounding)**：系统在告警发生时，将多模态异构数据（如 VOC > 1.0）转化为自然语言 Query，毫秒级检索 Top-K 安全条款喂给大模型。
   - **零代码业务解耦**：当机器人部署到新厂区时，**只需替换 Markdown 版本的 SOP 文档，无需重新编写一行代码，更无需支付高昂的模型微调（Fine-Tuning）成本，整个机器人的行为逻辑瞬间顺应新规变更。**
   
3. **坚如磐石的安全底线 (Deterministic Safety Guard)**：
   我们为大模型的“随性”拉起了警戒线。系统引入了独立的后置业务安全校验节点。即使 GPT 偶发严重幻觉（例如下令：带电喷水降温），硬编码的正则表达式和黑名单安全栅栏也会立刻阻断指令，并强迫 Agent 带着“被拒绝的法律依据”重新思考方案，确保下发至硬件的指令 **100% 满足工业安全规范**。

4. **极致的全栈工程化实践**：
   - **Frontend**: 采用 Next.js (App Router) 构建服务端渲染的高性能看板，大量使用 TailWindCSS 和 CSS Variables 支持暗黑主题，无状态组件配合实时流式 UI 数据渲染。
   - **Backend**: FastAPI 异步非阻塞高并发架构，Pydantic 严苛数据验证。
   - **Testing**: CI/CD 流水线中集成了包含完整 Pytest 驱动的后端 LangGraph 有向图逻辑测试与 Playwright E2E 前端界面自动化断言测试，保证了代码的极高交付质量。

---

## 🚀 快速开始

### 🔧 1. 后端服务启动

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install eval_type_backport  # 兼容 Python 3.8+ 的类型注解

# 配置环境变量
cp .env.example .env
# 请在 .env 中填入有效的 OPENAI_API_KEY 和 OPENAI_BASE_URL (注意包含 /v1 路径)

# 启动 FastAPI 大脑引擎
python -m uvicorn app.main:app --reload --port 8000
```

### 💻 2. 前端看板启动

```bash
cd frontend
npm install
# 启动 Next.js 监控大屏
npm run dev
```
*浏览器打开 `http://localhost:3000` 即可访问交互界面*

## 🧪 测试覆盖 (Testing)

本项目非常注重高可用性与工程严谨度，已配置覆盖核心链路的测试用例。

**后端 Agent 链路/知识库检索测试**:
```bash
cd backend
# 优先构建 RAG 本地向量索引
python -c "from app.core._scripts import build_index; build_index()"
# 运行 LangGraph 集成测试链路
pytest tests/test_integration.py -v
```

**前端 E2E 界面交互测试 (Playwright)**:
```bash
cd frontend
npx playwright install --with-deps chromium
npm run test:e2e
```

## 📂 架构图 (Architecture Diagram)

*(此处可插入你的系统架构图 Flow Chart)*

## 🤝 开源协议
MIT License. 欢迎随时 Fork 交流，或将其作为你的具身智能/Agent 落地的基础设施参考。
