# AI Agent 导航入口 (AGENTS.md)

欢迎来到 AICoach 仓库。本仓库采用 **Harness Engineering（驭缰工程）** 理念构建。
作为 AI 智能体，你是本系统的主要建设者和执行者。人类工程师负责设计约束、定义目标，而你负责产出代码并维护系统。

## 核心原则 (Harness Engineering Principles)

1. **接口设计决定模型表现 (Interface Drives Performance)**: 采用更适合 AI 的接口模式（如未来引入的 Hashline 协议），而非强迫 AI 去适应人类的字符级编辑，从底层提升生成成功率。
2. **建立“代码库免疫系统” (Immune System against Entropy)**: 防止技术债和坏味道被 Agent 指数级复制。通过强大的 Linter 和自动化规则（如 `harness_engineering/` 目录中定义的规则），在错误进入主分支前进行拦截和垃圾回收。
3. **仓库即唯一事实来源 (Repo as Source of Truth)**: 所有的架构决策、业务逻辑和任务状态都记录在代码库中。不存在任何外部的隐式知识。
4. **渐进式披露 (Progressive Disclosure)**: 本文件是你的起点（地图而非手册）。请顺着目录结构，通过读取子目录中的 `AGENTS.md` 获取更具体的上下文。
5. **机械化执行 (Mechanical Enforcement)**: 规则（如格式、接口、约束）将被转化为可自动验证的脚本或 Linter，错误信息内嵌修复指令，允许 Agent 自我纠正。
6. **面向智能体可读性 (Agent Readability)**: 优先使用清晰、无聊、稳定的技术栈，以降低你的推理成本。

## 项目目标与红线 (Project Goal & Boundaries)

**AICoach (AI 执行力教练)**
帮助知识工作者从“想做很多”变成“每天稳定完成关键任务”。重点是**稳定性**和**完成率**，而非绝对的效率。

*注意：Agent 极易产生“功能蔓延 (Feature Creep)”。在进行任何规划或开发前，必须阅读并严格遵守 [MVP 范围定义 (docs/concepts/mvp_scope.md)](./docs/concepts/mvp_scope.md) 中规定的红线。*

## 导航地图 (Navigation Map)

请根据你当前被分配的任务，选择阅读以下入口：

- 📚 **文档系统**: `/docs/AGENTS.md` (如果你需要了解产品需求、技术架构、提示词或评估标准，请首先前往这里)
- 💻 **源代码**: `/src` (系统的主代码库，具体入口视后续初始化而定)

---
*提示：当你进入任何子目录时，请优先寻找并读取该目录下的 `AGENTS.md`（或 `AGENTS.MD`）。*