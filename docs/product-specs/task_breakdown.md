# Agent开发任务拆解（严格顺序）

## 阶段1：基础后端

1. 创建 FastAPI 项目
2. 实现 Task 数据模型（Pydantic）
3. 实现 /generate-plan API
   - 调用 planner_prompt
   - 返回结构化 tasks

4. 实现 /tasks/{task_id}/complete
   - 更新状态

5. 实现 /review API
   - 调用 review_prompt

---

## 阶段2：存储

6. 接入 SQLite（MVP）
7. 保存 tasks 和 plan

---

## 阶段3：前端（简单）

8. 展示任务列表
9. 勾选完成按钮
10. 显示复盘结果