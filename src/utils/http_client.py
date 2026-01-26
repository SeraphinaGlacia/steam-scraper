"""
HTTP 客户端工具模块。

封装 HTTP 请求，提供重试机制和速率限制。
所有爬虫类均通过此客户端发起网络请求，统一处理超时、重试和延迟。

本模块提供两种客户端实现：
- HttpClient: 同步客户端（已废弃，仅为向后兼容保留）
- AsyncHttpClient: 异步客户端（推荐使用，基于 httpx）
"""

from __future__ import annotations

import asyncio
import random
import time
import warnings
from typing import Any, Optional

import httpx
import requests
import urllib3

from src.config import Config, get_config


class AsyncHttpClient:
    """异步 HTTP 客户端，支持重试和速率限制。

    基于 httpx.AsyncClient 实现，提供真正的非阻塞并发请求能力。
    推荐在所有爬虫类中使用此客户端替代同步版本。

    Attributes:
        config: 配置对象。
        _client: httpx 异步客户端实例（延迟初始化）。
    """

    def __init__(self, config: Optional[Config] = None):
        """初始化异步 HTTP 客户端。

        Args:
            config: 可选的配置对象，如果不提供则使用全局配置。
        """
        self.config = config or get_config()
        # 延迟初始化客户端，因为 AsyncClient 需要在异步上下文中使用
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """获取或创建 httpx 异步客户端。

        采用延迟初始化策略，确保客户端在异步上下文中正确创建。
        这样可以避免在模块导入时就创建客户端，提高灵活性。

        Returns:
            httpx.AsyncClient: 异步客户端实例。
        """
        if self._client is None:
            self._client = httpx.AsyncClient(
                headers={"User-Agent": self.config.http.user_agent},
                timeout=httpx.Timeout(self.config.http.timeout),
                # 禁用 SSL 验证以兼容某些网络环境
                # Steam API 在某些地区可能存在证书问题
                verify=False,
            )
        return self._client

    async def get(
        self,
        url: str,
        params: Optional[dict[str, Any]] = None,
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
        """
        client = await self._get_client()
        last_exception: Optional[Exception] = None

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

        raise last_exception  # type: ignore

    async def get_json(
        self,
        url: str,
        params: Optional[dict[str, Any]] = None,
        delay: bool = True,
    ) -> dict[str, Any]:
        """发送异步 GET 请求并返回 JSON 响应。

        Args:
            url: 请求 URL。
            params: 可选的查询参数。
            delay: 是否在请求后添加延迟，默认为 True。

        Returns:
            dict: JSON 响应数据。
        """
        response = await self.get(url, params, delay)
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


class HttpClient:
    """HTTP 客户端，支持重试和速率限制。

    .. deprecated::
        此类已废弃，请使用 AsyncHttpClient 替代。
        仅为向后兼容测试脚本而保留。

    Attributes:
        config: 配置对象。
        session: requests Session 对象。
    """

    def __init__(self, config: Optional[Config] = None):
        """初始化 HTTP 客户端。

        Args:
            config: 可选的配置对象，如果不提供则使用全局配置。
        """
        warnings.warn(
            "HttpClient 已废弃，请使用 AsyncHttpClient 替代。",
            DeprecationWarning,
            stacklevel=2,
        )
        self.config = config or get_config()
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.config.http.user_agent})

        # 禁用 SSL 警告
        # Steam API 请求使用 verify=False 跳过证书验证（为了兑容某些网络环境）
        # 因此需要禁用警告避免每次请求都输出 InsecureRequestWarning
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def get(
        self,
        url: str,
        params: Optional[dict[str, Any]] = None,
        delay: bool = True,
    ) -> requests.Response:
        """发送 GET 请求，带有重试和速率限制。

        Args:
            url: 请求 URL。
            params: 可选的查询参数。
            delay: 是否在请求后添加延迟，默认为 True。

        Returns:
            requests.Response: 响应对象。

        Raises:
            requests.RequestException: 请求失败且重试次数耗尽时抛出。
        """
        last_exception: Optional[Exception] = None

        for attempt in range(self.config.http.max_retries + 1):
            try:
                response = self.session.get(
                    url,
                    params=params,
                    timeout=self.config.http.timeout,
                    verify=False,  # 与原代码保持一致
                )
                response.raise_for_status()

                # 请求成功后添加延迟
                if delay:
                    self._delay()

                return response

            except requests.RequestException as e:
                last_exception = e
                if attempt < self.config.http.max_retries:
                    # 指数退避策略：等待时间 = 2^attempt + 随机抖动
                    # 这样做可以防止所有客户端在同一时间重试（雷鸣群问题）
                    # 并给服务器足够的恢复时间
                    wait_time = (2**attempt) + random.uniform(0, 1)
                    print(
                        f"请求失败，{wait_time:.1f} 秒后重试 ({attempt + 1}/{self.config.http.max_retries}): {e}"
                    )
                    time.sleep(wait_time)

        raise last_exception  # type: ignore

    def get_json(
        self,
        url: str,
        params: Optional[dict[str, Any]] = None,
        delay: bool = True,
    ) -> dict[str, Any]:
        """发送 GET 请求并返回 JSON 响应。

        Args:
            url: 请求 URL。
            params: 可选的查询参数。
            delay: 是否在请求后添加延迟，默认为 True。

        Returns:
            dict: JSON 响应数据。
        """
        response = self.get(url, params, delay)
        return response.json()

    def _delay(self) -> None:
        """添加随机延迟以避免请求过快。"""
        delay = random.uniform(
            self.config.http.min_delay,
            self.config.http.max_delay,
        )
        time.sleep(delay)
