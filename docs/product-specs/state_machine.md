# 状态机（工程级）

## 状态定义

IDLE
PLANNED
IN_PROGRESS
STUCK
COMPLETED
REVIEWED

---

## 状态转换 + API绑定

### IDLE → PLANNED
触发：
- 用户调用 /generate-plan

---

### PLANNED → IN_PROGRESS
触发：
- 用户开始任务

---

### IN_PROGRESS → STUCK
触发：
- 30分钟未完成当前任务
- 或60分钟无任何操作

行为：
- 调用 coach（未来扩展）

---

### IN_PROGRESS → COMPLETED
触发：
- 所有任务 status=done

---

### COMPLETED → REVIEWED
触发：
- 用户调用 /review