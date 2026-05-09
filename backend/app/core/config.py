"""
核心配置模块 (Core Config)

设计意图：
    集中管理所有可配置项，使用 Pydantic Settings 进行类型安全的配置管理。
    这样做的好处是：
    1. 配置项有明确的类型提示，IDE 和 Agent 都能轻松理解
    2. 支持从环境变量覆盖，便于部署时灵活调整
    3. 单一真相来源，避免配置散落在各处

MVP 阶段配置项保持最小化，后续按需扩展。
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    应用全局配置类。

    所有配置项都可以通过环境变量覆盖（前缀 APP_）。
    例如：APP_DEBUG=true 会覆盖 debug 字段的默认值。
    """

    # 应用基本信息
    app_name: str = "AICoach API"
    app_version: str = "0.1.0"
    debug: bool = True  # MVP 阶段默认开启调试模式，方便开发

    # 服务配置
    host: str = "0.0.0.0"  # 监听所有网络接口，方便局域网测试
    port: int = 8000

    # 数据库配置
    # SQLite 使用相对路径，数据库文件将创建在 backend/ 目录下
    database_url: str = "sqlite+aiosqlite:///./aicoach.db"

    # ===== LLM 配置 =====
    # 使用兼容 OpenAI 格式的 API（如 DeepSeek、本地 Ollama 等）
    # base_url 和 api_key 通过环境变量设置，避免硬编码敏感信息
    llm_base_url: str = "https://api.deepseek.com"
    llm_api_key: str = ""  # ⚠️ 必须通过环境变量 APP_LLM_API_KEY 设置
    llm_model: str = "deepseek-chat"  # 默认使用 DeepSeek Chat 模型
    llm_temperature: float = 0.3  # 低温度值：Planner 需要稳定、可预测的输出
    llm_max_tokens: int = 2000  # 最大生成 token 数，MVP 阶段足够

    # JWT 认证配置
    secret_key: str = "aicoach-mvp-dev-secret-key-change-in-production"  # ⚠️ 生产环境必须通过环境变量 APP_SECRET_KEY 设置
    algorithm: str = "HS256"  # JWT 签名算法
    access_token_expire_minutes: int = 60 * 8  # Token 有效期：8 小时（可通过环境变量覆盖）

    # 登录安全策略
    max_failed_login_attempts: int = 5  # 连续失败次数阈值
    account_lock_minutes: int = 30  # 锁定时长（分钟）

    # CORS 配置（逗号分隔）
    cors_allow_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    model_config = {
        # 允许通过环境变量（前缀 APP_）覆盖配置
        "env_prefix": "APP_",
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }


# 创建全局单例，其他模块通过 from app.core.config import settings 获取配置
settings = Settings()
