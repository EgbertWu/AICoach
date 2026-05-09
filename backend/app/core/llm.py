"""
LLM 客户端模块 (LLM Client)

设计意图：
    封装与 LLM 服务的交互逻辑，提供统一的调用接口。
    使用 OpenAI Python SDK（兼容 DeepSeek、Ollama 等 OpenAI 格式 API），
    而非 LangChain，原因是：
    1. 更轻量：只依赖 openai 包，不引入 LangChain 的庞大依赖树
    2. 更透明：调用链路短，Agent 能轻松理解每一步在做什么
    3. 更易调试：出问题时可以直接看到原始请求和响应
    4. 符合 backend_design.md 中"推荐直接使用 SDK，保持代码透明度"的建议
"""

from typing import Any, cast

try:
    from openai import AsyncOpenAI
except ModuleNotFoundError:  # pragma: no cover
    AsyncOpenAI = None  # type: ignore[assignment]

from app.core.config import settings


def get_llm_client() -> Any:
    """
    获取异步 LLM 客户端实例。

    设计意图：
        使用工厂函数而非模块级全局变量创建客户端，
        这样在测试时可以轻松替换为 mock 客户端。
        每次调用创建新实例的开销极小（OpenAI SDK 内部使用连接池复用）。

    Returns:
        AsyncOpenAI: 配置好 base_url 和 api_key 的异步客户端

    Raises:
        ValueError: 如果 api_key 未配置，给出明确的错误提示
    """
    if AsyncOpenAI is None:
        raise RuntimeError(
            "未安装 openai 依赖，无法创建 LLM 客户端。请安装 openai：pip install openai"
        )

    if not settings.llm_api_key:
        raise ValueError(
            "LLM API Key 未配置！请在 .env 文件中设置 APP_LLM_API_KEY，"
            "或通过环境变量 APP_LLM_API_KEY 传入。"
        )

    return cast(Any, AsyncOpenAI)(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
    )
