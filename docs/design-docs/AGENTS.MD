# 设计文档入口 (AGENTS.MD)

本目录包含系统的核心架构与接口设计规范。在 Harness Engineering 体系中，接口设计直接决定模型表现。

## 核心设计理念

1. **接口设计决定模型表现 (Interface Drives Performance)**:
   - 传统的人机接口（如 Diff 或精确字符串替换）并不适合自回归模型。
   - **Hashline 协议设计**: 在设计文件读写或代码修改相关的 Agent 接口时，必须考虑将“内容寻址”与“内容生成”分离。例如，给读取到的文件行赋予 `<行号>:<哈希标签>|` 前缀，让模型通过引用哈希标签来进行修改，从而避开模型在精确字符匹配上的短板。
   
2. **面向智能体可读性 (Agent Readability)**:
   - 架构设计必须优先考虑清晰、稳定、主流的技术栈，减少“魔法”和隐式依赖。

## 内容地图

- **[`architecture.md`](./architecture.md)**: 系统高层架构图，说明技术栈选型原因和系统宏观边界。
- **[`frontend_design.md`](./frontend_design.md)**: 前端详细设计（React + Vite），包含目录结构和组件规约。
- **[`backend_design.md`](./backend_design.md)**: 后端详细设计（FastAPI + SQLite），包含 Agent 编排、数据验证（Pydantic）与路由划分。

*(此目录后续将包含针对 Hashline 等新接口协议的具体实现规范。)*
