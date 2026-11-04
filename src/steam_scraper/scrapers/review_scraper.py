"""评价历史爬虫模块。

从 Steam 获取游戏的评价统计历史数据，支持异步并发爬取和数据库存储。
与游戏信息爬虫不同，评价数据来自 reviewhistogram API，
保留接口提供的月、周、日统计粒度及近期逐日数据。
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, ParamSpec

from steam_scraper.config import Config, get_config
from steam_scraper.database import DatabaseManager
from steam_scraper.models import ReviewGranularity, ReviewSnapshot
from steam_scraper.utils.checkpoint import Checkpoint
from steam_scraper.utils.failure_manager import FailureManager
from steam_scraper.utils.http_client import AsyncHttpClient
from steam_scraper.utils.ui import UIManager, terminal_text

_DbArgs = ParamSpec("_DbArgs")


def read_app_ids(file_path: str | Path, ui: UIManager | None = None) -> list[int]:
    """读取每行一个的正整数 AppID，跳过空行和非法值。

    Args:
        file_path: UTF-8 文本文件，允许带 BOM。
        ui: 可选的终端界面，用于报告被跳过的非法行。

    Returns:
        保留输入顺序和重复项的正整数 AppID 列表。

    Raises:
        OSError: 文件不存在、是目录或无法读取时抛出。
        UnicodeError: 文件不是有效 UTF-8 文本时抛出。
    """
    app_ids: list[int] = []
    with Path(file_path).open(encoding="utf-8-sig") as file:
        for line in file:
            app_id_text = line.strip()
            if not app_id_text:
                continue
            try:
                app_id = int(app_id_text)
            except ValueError:
                app_id = 0
            if app_id > 0:
                app_ids.append(app_id)
            elif ui:
                ui.print_warning(terminal_text(f"无效的 AppID: {app_id_text}"))
    return app_ids


def _review_snapshots(app_id: int, data: dict[str, Any]) -> list[ReviewSnapshot]:
    """解析完整评价响应，保留统计周期并优先采用近期逐日桶。

    Returns:
        按 UTC 周期起点和粒度去重的快照；合法的无评价响应返回空列表。

    Raises:
        ValueError: 接口报告失败，或响应结构、粒度和统计值无效。
    """
    results = data.get("results")
    if ("success" in data and data["success"] != 1) or not isinstance(results, dict):
        raise ValueError("Steam 返回了无效的评价历史响应")

    rollup_type = results.get("rollup_type")
    if rollup_type in ("day", "week", "month"):
        rollup_granularity: ReviewGranularity = rollup_type
    elif rollup_type is None:
        rollup_granularity = "unknown"
    else:
        raise ValueError(f"Steam 返回了未知的评价统计粒度: {rollup_type}")

    if "rollups" not in results:
        # 无评价游戏实际省略 rollups；要求完整的空历史标记，不能将任意缺字段响应视为成功。
        if (
            data.get("success") == 1
            and "start_date" in results
            and "end_date" in results
            and results["start_date"] in (None, 0)
            and results["end_date"] in (None, 0)
            and results.get("weeks") == []
            and results.get("recent", []) == []
        ):
            return []
        raise ValueError("Steam 返回了无效的评价历史响应")

    rollups = results["rollups"]
    recent = results.get("recent", [])
    if not isinstance(rollups, list) or not isinstance(recent, list):
        raise ValueError("Steam 返回了无效的评价统计列表")

    snapshots: dict[tuple[date, ReviewGranularity], ReviewSnapshot] = {}
    groups: list[tuple[list[Any], ReviewGranularity]] = [
        (rollups, rollup_granularity),
        (recent, "day"),
    ]
    for records, granularity in groups:
        for item in records:
            if not isinstance(item, dict):
                raise ValueError("Steam 返回了无效的评价统计记录")
            values = [
                item.get("date"),
                item.get("recommendations_up"),
                item.get("recommendations_down"),
            ]
            if any(
                not isinstance(value, int) or isinstance(value, bool) or value < 0
                for value in values
            ):
                raise ValueError("Steam 返回了无效的评价时间或数量")
            timestamp, positive, negative = values
            # 时间戳标识统计桶的 UTC 起点，不能按用户时区平移日期。
            bucket_date = datetime.fromtimestamp(timestamp, tz=timezone.utc).date()
            snapshot = ReviewSnapshot(
                app_id=app_id,
                date=bucket_date,
                recommendations_up=positive,
                recommendations_down=negative,
                granularity=granularity,
            )
            snapshots[(bucket_date, granularity)] = snapshot
    return list(snapshots.values())


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
        config: Config | None = None,
        checkpoint: Checkpoint | None = None,
        failure_manager: FailureManager | None = None,
        ui_manager: UIManager | None = None,
        stop_event: threading.Event | None = None,
    ) -> None:
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
        self._db_lock = asyncio.Lock()

    async def _run_db(
        self,
        operation: Callable[_DbArgs, None],
        *args: _DbArgs.args,
        **kwargs: _DbArgs.kwargs,
    ) -> None:
        """串行执行数据库操作，取消时也等待写入线程结束。

        Raises:
            asyncio.CancelledError: 取消发生后，在途数据库操作结束时抛出。
        """
        async with self._db_lock:
            write_task = asyncio.create_task(
                asyncio.to_thread(operation, *args, **kwargs)
            )
            try:
                await asyncio.shield(write_task)
            except asyncio.CancelledError:
                # 线程不会随协程取消，必须持锁等写入结束才允许关闭连接。
                await write_task
                raise

    async def scrape_reviews(
        self, app_id: int, force: bool = False, commit_db: bool = True
    ) -> tuple[list[ReviewSnapshot] | None, bool]:
        """爬取指定游戏的评价历史数据并保存。

        Args:
            app_id: Steam 游戏 ID。
            force: 强制模式，跳过失败标记检查（用于 retry 场景）。默认为 False。
            commit_db: 是否立即提交数据库事务和更新断点。默认为 True。

        Returns:
            评价快照列表和“是否跳过重复项”标记。空列表表示成功但没有评价，
            None 表示失败或跳过已失败任务。
        """
        # 检查断点（使用 review 专用状态，同时检测重复）
        if self.checkpoint and self.checkpoint.is_appid_completed(app_id, "review"):
            return [], True  # 跳过重复
        # force=True 时跳过失败检查，用于 retry 场景
        if (
            self.checkpoint
            and self.checkpoint.is_appid_failed(app_id, "review")
            and not force
        ):
            return None, False

        url = (
            f"https://store.steampowered.com/appreviewhistogram/{app_id}"
            f"?l=schinese&review_score_preference=0"
        )

        reviews: list[ReviewSnapshot] = []

        try:
            data = await self.client.get_json(url, delay=True)
            reviews = _review_snapshots(app_id, data)

            # 空历史也要替换旧快照，避免已消失的数据继续留在数据库。
            await self._run_db(self.db.save_reviews, app_id, reviews, commit=commit_db)
            if commit_db:
                if self.checkpoint:
                    self.checkpoint.mark_appid_completed(app_id, "review")
                if self.failure_manager:
                    self.failure_manager.remove_failure("review", app_id)

        except Exception as e:
            error_msg = f"爬取游戏 {app_id} 评价历史失败: {e}"
            self.ui.print_error(terminal_text(error_msg))
            if self.failure_manager:
                self.failure_manager.log_failure("review", app_id, str(e))
            if self.checkpoint:
                self.checkpoint.mark_appid_failed(app_id, "review")
            return None, False

        return reviews, False

    async def scrape_from_file(
        self,
        file_path: str | Path,
    ) -> None:
        """从文件读取 app_id 列表并批量爬取评价数据。

        Args:
            file_path: 包含 app_id 的文件路径（每行一个 ID）。

        Raises:
            OSError: 输入文件不存在或无法读取时抛出。
            UnicodeError: 输入文件不是有效 UTF-8 文本时抛出。
        """
        await self.scrape_from_list(read_app_ids(file_path, self.ui))

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
        batch_size = 50
        aborted = False

        async def limited_scrape(
            app_id: int,
        ) -> tuple[int, list[ReviewSnapshot] | None]:
            """带并发限制的评价爬取函数。

            Args:
                app_id: Steam 游戏 ID。

            Returns:
                AppID 与对应评价快照列表组成的元组。
            """
            async with semaphore:
                # 检查停止信号
                if aborted or (self.stop_event and self.stop_event.is_set()):
                    return app_id, None
                # 不再需要 skipped 返回值，因为断点跳过已在外层处理
                # 使用 commit_db=False 实现批量提交
                result, _ = await self.scrape_reviews(app_id, commit_db=False)
                return app_id, result

        async def commit_pending() -> None:
            """先提交评价事务，再持久化完成状态；提交失败交给调用方处理。"""
            await self._run_db(self.db.commit)
            if self.checkpoint:
                self.checkpoint.mark_appids_completed(pending_app_ids, "review")
            if self.failure_manager:
                for app_id in pending_app_ids:
                    self.failure_manager.remove_failure("review", app_id)
            pending_app_ids.clear()

        tasks = [
            asyncio.create_task(limited_scrape(app_id)) for app_id in unique_app_ids
        ]
        try:
            with self.ui.create_progress() as progress:
                task = progress.add_task(
                    "[green]抓取评价...", total=len(unique_app_ids)
                )

                for future in asyncio.as_completed(tasks):
                    app_id, reviews = await future
                    # 成功的空结果也必须完成断点，失败不能冒充成功。
                    if reviews is not None:
                        pending_app_ids.append(app_id)
                    if len(pending_app_ids) >= batch_size:
                        await commit_pending()
                    progress.update(task, advance=1)

                if pending_app_ids:
                    await commit_pending()
        finally:
            # to_thread 的写入无法随协程取消；先停止调度并等在途写入结束。
            aborted = True
            await asyncio.gather(*tasks, return_exceptions=True)
            await self.client.close()

        # 输出跳过的重复 AppID 汇总（只汇报本轮内动态重复）
        if skipped_appids:
            self.ui.print_warning(
                f"跳过 {len(skipped_appids)} 个重复 AppID: {skipped_appids}"
            )
