"""
评价历史爬虫模块。

从 Steam 获取游戏的评价统计历史数据，支持并发爬取和数据库存储。
"""

from __future__ import annotations

import datetime
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, Optional

from src.config import Config, get_config
from src.database import DatabaseManager
from src.models import ReviewSnapshot
from src.utils.checkpoint import Checkpoint
from src.utils.http_client import HttpClient
from src.utils.ui import UIManager


class ReviewScraper:
    """Steam 评价历史爬虫。

    从 Steam API 获取游戏的评价统计历史数据。

    Attributes:
        config: 配置对象。
        client: HTTP 客户端。
        checkpoint: 断点管理器。
        db: 数据库管理器。
        ui: UI 管理器。
    """

    def __init__(
        self,
        config: Optional[Config] = None,
        checkpoint: Optional[Checkpoint] = None,
        failure_manager: Optional[Any] = None,
        ui_manager: Optional[UIManager] = None,
        stop_event: Optional[threading.Event] = None,
    ):
        """初始化评价爬虫。

        Args:
            config: 可选的配置对象。
            checkpoint: 可选的断点管理器。
            failure_manager: 可选的失败管理器。
            ui_manager: 可选的 UI 管理器。
            stop_event: 可选的停止事件标志。
        """
        self.config = config or get_config()
        self.client = HttpClient(self.config)
        self.checkpoint = checkpoint
        self.failure_manager = failure_manager
        self.db = DatabaseManager(self.config.output.db_path)
        self.ui = ui_manager or UIManager()
        self.stop_event = stop_event

    def scrape_reviews(self, app_id: int, force: bool = False) -> list[ReviewSnapshot]:
        """爬取指定游戏的评价历史数据并保存。

        Args:
            app_id: Steam 游戏 ID。
            force: 强制模式，跳过失败标记检查（用于 retry 场景）。

        Returns:
            list[ReviewSnapshot]: 评价快照列表。
        """
        # 检查断点（使用 review 专用状态）
        if self.checkpoint and self.checkpoint.is_appid_completed(app_id, "review"):
            return []
        # force=True 时跳过失败检查，用于 retry 场景
        if self.checkpoint and self.checkpoint.is_appid_failed(app_id, "review") and not force:
            return []

        url = (
            f"https://store.steampowered.com/appreviewhistogram/{app_id}"
            f"?l=schinese&review_score_preference=0"
        )

        reviews: list[ReviewSnapshot] = []

        try:
            data = self.client.get_json(url, delay=True)
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
            
            # 保存到数据库
            if reviews:
                self.db.save_reviews(app_id, reviews)
                if self.checkpoint:
                    self.checkpoint.mark_appid_completed(app_id, "review")
                # print(f"已保存游戏 {app_id} 的 {len(reviews)} 条评价记录")

        except Exception as e:
            error_msg = f"爬取游戏 {app_id} 评价历史失败: {e}"
            self.ui.print_error(error_msg)
            if self.failure_manager:
                self.failure_manager.log_failure("review", app_id, str(e))
            if self.checkpoint:
                self.checkpoint.mark_appid_failed(app_id, "review")

        return reviews

    def scrape_from_file(
        self,
        file_path: str | Path,
    ) -> None:
        """从文件读取 app_id 列表并批量爬取评价数据。

        Args:
            file_path: 包含 app_id 的文件路径（每行一个 ID）。
        """
        file_path = Path(file_path)
        if not file_path.exists():
            self.ui.print_error(f"文件 {file_path} 不存在")
            return

        app_ids = []
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                appid_str = line.strip()
                if not appid_str:
                    continue
                try:
                    app_ids.append(int(appid_str))
                except ValueError:
                    self.ui.print_warning(f"无效的 AppID: {appid_str}")

        self.scrape_from_list(app_ids)

    def scrape_from_list(
        self,
        app_ids: list[int],
    ) -> None:
        """从列表批量爬取评价数据（并发）。

        Args:
            app_ids: app_id 列表。
        """
        self.ui.print_info(
            f"开始爬取 {len(app_ids)} 个游戏的评价，并发数: {self.config.scraper.max_workers}"
        )

        with self.ui.create_progress() as progress:
            task = progress.add_task("[green]抓取评价...", total=len(app_ids))

            with ThreadPoolExecutor(max_workers=self.config.scraper.max_workers) as executor:
                futures = {}
                for app_id in app_ids:
                    if self.stop_event and self.stop_event.is_set():
                        break
                    futures[executor.submit(self.scrape_reviews, app_id)] = app_id

                for future in as_completed(futures):
                    app_id = futures[future]
                    try:
                        future.result()
                    except Exception as e:
                        self.ui.print_error(f"处理游戏 {app_id} 评价异常: {e}")
                    finally:
                        progress.update(task, advance=1)
