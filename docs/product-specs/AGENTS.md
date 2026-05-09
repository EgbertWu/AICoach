# 产品规格与评估体系入口 (AGENTS.md)

本目录用于存放系统产品规格、评估指标和测试用例。这是 Harness Engineering 中实现“机械化执行 (Mechanical Enforcement)”和“约束即产品”的核心地带。

## 内容地图

- **需求规格类**: `feature_spec.md`, `api_spec.yml`, `task_breakdown.md`（定义了系统应当实现什么）。
- **智能体控制类**: `state_machine.md`（定义了 AI 教练的对话状态流转）。
- **评估与测试类**: `eval_spec.md`, `metrics.md`, `test_cases.md`（作为“代码库免疫系统”，通过规则拦截技术债，防止任务发散）。

## 维护原则

- **高标准执行**: 这里的文档是系统验证的标准来源，每次系统或 Prompt 的迭代都必须符合 `test_cases.md` 和 `eval_spec.md`。
- **机械化映射**: 测试用例应该最终映射到自动化的测试脚本中。错误信息应包含修复指令，方便智能体自我纠正。