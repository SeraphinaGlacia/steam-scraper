"""
游戏信息爬虫模块。

从 Steam 商店爬取游戏基础信息，支持并发爬取和数据库存储。
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional

from bs4 import BeautifulSoup

from src.config import Config, get_config
from src.database import DatabaseManager
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
        db: 数据库管理器。
    """

    def __init__(
        self,
        config: Optional[Config] = None,
        checkpoint: Optional[Checkpoint] = None,
        failure_manager: Optional[Any] = None,
    ):
        """初始化游戏爬虫。

        Args:
            config: 可选的配置对象。
            checkpoint: 可选的断点管理器。
            failure_manager: 可选的失败管理器。
        """
        self.config = config or get_config()
        self.client = HttpClient(self.config)
        self.checkpoint = checkpoint
        self.failure_manager = failure_manager
        self.db = DatabaseManager(self.config.output.db_path)

        # 构建基础 URL
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
            error_msg = f"获取游戏 {app_id} 详情失败: {e}"
            print(error_msg)
            if self.failure_manager:
                self.failure_manager.log_failure("game", app_id, str(e))

        return None

    def scrape_page_games(self, page: int) -> list[int]:
        """爬取指定页面的游戏 AppID 列表。

        Args:
            page: 页码。

        Returns:
            list[int]: 该页面的 AppID 列表。
        """
        params = {
            "category1": self.config.scraper.category,
            "sort_by": "_ASC",
            "page": str(page),
        }

        app_ids = []

        try:
            response = self.client.get(self.base_url, params=params, delay=False)
            soup = BeautifulSoup(response.text, "html.parser")

            games = soup.find_all("a", {"class": "search_result_row"})

            for game in games:
                app_id_str = game.get("data-ds-appid")
                if app_id_str:
                    app_ids.append(int(app_id_str))

        except Exception as e:
            print(f"爬取第 {page} 页列表失败: {e}")

        return app_ids

    def process_game(self, app_id: int) -> Optional[GameInfo]:
        """处理单个游戏：获取详情并保存。

        Args:
            app_id: 游戏 ID。

        Returns:
            Optional[GameInfo]: 游戏详情。
        """
        # 检查是否已在断点中完成 or 数据库中已存在
        if self.checkpoint and self.checkpoint.is_appid_completed(app_id):
            return None # Skip
        
        # 可选：如果数据库已有且不需要更新，也可以跳过
        # if self.db.is_game_exists(app_id): ...

        details = self.get_game_details(app_id)
        if details:
            self.db.save_game(details)
            print(f"已保存: {details.name} ({app_id})")
            
            if self.checkpoint:
                self.checkpoint.mark_appid_completed(app_id)
            
        return details

    def run(
        self,
        max_pages: Optional[int] = None,
    ) -> list[int]:
        """运行爬虫（并发模式）。

        Args:
            max_pages: 可选的最大页数限制。

        Returns:
            list[int]: 所有处理过的 app_id。
        """
        total_pages = self.get_total_pages()
        if max_pages:
            total_pages = min(total_pages, max_pages)

        print(f"开始爬取 {total_pages} 页，并发数: {self.config.scraper.max_workers}")
        
        all_app_ids = []

        # 1. 获取所有页面的 AppID (这部分可以是串行或适当并发，为了简单先串行或小并发)
        # 考虑到获取页面列表比较快，我们直接在主循环处理
        
        # 使用线程池并发处理游戏详情
        with ThreadPoolExecutor(max_workers=self.config.scraper.max_workers) as executor:
            for page in range(1, total_pages + 1):
                if self.checkpoint and self.checkpoint.is_page_completed(page):
                    print(f"跳过已完成的第 {page} 页")
                    continue

                print(f"正在读取第 {page}/{total_pages} 页列表...")
                app_ids = self.scrape_page_games(page)
                
                if not app_ids:
                    continue
                
                # 提交任务到线程池
                futures = {executor.submit(self.process_game, app_id): app_id for app_id in app_ids}
                
                for future in as_completed(futures):
                    app_id = futures[future]
                    try:
                        future.result()
                        all_app_ids.append(app_id)
                    except Exception as e:
                        print(f"处理游戏 {app_id} 异常: {e}")

                if self.checkpoint:
                    self.checkpoint.mark_page_completed(page)

        # 最终不再返回 GameInfo 对象列表，而是 AppID 列表，因为数据已入库
        return all_app_ids

    def get_app_ids(self) -> list[int]:
        """从数据库获取所有 app_id。"""
        return self.db.get_all_app_ids()
