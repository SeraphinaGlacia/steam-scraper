"""
游戏信息爬虫模块。

从 Steam 商店爬取游戏基础信息。
"""

from __future__ import annotations

from typing import Callable, Optional

from bs4 import BeautifulSoup

from src.config import Config, get_config
from src.models import GameInfo
from src.utils.checkpoint import Checkpoint
from src.utils.http_client import HttpClient


class GameScraper:
    """Steam 游戏信息爬虫。

    从 Steam 商店搜索页面爬取游戏列表，并获取每个游戏的详细信息。

    Attributes:
        config: 配置对象。
        client: HTTP 客户端。
        checkpoint: 断点管理器。
        games: 已爬取的游戏信息列表。
    """

    def __init__(
        self,
        config: Optional[Config] = None,
        checkpoint: Optional[Checkpoint] = None,
    ):
        """初始化游戏爬虫。

        Args:
            config: 可选的配置对象。
            checkpoint: 可选的断点管理器。
        """
        self.config = config or get_config()
        self.client = HttpClient(self.config)
        self.checkpoint = checkpoint
        self.games: list[GameInfo] = []

        # 构建基础 URL（保持原有参数）
        self.base_url = (
            f"https://store.steampowered.com/search/"
            f"?l={self.config.scraper.language}"
            f"&cc={self.config.scraper.currency}"
        )

    def get_total_pages(self) -> int:
        """获取搜索结果的总页数。

        Returns:
            int: 总页数。
        """
        params = {"category1": self.config.scraper.category, "page": "1"}

        try:
            response = self.client.get(self.base_url, params=params, delay=False)
            soup = BeautifulSoup(response.text, "html.parser")

            search_results = soup.find("div", {"class": "search_pagination_left"})
            if search_results:
                total_results = int(search_results.text.strip().split(" ")[-2])
                return (total_results // 25) + 1  # Steam 每页显示 25 个游戏
        except Exception as e:
            print(f"获取总页数失败: {e}")

        return 5000  # 默认值

    def get_game_details(self, app_id: int) -> Optional[GameInfo]:
        """获取单个游戏的详细信息。

        Args:
            app_id: Steam 游戏 ID。

        Returns:
            Optional[GameInfo]: 游戏信息对象，获取失败时返回 None。
        """
        url = (
            f"https://store.steampowered.com/api/appdetails"
            f"?appids={app_id}"
            f"&l={self.config.scraper.language}"
            f"&cc={self.config.scraper.currency}"
        )

        try:
            data = self.client.get_json(url)

            if data.get(str(app_id), {}).get("success"):
                game_data = data[str(app_id)]["data"]
                return GameInfo.from_api_response(app_id, game_data)

        except Exception as e:
            print(f"获取游戏 {app_id} 详情失败: {e}")

        return None

    def scrape_page(self, page: int) -> list[GameInfo]:
        """爬取指定页面的游戏列表。

        Args:
            page: 页码。

        Returns:
            list[GameInfo]: 该页面的游戏信息列表。
        """
        params = {
            "category1": self.config.scraper.category,
            "sort_by": "_ASC",
            "page": str(page),
        }

        page_games: list[GameInfo] = []

        try:
            response = self.client.get(self.base_url, params=params, delay=False)
            soup = BeautifulSoup(response.text, "html.parser")

            games = soup.find_all("a", {"class": "search_result_row"})

            for game in games:
                app_id_str = game.get("data-ds-appid")
                if not app_id_str:
                    continue

                app_id = int(app_id_str)

                # 检查是否已在断点中完成
                if self.checkpoint and self.checkpoint.is_appid_completed(app_id):
                    continue

                details = self.get_game_details(app_id)

                if details:
                    page_games.append(details)
                    self.games.append(details)
                    print(f"已爬取: {details.name}")

                    if self.checkpoint:
                        self.checkpoint.mark_appid_completed(app_id)

        except Exception as e:
            print(f"爬取第 {page} 页失败: {e}")

        return page_games

    def run(
        self,
        max_pages: Optional[int] = None,
        on_page_complete: Optional[Callable[[int, list[GameInfo]], None]] = None,
    ) -> list[GameInfo]:
        """运行爬虫。

        Args:
            max_pages: 可选的最大页数限制。
            on_page_complete: 可选的页面完成回调函数。

        Returns:
            list[GameInfo]: 所有爬取的游戏信息列表。
        """
        total_pages = self.get_total_pages()
        if max_pages:
            total_pages = min(total_pages, max_pages)

        print(f"开始爬取 {total_pages} 页...")

        for page in range(1, total_pages + 1):
            # 检查是否已在断点中完成
            if self.checkpoint and self.checkpoint.is_page_completed(page):
                print(f"跳过已完成的第 {page} 页")
                continue

            print(f"正在爬取第 {page}/{total_pages} 页")
            page_games = self.scrape_page(page)

            if self.checkpoint:
                self.checkpoint.mark_page_completed(page)

            if on_page_complete:
                on_page_complete(page, page_games)

        return self.games

    def get_app_ids(self) -> list[int]:
        """获取所有已爬取游戏的 app_id 列表。

        Returns:
            list[int]: app_id 列表。
        """
        return [game.app_id for game in self.games]
