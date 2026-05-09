"""
健康检查端点 (Health Check Endpoint)

设计意图：
    提供一个最简单的 GET /health 接口，用于：
    1. 验证服务是否正常启动
    2. 在部署/监控中作为存活探针 (Liveness Probe)
    3. 为前端和自动化测试提供一个"零依赖"的验证入口

    将健康检查独立为一个路由文件，而不是直接写在 main.py 中，
    是为了遵循"每个端点文件对应一个业务领域"的分层原则。
"""

from fastapi import APIRouter

from app.core.config import settings

# 创建独立的路由器，前缀为空（挂载到根路径）
# 后续其他端点会使用带前缀的路由器（如 /api/tasks、/api/plans）
router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> dict:
    """
    健康检查接口。

    返回服务的基本状态信息，包括应用名称和版本号。
    使用 async def 因为 FastAPI 会自动将其放入事件循环中运行，
    即使当前没有 I/O 操作，保持 async 风格的一致性。

    Returns:
        dict: 包含 status、app_name、version 的状态字典
    """
    return {
        "status": "ok",
        "app_name": settings.app_name,
        "version": settings.app_version,
    }
