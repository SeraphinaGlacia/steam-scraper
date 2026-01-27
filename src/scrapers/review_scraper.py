"""
评价历史爬虫模块。

从 Steam 获取游戏的评价统计历史数据，支持异步并发爬取和数据库存储。
与游戏信息爬虫不同，评价数据来自 reviewhistogram API，
返回的是每天的好评/差评数量统计。
"""

from __future__ import annotations

import asyncio
import datetime
import threading
from pathlib import Path
from typing import Any, Optional

from src.config import Config, get_config
from src.database import DatabaseManager
from src.models import ReviewSnapshot
from src.utils.checkpoint import Checkpoint
from src.utils.http_client import AsyncHttpClient
from src.utils.ui import UIManager


class ReviewScraper:
    """Steam 评价历史爬虫（异步版本）。

    从 Steam API 获取游戏的评价统计历史数据。
    使用 asyncio 实现真正的非阻塞并发，显著提升爬取效率。

    Attributes:
        config: 配置对象。
        client: 异步 HTTP 客户端。
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
        self.client = AsyncHttpClient(self.config)
        self.checkpoint = checkpoint
        self.failure_manager = failure_manager
        self.db = DatabaseManager(self.config.output.db_path)
        self.ui = ui_manager or UIManager()
        self.stop_event = stop_event

    async def scrape_reviews(
        self, app_id: int, force: bool = False, commit_db: bool = True
    ) -> tuple[list[ReviewSnapshot], bool]:
        """爬取指定游戏的评价历史数据并保存。

        Args:
            app_id (int): Steam 游戏 ID。
            force (bool): 强制模式，跳过失败标记检查（用于 retry 场景）。默认为 False。
            commit_db (bool): 是否立即提交数据库事务和更新断点。默认为 True。

        Returns:
            tuple[list[ReviewSnapshot], bool]: (评价快照列表, 是否跳过重复)
        """
        # 检查断点（使用 review 专用状态，同时检测重复）
        if self.checkpoint and self.checkpoint.is_appid_completed(app_id, "review"):
            return [], True  # 跳过重复
        # force=True 时跳过失败检查，用于 retry 场景
        if self.checkpoint and self.checkpoint.is_appid_failed(app_id, "review") and not force:
            return [], False

        url = (
            f"https://store.steampowered.com/appreviewhistogram/{app_id}"
            f"?l=schinese&review_score_preference=0"
        )

        reviews: list[ReviewSnapshot] = []

        try:
            data = await self.client.get_json(url, delay=True)
            rollups = data.get("results", {}).get("rollups", [])

            for item in rollups:
                ts = item["date"]  # UNIX 时间戳（秒）
                positive = item["recommendations_up"]
                negative = item["recommendations_down"]

                # 将时间戳转换为 UTC+8（北京时间）
                # Steam API 返回的是 UTC 时间戳，需要加 8 小时转换为中国时区
                # 这样确保数据日期与用户习惯的本地时间一致
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
                self.db.save_reviews(app_id, reviews, commit=commit_db)
                if commit_db and self.checkpoint:
                    self.checkpoint.mark_appid_completed(app_id, "review")

        except Exception as e:
            error_msg = f"爬取游戏 {app_id} 评价历史失败: {e}"
            self.ui.print_error(error_msg)
            if self.failure_manager:
                self.failure_manager.log_failure("review", app_id, str(e))
            if self.checkpoint:
                self.checkpoint.mark_appid_failed(app_id, "review")

        return reviews, False

    async def scrape_from_file(
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

        await self.scrape_from_list(app_ids)

    async def scrape_from_list(
        self,
        app_ids: list[int],
    ) -> None:
        """从列表批量爬取评价数据（异步并发）。

        使用 asyncio.Semaphore 控制并发数，避免同时发起过多请求。
        相比 ThreadPoolExecutor，异步模式能更高效地利用系统资源。

        Args:
            app_ids: app_id 列表。
        """
        # 预处理：去重和断点跳过
        seen_appids: set[int] = set()
        skipped_appids: list[int] = []  # 本轮内动态重复（需汇报）
        unique_app_ids: list[int] = []

        for app_id in app_ids:
            # 情况1：本轮内已出现过（列表重复）→ 汇报
            if app_id in seen_appids:
                skipped_appids.append(app_id)
                continue
            seen_appids.add(app_id)
            # 情况2：断点中已完成 → 静默跳过，不汇报（这是 --resume 的预期行为）
            if self.checkpoint and self.checkpoint.is_appid_completed(app_id, "review"):
                continue
            unique_app_ids.append(app_id)

        self.ui.print_info(
            f"开始爬取 {len(unique_app_ids)} 个游戏的评价（跳过 {len(app_ids) - len(unique_app_ids) - len(skipped_appids)} 个已完成），"
            f"并发数: {self.config.scraper.max_workers}"
        )

        # 使用信号量限制并发数
        semaphore = asyncio.Semaphore(self.config.scraper.max_workers)
        # 批量提交的缓冲区
        pending_app_ids: list[int] = []
        BATCH_SIZE = 50

        async def limited_scrape(app_id: int) -> tuple[int, list[ReviewSnapshot]]:
            """带并发限制的评价爬取函数。
            
            Args:
                app_id (int): Steam 游戏 ID。
                
            Returns:
                tuple[int, list[ReviewSnapshot]]: (app_id, 评价快照列表)
            """
            async with semaphore:
                # 检查停止信号
                if self.stop_event and self.stop_event.is_set():
                    return app_id, []
                # 不再需要 skipped 返回值，因为断点跳过已在外层处理
                # 使用 commit_db=False 实现批量提交
                result, _ = await self.scrape_reviews(app_id, commit_db=False)
                return app_id, result

        with self.ui.create_progress() as progress:
            task = progress.add_task("[green]抓取评价...", total=len(unique_app_ids))

            # 创建所有任务（只处理不重复且未完成的）
            tasks = [limited_scrape(app_id) for app_id in unique_app_ids]

            # 使用 asyncio.as_completed 实现实时进度更新
            for future in asyncio.as_completed(tasks):
                try:
                    app_id, reviews = await future

                    # 如果成功爬取到数据，加入待提交列表
                    if reviews:
                        pending_app_ids.append(app_id)

                    # 批量提交逻辑
                    if len(pending_app_ids) >= BATCH_SIZE:
                        self.db.commit()
                        if self.checkpoint:
                            self.checkpoint.mark_appids_completed(pending_app_ids, "review")
                        pending_app_ids = []

                except Exception as e:
                    self.ui.print_error(f"处理评价异常: {e}")
                finally:
                    progress.update(task, advance=1)

            # 处理剩余的未提交数据
            if pending_app_ids:
                self.db.commit()
                if self.checkpoint:
                    self.checkpoint.mark_appids_completed(pending_app_ids, "review")

        # 输出跳过的重复 AppID 汇总（只汇报本轮内动态重复）
        if skipped_appids:
            self.ui.print_warning(
                f"跳过 {len(skipped_appids)} 个重复 AppID: {skipped_appids}"
            )

        # 关闭 HTTP 客户端释放资源
        await self.client.close()
