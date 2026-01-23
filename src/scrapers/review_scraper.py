"""
评价历史爬虫模块。

从 Steam 获取游戏的评价统计历史数据。
"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Callable, Optional

from src.config import Config, get_config
from src.models import ReviewSnapshot
from src.utils.checkpoint import Checkpoint
from src.utils.http_client import HttpClient


class ReviewScraper:
    """Steam 评价历史爬虫。

    从 Steam API 获取游戏的评价统计历史数据。

    Attributes:
        config: 配置对象。
        client: HTTP 客户端。
        checkpoint: 断点管理器。
    """

    def __init__(
        self,
        config: Optional[Config] = None,
        checkpoint: Optional[Checkpoint] = None,
        failure_manager: Optional[Any] = None,
    ):
        """初始化评价爬虫。

        Args:
            config: 可选的配置对象。
            checkpoint: 可选的断点管理器。
            failure_manager: 可选的失败管理器。
        """
        self.config = config or get_config()
        self.client = HttpClient(self.config)
        self.checkpoint = checkpoint
        self.failure_manager = failure_manager

    def scrape_reviews(self, app_id: int) -> list[ReviewSnapshot]:
        """爬取指定游戏的评价历史数据。

        Args:
            app_id: Steam 游戏 ID。

        Returns:
            list[ReviewSnapshot]: 评价快照列表。
        """
        url = (
            f"https://store.steampowered.com/appreviewhistogram/{app_id}"
            f"?l=schinese&review_score_preference=0"
        )

        reviews: list[ReviewSnapshot] = []

        try:
            data = self.client.get_json(url, delay=False)
            rollups = data.get("results", {}).get("rollups", [])

            for item in rollups:
                ts = item["date"]  # UNIX 时间戳（秒）
                positive = item["recommendations_up"]
                negative = item["recommendations_down"]

                # 转换时间戳为 UTC+8（北京时间）
                dt_utc = datetime.datetime.utcfromtimestamp(ts)
                dt_local = dt_utc + datetime.timedelta(hours=8)

                review = ReviewSnapshot(
                    app_id=app_id,
                    date=dt_local.date(),
                    recommendations_up=positive,
                    recommendations_down=negative,
                )
                reviews.append(review)

        except Exception as e:
            error_msg = f"爬取游戏 {app_id} 评价历史失败: {e}"
            print(error_msg)
            if self.failure_manager:
                self.failure_manager.log_failure("review", app_id, str(e))
            if self.checkpoint:
                self.checkpoint.mark_appid_failed(app_id)

        return reviews

    def scrape_from_file(
        self,
        file_path: str | Path,
        on_complete: Optional[Callable[[int, list[ReviewSnapshot]], None]] = None,
    ) -> dict[int, list[ReviewSnapshot]]:
        """从文件读取 app_id 列表并批量爬取评价数据。

        Args:
            file_path: 包含 app_id 的文件路径（每行一个 ID）。
            on_complete: 可选的完成回调函数，每个游戏爬取完成后调用。

        Returns:
            dict[int, list[ReviewSnapshot]]: app_id 到评价列表的映射。
        """
        file_path = Path(file_path)
        if not file_path.exists():
            print(f"文件 {file_path} 不存在")
            return {}

        all_reviews: dict[int, list[ReviewSnapshot]] = {}

        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                appid_str = line.strip()
                if not appid_str:
                    continue

                try:
                    app_id = int(appid_str)

                    # 检查断点
                    if self.checkpoint and self.checkpoint.is_appid_completed(app_id):
                        print(f"跳过已完成的游戏 {app_id}")
                        continue

                    reviews = self.scrape_reviews(app_id)
                    all_reviews[app_id] = reviews

                    if self.checkpoint:
                        self.checkpoint.mark_appid_completed(app_id)

                    if on_complete:
                        on_complete(app_id, reviews)

                    print(f"已爬取游戏 {app_id} 的 {len(reviews)} 条评价记录")

                except ValueError:
                    print(f"[警告] 无效的 AppID: {appid_str}")

        return all_reviews

    def scrape_from_list(
        self,
        app_ids: list[int],
        on_complete: Optional[Callable[[int, list[ReviewSnapshot]], None]] = None,
    ) -> dict[int, list[ReviewSnapshot]]:
        """从列表批量爬取评价数据。

        Args:
            app_ids: app_id 列表。
            on_complete: 可选的完成回调函数。

        Returns:
            dict[int, list[ReviewSnapshot]]: app_id 到评价列表的映射。
        """
        all_reviews: dict[int, list[ReviewSnapshot]] = {}

        for app_id in app_ids:
            # 检查断点
            if self.checkpoint and self.checkpoint.is_appid_completed(app_id):
                print(f"跳过已完成的游戏 {app_id}")
                continue

            reviews = self.scrape_reviews(app_id)
            all_reviews[app_id] = reviews

            if self.checkpoint:
                self.checkpoint.mark_appid_completed(app_id)

            if on_complete:
                on_complete(app_id, reviews)

            print(f"已爬取游戏 {app_id} 的 {len(reviews)} 条评价记录")

        return all_reviews
