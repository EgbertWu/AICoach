# 核心评估指标 (Metrics)

根据 Harness Engineering 理念，我们需要从**产品价值**和**系统效能**两个维度来进行衡量。

## 1. 业务产品指标 (Product Metrics)
这是我们最终的目标，一切代码和文档的产出都为了提升以下指标：

- **核心留存**: 日活用户（DAU）、连续使用天数（体现“教练依赖感”）。
- **执行转化**: 平均完成率（需维持在 80% 以上，见 `mvp_scope.md`）、每日任务完成绝对数量。

## 2. Agent 效能指标 (Agent & System Metrics)
用于在自动化测试流水线和 CI/CD 阶段监控智能体的行为质量：

- **格式遵循率 (Format Adherence Rate)**: Agent 输出完全符合 JSON schema 等规则的比例。
- **吞吐量与性能 (Throughput)**: 
  - Token 消耗量及每次对话成本。
  - 首字响应时间 (TTFB) 与端到端延迟。
- **自我纠正成功率 (Self-Correction Rate)**: Agent 在格式错误后，通过重新 Prompting 成功纠正的比例。
- **Lint 通过率**: 代码/计划生成符合机械化验证（数量 <= 5 等）的概率。