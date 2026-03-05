<div align="center">
  <h1>🛡️ NEXUS-OMNIGUARD (智巡护航)</h1>
  <h3>工业级具身智能巡检决策中枢</h3>

  <p>
    <b>基于 LangGraph 状态机与 RAG 知识库构建的可落地 LLM 智能体架构</b>
  </p>

  [![Python Space](https://img.shields.io/badge/Python-3.11-blue.svg?style=flat-square&logo=python)]()
  [![TypeScript](https://img.shields.io/badge/TypeScript-5.0-blue.svg?style=flat-square&logo=typescript)]()
  [![FastAPI](https://img.shields.io/badge/FastAPI-0.109-009688.svg?style=flat-square&logo=fastapi)]()
  [![Next.js](https://img.shields.io/badge/Next.js-14.1-black.svg?style=flat-square&logo=next.js)]()
  [![LangGraph](https://img.shields.io/badge/LangGraph-Stateful_Agents-orange.svg?style=flat-square)]()
  [![ChromaDB](https://img.shields.io/badge/ChromaDB-Vector_Search-FF6F00.svg?style=flat-square)]()

</div>

---

## 📺 演示视频 (Demo)

> **[点击查看 演示录屏]**
>
> `https://github.com/user-attachments/assets/7435bed7-f65a-49b2-9983-278f774982bd`

---

## 🏗️ 核心架构 (Architecture)

本项目采用 **Multi-Agent System** 架构，实现了从**数据感知**到**决策执行**的全流程闭环。系统核心是一个由 **LangGraph** 驱动的确定性有限状态机（FSM），确保在复杂的工业环境中，AI 的行为始终可控、可解释、可追溯。

```mermaid
graph LR
    subgraph "Edge Device / IoT Layer"
    S[Sensors] -->|Telemetry Stream| API(FastAPI Gateway)
    API -->|SSE Events| UI[Next.js Dashboard]
    end

    subgraph "Agentic Brain (LangGraph)"
    API -->|Trigger| O[Observe Node]
    O -->|Risk Score| R[Retrieve Node]
    R -->|RAG Context| P[Plan Node]
    P -->|Draft Plan| V{Safety Guard}
    
    V -->|Pass| E[Execute Node]
    V -->|Fail / Hallucination| P
    end

    subgraph "Knowledge Base"
    R -.->|Query| DB[(ChromaDB)]
    DB -.->|SOP Chunks| R
    end
    
    E -->|JSON Command| S
```

### � 目录结构解析

- **`/backend`**: 智能体核心逻辑
  - `app/core/agent_graph.py`: **大脑核心**。定义了 LangGraph 的状态流转（感知->检索->规划->校验）。
  - `app/core/rag_engine.py`: **记忆模块**。基于 ChromaDB 实现的 RAG 引擎，负责 SOP 文档的切片与向量检索。
  - `app/simulator`: **环境模拟**。生成高盐雾、危化品泄漏等极端场景的传感器数据。
- **`/frontend`**: 交互式看板
  - 基于 Next.js + Tailwind CSS，实时展示推理思维链（Chain of Thought）与传感器波形。
- **`/docs`**: 知识库源文件
  - 包含 20+ 份真实的 Markdown 格式巡检手册（SOP），是 Agent 决策的法律依据。

---

## 🧠 底层逻辑拆解 (Under the Hood)

### 1. 感知层：多模态数据融合 (Observe)
- **模拟器 (`sensor_simulator.py`)**: 系统内置了一个高保真的物理环境模拟器，能够生成温度、湿度、VOC（挥发性有机物）、盐雾浓度等多种传感器时序数据。
- **风险量化**: Agent 首先对遥测数据进行清洗，计算 `Risk Score`（风险评分）。例如，当 `VOC > 1.0 mg/m³` 时，系统会自动标记为“高危场景”，并触发紧急模式。

### 2. 记忆层：结构化 RAG 检索 (Retrieve)
- **SOP 数字化**: 系统启动时，会自动扫描 `/docs` 目录下的 Markdown 手册，将其按“标题-段落”进行语义切片，并存入本地向量数据库。
- **动态检索**: 当感知到“盐雾超标”时，Agent 不会凭空捏造对策，而是将异常状态转化为 Query，在知识库中检索相关的《防腐蚀维护规程》，提取 Top-3 条款作为上下文（Context）。

### 3. 认知层：思维链规划 (Plan)
- **Prompt Engineering**: 我们设计了包含 `Role`（角色）、`Task`（任务）、`Constraint`（约束）的结构化 Prompt。
- **LLM 推理**: Agent 结合**实时数据**与**检索到的 SOP 条款**，生成一段包含 `Thought`（思考过程）与 `Action`（行动指令）的 JSON。
  > *思考示例：“检测到盐雾浓度 18mg/m³，根据 SOP-07 条款 3.2，应立即启动自清洁程序并撤离至干燥区。”*

### 4. 安全层：确定性防御 (Safety Guard)
- **反幻觉机制**: LLM 生成的指令必须经过 `safety_guard` 节点的校验。
- **硬编码规则**: 系统内置了正则表达式与黑名单。例如，如果 LLM 建议“打开所有阀门”但未通过权限校验，或者指令参数超出硬件极限（如速度 > 2.0m/s），**Safety Guard 会直接拦截指令，并强制 Agent 重新规划（Re-plan）**，直到输出合规为止。

---

## 🚀 快速开始 (Quick Start)

### 方式一：Docker 一键启动 (推荐)

```bash
# 1. 克隆仓库
git clone https://github.com/a0982868339-ship-it/LogisticsDemo.git
cd LogisticsDemo

# 2. 配置环境变量
cp backend/.env.example backend/.env
# 编辑 backend/.env 填入你的 OPENAI_API_KEY

# 3. 启动服务
docker compose up --build
```

访问 `http://localhost:3000` 即可看到控制台。

### 方式二：本地开发模式

**后端 (Python 3.11+)**
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

**前端 (Node.js 18+)**
```bash
cd frontend
npm install
npm run dev
```

---

## 🛠️ 技术栈 (Tech Stack)

| 模块 | 技术选型 | 说明 |
| :--- | :--- | :--- |
| **LLM Orchestration** | **LangGraph** | 实现有状态、可循环、可纠错的 Agent 编排 |
| **Backend Framework** | **FastAPI** | 高性能异步 Python Web 框架 |
| **Vector DB** | **ChromaDB** | 本地轻量级向量数据库，用于 RAG |
| **Frontend** | **Next.js 14** | App Router, Server Components |
| **Styling** | **Tailwind CSS** | 现代化 UI 样式库 |
| **E2E Testing** | **Playwright** | 自动化端对端测试 |
| **Deployment** | **Docker & K8s** | 容器化与集群部署支持 |

---

**Made with ❤️ by [Your Name]**
