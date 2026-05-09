# 生成物与数据模型入口 (AGENTS.md)

本目录用于存放系统设计中的数据模型（Data Model）以及未来由 Agent 或工具自动生成的结构化派生文档。

## 内容地图

- `data_model.md`: 定义了系统的核心数据结构（如 Task, UserProfile, Session 等）。这些定义是数据库 Schema 或 ORM 模型的唯一真相来源（Source of Truth）。

## 维护原则

- **机械化映射**: 本目录下的数据模型设计，必须严格映射到代码库中的类型定义（如 TypeScript interfaces、Python Pydantic models）。
- **不可手动篡改派生物**: 如果某些文档是通过脚本从代码中自动提取生成的（如未来的 OpenAPI Specs 派生文档），请不要手动修改它们，而是去修改源文件。