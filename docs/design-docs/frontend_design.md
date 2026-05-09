# 前端详细设计文档 (Frontend Design)

本节基于 `architecture.md` 进一步细化前端技术栈、目录结构及核心组件设计，以满足 MVP 阶段的需求。

## 1. 技术栈选型细化

* **核心框架**: React 18 + Vite (提供极速的冷启动和 HMR)
* **语言**: TypeScript (提供类型安全，与后端接口保持一致，符合“智能体可读性”)
* **样式方案**: Tailwind CSS (实用优先，避免繁琐的 CSS 文件管理)
* **UI 组件库**: shadcn/ui (无头组件库，提供高度可定制的无障碍组件，减少重复造轮子)
* **状态管理**: React Context + Hooks (MVP 阶段避免引入 Redux 等重型状态管理)
* **数据请求**: Axios (处理与后端 FastAPI 的 HTTP 通信)
* **路由**: React Router (虽然 MVP 只需要单一页面，但保留基础路由以便后续扩展)

## 2. 核心功能模块 (MVP 范围)

1.  **目标输入区 (Goal Input)**: 用户输入当日核心目标的文本框。
2.  **计划生成反馈 (Planner Feedback)**: 显示 AI 生成计划的过程状态（如 loading 动画）。
3.  **任务列表展示 (Task List)**: 以卡片形式展示生成的 3-5 个任务，每个卡片包含任务描述和“完成标准”。
4.  **执行交互 (Execution)**: 任务卡片上的 Checkbox，勾选后触发动画并发送状态给后端。
5.  **复盘展示 (Review Display)**: 每日结束时，展示 AI 生成的完成率分析和鼓励性建议。

## 3. 目录结构设计 (Directory Structure)

```text
src/
├── assets/         # 静态资源 (图片, 图标等)
├── components/     # 可复用的 UI 组件
│   ├── ui/         # 基础 UI 组件 (如 Button, Input, Card)
│   └── business/   # 业务组件 (如 TaskCard, GoalInputForm)
├── hooks/          # 自定义 React Hooks (如 useTasks, useAICoach)
├── pages/          # 页面级组件
│   └── Dashboard/  # MVP 核心页面，集成所有业务组件
├── services/       # API 请求封装 (与后端 FastAPI 交互)
├── types/          # TypeScript 类型定义 (如 Task, PlanResponse)
├── utils/          # 工具函数
├── App.tsx         # 根组件
└── main.tsx        # 应用入口
```

## 4. 关键组件规约 (Component Contracts)

为了符合 Harness Engineering 原则，前端组件设计必须遵循“接口驱动”：

*   **数据驱动**: 视图层 (View) 只负责渲染从 `hooks` 或 `services` 获取的数据。
*   **状态隔离**: 组件的内部状态 (Local State) 与全局业务状态 (Global State) 严格分离。
*   **类型严谨**: 所有 `props` 必须有明确的 TypeScript 接口定义。

### 4.1 核心组件设计：任务卡片 (TaskCard)

作为 MVP 阶段用户最高频交互的组件，`TaskCard` 必须在视觉上清晰传达 Harness Engineering 的核心理念：“明确的完成标准决定执行力”。同时，它是收集用户行为数据（供 Coach 决策）的核心入口。

**设计要求：**
1. **视觉层级分离**:
   - `description` (任务描述)：大字体、主色调，作为卡片的标题，让用户一眼看清“做什么”。
   - `criteria` (完成标准)：较小字体、次要色调（如灰色或带有背景色的块），放在描述下方。**这是区别于普通 Todo 应用的关键设计**，让用户明确知道“怎么算做完”。
2. **编辑与时间属性 (Coach 干预基础)**:
   - **手动编辑**: 卡片必须提供“编辑”按钮。当用户对 AI 生成的任务不满时，可直接修改描述、标准、以及预期时间。
   - **时间区间**: 显示计划的 `start_time` 和 `end_time`（或 deadline）。
   - **执行计时器**: 卡片上需内置一个启动/暂停的计时器（Stopwatch/Pomodoro 风格）。当计时器启动，任务状态变为 `in_progress`；当耗时异常时，前端或后端将触发提醒，实现“长时间未执行”或“卡住”的 AI 干预逻辑。
3. **交互反馈**:
   - 包含一个明显的 Checkbox 或“完成”按钮。
   - 勾选后，整个卡片应有状态变化（如变灰、文字增加删除线、伴随微小的成功动画），并上传实际耗时 (`duration_seconds`) 给后端。
4. **状态展示**: 根据后端的 `status` 字段（pending, in_progress, completed）改变卡片的边框颜色或图标提示。

*(后续开发中，具体的组件实现细节将遵循本规范。)*