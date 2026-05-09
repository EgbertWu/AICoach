"""
任务唯一性指纹工具 (Task Fingerprint Utilities)

设计意图：
    为“长期任务状态管理”提供稳定、可复用的唯一性校验能力。
    通过对任务内容做规范化并计算 hash，便于：
    - 同一目标同一天防重复插入（并发派发 / 重复点击）
    - 后续扩展：跨天去重、相似任务检测等

改动原因：
    任务重复生成与状态不一致的根因之一是缺少“可持久化、可校验”的唯一键。
"""

from __future__ import annotations

import hashlib
import re


_WS_RE = re.compile(r"\s+")


def normalize_task_text(text: str) -> str:
    """
    规范化任务文本。

    改动原因：
        直接对原始文本做 hash 会对空格/大小写过于敏感，导致“看起来相同”的任务无法命中去重。
        MVP 阶段先做最小但有效的规范化：trim、lower、折叠空白。
    """
    value = (text or "").strip().lower()
    value = _WS_RE.sub(" ", value)
    return value


def task_fingerprint(description: str, criteria: str | None = None) -> str:
    """
    计算任务指纹（sha256 hex）。

    改动原因：
        需要一个可持久化的、长度固定的唯一键来做数据库唯一性约束。
        同时把 criteria 纳入可以减少“描述相同但标准不同”的误判。
    """
    desc = normalize_task_text(description)
    crit = normalize_task_text(criteria or "")
    raw = f"{desc}\n---\n{crit}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

