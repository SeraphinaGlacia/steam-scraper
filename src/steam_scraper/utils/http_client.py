"""HTTP 客户端工具模块。

基于 httpx 封装异步 HTTP 请求，统一处理超时、重试和速率限制。
"""

from __future__ import annotations

import asyncio
import random
from typing import Any

import httpx

try:
    import orjson
except ImportError:
    orjson = None

from steam_scraper.config import Config, get_config


class AsyncHttpClient:
    """异步 HTTP 客户端，支持重试和速率限制。

    基于 httpx.AsyncClient 实现非阻塞并发请求，供所有爬虫复用。

    Attributes:
        config: 配置对象。
        _client: httpx 异步客户端实例（延迟初始化）。
    """

    def __init__(self, config: Config | None = None) -> None:
        """初始化异步 HTTP 客户端。

        Args:
            config: 可选的配置对象，如果不提供则使用全局配置。
        """
        self.config = config or get_config()
        # 延迟初始化客户端，因为 AsyncClient 需要在异步上下文中使用
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """获取或创建 httpx 异步客户端。

        采用延迟初始化策略，确保客户端在异步上下文中正确创建。
        这样可以避免在模块导入时就创建客户端，提高灵活性。

        Returns:
            可复用的异步客户端实例。
        """
        if self._client is None:
            limits = httpx.Limits(
                max_connections=self.config.http.max_connections,
                max_keepalive_connections=self.config.http.max_keepalive_connections,
            )
            self._client = httpx.AsyncClient(
                headers={"User-Agent": self.config.http.user_agent},
                timeout=httpx.Timeout(self.config.http.timeout),
                limits=limits,
                # 部分地区访问 Steam 时存在证书链异常，当前策略继续跳过验证。
                verify=False,
            )
        return self._client

    async def get(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        delay: bool = True,
    ) -> httpx.Response:
        """发送异步 GET 请求，带有重试和速率限制。

        Args:
            url: 请求 URL。
            params: 可选的查询参数。
            delay: 是否在请求后添加延迟，默认为 True。

        Returns:
            httpx.Response: 响应对象。

        Raises:
            httpx.HTTPStatusError: HTTP 状态码错误（4xx/5xx）。
            httpx.RequestError: 请求失败且重试次数耗尽时抛出。
            ValueError: 配置的最大重试次数小于 0 时抛出。
        """
        client = await self._get_client()
        last_exception: httpx.HTTPStatusError | httpx.RequestError | None = None

        for attempt in range(self.config.http.max_retries + 1):
            try:
                response = await client.get(url, params=params)
                response.raise_for_status()

                # 请求成功后添加延迟，避免请求过快触发限流
                if delay:
                    await self._delay()

                return response

            except (httpx.HTTPStatusError, httpx.RequestError) as e:
                last_exception = e
                if attempt < self.config.http.max_retries:
                    # 指数退避策略：等待时间 = 2^attempt + 随机抖动
                    # 这样做可以防止所有客户端在同一时间重试（雷鸣群问题）
                    # 并给服务器足够的恢复时间
                    wait_time = (2**attempt) + random.uniform(0, 1)
                    print(
                        f"请求失败，{wait_time:.1f} 秒后重试 "
                        f"({attempt + 1}/{self.config.http.max_retries}): {e}"
                    )
                    await asyncio.sleep(wait_time)

        if last_exception is not None:
            raise last_exception
        msg = "http.max_retries 不能小于 0"
        raise ValueError(msg)

    async def get_json(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        delay: bool = True,
    ) -> dict[str, Any]:
        """发送异步 GET 请求并返回 JSON 响应。

        Args:
            url: 请求 URL。
            params: 可选的查询参数。
            delay: 是否在请求后添加延迟，默认为 True。

        Returns:
            JSON 对象形式的响应数据。
        """
        response = await self.get(url, params, delay)

        # 尝试使用 orjson 解析，速度更快
        if orjson is not None:
            try:
                return orjson.loads(response.content)
            except Exception:
                pass

        return response.json()

    async def _delay(self) -> None:
        """添加随机延迟以避免请求过快。

        使用 asyncio.sleep 实现非阻塞延迟，不会阻塞事件循环。
        """
        delay = random.uniform(
            self.config.http.min_delay,
            self.config.http.max_delay,
        )
        await asyncio.sleep(delay)

    async def close(self) -> None:
        """关闭客户端连接。

        在爬虫完成后应当调用此方法释放资源。
        """
        if self._client is not None:
            await self._client.aclose()
            self._client = None
