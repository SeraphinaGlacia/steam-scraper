"""
HTTP 客户端工具模块。

封装 HTTP 请求，提供重试机制和速率限制。
所有爬虫类均通过此客户端发起网络请求，统一处理超时、重试和延迟。
"""

from __future__ import annotations

import random
import time
from typing import Any, Optional

import requests
import urllib3

from src.config import Config, get_config

# 移除了全局副作用



class HttpClient:
    """HTTP 客户端，支持重试和速率限制。

    Attributes:
        config: 配置对象。
        session: requests Session 对象。
    """

    def __init__(self, config: Optional[Config] = None):
        """初始化 HTTP 客户端。

        Args:
            config: 可选的配置对象，如果不提供则使用全局配置。
        """
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
