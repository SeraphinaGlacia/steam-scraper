"""游戏信息爬虫模块。

从 Steam 商店爬取游戏基础信息，支持异步并发爬取和数据库存储。
"""

from __future__ import annotations

import asyncio
import re
import threading
from html import unescape

import httpx

from steam_scraper.config import Config, get_config
from steam_scraper.database import DatabaseManager
from steam_scraper.models import GameInfo
from steam_scraper.utils.checkpoint import Checkpoint
from steam_scraper.utils.failure_manager import FailureManager
from steam_scraper.utils.http_client import AsyncHttpClient
from steam_scraper.utils.ui import UIManager

_RESULTS_PER_PAGE = 25


class SteamSearchError(RuntimeError):
    """搜索请求或响应解析失败，当前游戏采集必须停止并从断点恢复。"""


def _is_empty_search(html: str) -> bool:
    """检查 Steam 结果计数组件是否明确显示零条结果。

    Returns:
        只有可识别的零结果说明返回 True；缺失或未知页面结构返回 False。
    """
    match = re.search(
        r'<div\b[^>]*class=[\'"][^\'"]*\bsearch_results_count\b[^\'"]*[\'"]'
        r"[^>]*>(.*?)</div>",
        html,
        re.DOTALL,
    )
    if match is None:
        return False
    # 结果说明会随商店语言变化；首个数字始终是匹配结果数。
    text = re.sub(r"<[^>]+>", " ", unescape(match.group(1)))
    count = re.search(r"\d[\d,]*", text)
    return count is not None and int(count.group().replace(",", "")) == 0


class GameScraper:
    """Steam 游戏信息爬虫（异步版本）。

    从 Steam 商店搜索页面爬取游戏列表，并获取每个游戏的详细信息。
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
        """初始化游戏爬虫。

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

        self.base_url = "https://store.steampowered.com/search/"

    async def get_total_pages(self) -> int:
        """获取搜索结果的总页数；明确没有结果时返回零。

        Returns:
            已从 Steam 响应确认的总页数。

        Raises:
            SteamSearchError: 请求失败或响应没有可识别的结果计数。
        """
        # 计数解析使用固定语言；地区仍需保留，以匹配实际扫描的商店结果。
        params = {
            "category1": self.config.scraper.category,
            "page": "1",
            "l": "english",
            "cc": self.config.scraper.currency,
        }

        try:
            response = await self.client.get(self.base_url, params=params, delay=False)
        except httpx.HTTPError as exc:
            raise SteamSearchError(f"获取搜索结果总页数失败: {exc}") from exc

        html = response.text
        match = re.search(
            r'class="search_pagination_left"[^>]*>[^<]*of\s+([0-9][0-9,]*)',
            html,
            re.IGNORECASE,
        ) or re.search(
            r"Showing [\d,]+ - [\d,]+ of ([0-9][0-9,]*)", html, re.IGNORECASE
        )
        if match is not None:
            total_results = int(match.group(1).replace(",", ""))
            return (total_results + _RESULTS_PER_PAGE - 1) // _RESULTS_PER_PAGE
        if _is_empty_search(html):
            return 0
        raise SteamSearchError("无法解析 Steam 搜索结果总数，采集已停止，请稍后重试")

    async def get_game_details(self, app_id: int) -> GameInfo | None:
        """获取单个游戏的详细信息。

        Args:
            app_id: Steam 游戏 ID。

        Returns:
            游戏信息对象，获取失败时返回 None。
        """
        url = (
            f"https://store.steampowered.com/api/appdetails"
            f"?appids={app_id}"
            f"&l={self.config.scraper.language}"
            f"&cc={self.config.scraper.currency}"
        )

        try:
            data = await self.client.get_json(url)

            if data.get(str(app_id), {}).get("success"):
                game_data = data[str(app_id)]["data"]
                return GameInfo.from_api_response(app_id, game_data)
            else:
                # API 返回 success=false，可能是 DLC、已下架游戏等
                # 静默记录失败，不在终端打印错误避免刷屏
                if self.failure_manager:
                    self.failure_manager.log_failure(
                        "game", app_id, "API returned success=false (可能是 DLC/已下架)"
                    )

        except Exception as e:
            error_msg = f"获取游戏 {app_id} 详情失败: {e}"
            self.ui.print_error(error_msg)
            if self.failure_manager:
                self.failure_manager.log_failure("game", app_id, str(e))

        return None

    async def scrape_page_games(self, page: int) -> list[int]:
        """爬取指定页面的游戏 AppID 列表。

        Args:
            page: 页码。

        Returns:
            该页面的 AppID 列表；只有明确的零结果页面返回空列表。

        Raises:
            SteamSearchError: 请求失败、AppID 无效或响应不是可识别的搜索结果。
        """
        params = {
            "category1": self.config.scraper.category,
            "sort_by": "_ASC",
            "page": str(page),
            "l": self.config.scraper.language,
            "cc": self.config.scraper.currency,
        }

        try:
            response = await self.client.get(self.base_url, params=params, delay=False)
        except httpx.HTTPError as exc:
            raise SteamSearchError(f"爬取第 {page} 页列表失败: {exc}") from exc

        html = response.text
        app_ids = []
        for match in re.finditer(r'data-ds-appid="([^"]*)"', html):
            # 捆绑包继续只取首个 AppID，但不能在解析失败时返回半页结果。
            first_id = match.group(1).split(",")[0]
            if not first_id.isdecimal() or int(first_id) <= 0:
                raise SteamSearchError(f"第 {page} 页包含无效 AppID，采集已停止")
            app_ids.append(int(first_id))

        if app_ids or _is_empty_search(html):
            return app_ids
        raise SteamSearchError(f"无法解析第 {page} 页游戏列表，采集已停止")

    async def process_game(
        self,
        app_id: int,
        force: bool = False,
        commit_db: bool = True,
        save_to_db: bool = True,
    ) -> tuple[GameInfo | None, bool]:
        """处理单个游戏：获取详情并保存。

        此方法会先检查断点状态，跳过已完成或已失败的 AppID。
        无论爬取成功还是失败，都会更新断点状态，确保：
        - 成功的 AppID 不会重复爬取
        - 失败的 AppID 被标记，避免无限重试

        Args:
            app_id: Steam 游戏 ID。
            force: 强制模式，跳过失败标记检查（用于 retry 场景）。默认为 False。
            commit_db: 是否立即提交数据库事务和更新断点。默认为 True。
                - 单个处理（如 retry）时应为 True，确保数据安全。
                - 批量处理（如 run）时应为 False，由调用方统一提交以提升性能。
            save_to_db: 是否保存到数据库。默认为 True。
                - 批量处理时设为 False，由调用方收集后批量插入。

        Returns:
            包含游戏详情和“是否跳过重复项”标记的元组：
                - 成功时返回 (游戏详情对象, False)
                - 跳过重复时返回 (None, True)
                - 失败时返回 (None, False)

        Raises:
            asyncio.CancelledError: 任务取消时，等待已启动的数据库写入完成后抛出。
        """
        # 1. 检查是否已在断点中完成（重复 AppID）
        if self.checkpoint and self.checkpoint.is_appid_completed(app_id):
            return None, True  # 跳过重复

        # 2. 检查是否已标记为失败（避免重复尝试已知不可爬取的 ID）
        # force=True 时跳过此检查，用于 retry 场景
        if self.checkpoint and self.checkpoint.is_appid_failed(app_id) and not force:
            return None, False

        # 3. 尝试获取游戏详情
        details = await self.get_game_details(app_id)

        if details:
            # 成功：根据 flag 决定是否保存到数据库
            if save_to_db:
                save_task = asyncio.create_task(
                    asyncio.to_thread(self.db.save_game, details, commit=commit_db)
                )
                try:
                    await asyncio.shield(save_task)
                except asyncio.CancelledError:
                    # SQLite 写入线程无法取消；退出前等它结束，避免关闭连接的竞态。
                    await save_task
                    raise

            # 如果是立即提交模式（如 retry），则立即更新断点
            # 否则（如 run 批量模式），由调用方确认 DB 提交后再更新断点
            if commit_db and save_to_db:
                if self.checkpoint:
                    self.checkpoint.mark_appid_completed(app_id)
                if self.failure_manager:
                    self.failure_manager.remove_failure("game", app_id)
        else:
            # 失败：标记为失败，避免后续死循环重试
            # 这些 ID 可通过 `uv run steam-scraper retry` 命令专门处理
            if self.checkpoint:
                self.checkpoint.mark_appid_failed(app_id)

        return details, False

    async def run(
        self,
        max_pages: int | None = None,
    ) -> list[int]:
        """运行爬虫（高效生产者-消费者模型）。

        架构设计:
        1. Producer (生产者): 扫描搜索结果页，提取 AppID -> id_queue
        2. Worker (消费者): 处理 AppID，获取详情 -> result_queue
        3. Committer (提交者): 收集结果，批量写入 DB 和更新 Checkpoint

        Args:
            max_pages: 可选的最大页数限制。

        Returns:
            list[int]: 所有处理过的 app_id。

        Raises:
            SteamSearchError: 搜索计数或列表页失败，已完成的数据保留以供恢复。
            asyncio.CancelledError: 任务取消时，等待在途任务和已启动的写入结束后抛出。
        """
        id_queue: asyncio.Queue[int] = asyncio.Queue(
            maxsize=self.config.scraper.max_workers * 2
        )
        result_queue: asyncio.Queue[tuple[int, GameInfo | None, bool] | None] = (
            asyncio.Queue()
        )

        # 统计数据
        seen_appids: set[int] = set()
        skipped_appids: list[int] = []
        all_app_ids: list[int] = []
        pending_pages: dict[int, set[int]] = {}
        commit_errors: list[Exception] = []
        stop_event = self.stop_event or threading.Event()

        def mark_ready_pages() -> None:
            """仅在整页结果已持久化后保存页面断点，避免恢复时丢失排队任务。"""
            if self.checkpoint is None:
                return
            for page, app_ids in list(pending_pages.items()):
                if all(
                    self.checkpoint.is_appid_completed(app_id)
                    or self.checkpoint.is_appid_failed(app_id)
                    for app_id in app_ids
                ):
                    self.checkpoint.mark_page_completed(page)
                    del pending_pages[page]

        # 1. 生产者任务：扫描页面
        async def producer() -> None:
            """生产 AppID 任务。

            遍历搜索结果页面，提取 AppID 并放入任务队列。
            """
            for page in range(1, total_pages + 1):
                if stop_event.is_set():
                    break

                if self.checkpoint and self.checkpoint.is_page_completed(page):
                    progress.update(page_task, advance=1)
                    continue

                app_ids = await self.scrape_page_games(page)
                progress.update(page_task, advance=1)

                if not app_ids:
                    continue

                pending_pages[page] = set(app_ids)

                # 推送 ID 到队列
                for app_id in app_ids:
                    if app_id in seen_appids:
                        skipped_appids.append(app_id)
                        continue

                    seen_appids.add(app_id)
                    # 如果已经在 checkpoint 中完成，则不加入队列（完全跳过）
                    if self.checkpoint and self.checkpoint.is_appid_completed(app_id):
                        skipped_appids.append(app_id)
                        continue

                    await id_queue.put(app_id)
                    current_total = progress.tasks[game_task].total or 0
                    progress.update(game_task, total=current_total + 1)

                mark_ready_pages()

        # 2. 消费者任务：处理游戏
        async def worker() -> None:
            """处理游戏详情任务。

            从队列获取 AppID，爬取详情，并将结果发送给 Committer。
            """
            while True:
                app_id = await id_queue.get()
                try:
                    if stop_event.is_set():
                        continue

                    # 核心处理逻辑
                    # commit_db=False, save_to_db=False (结果交给 Committer 处理)
                    game_info, skipped = await self.process_game(
                        app_id, commit_db=False, save_to_db=False
                    )

                    # 将结果放入结果队列
                    await result_queue.put((app_id, game_info, skipped))

                except Exception as e:
                    self.ui.print_error(f"Worker Error {app_id}: {e}")
                finally:
                    id_queue.task_done()
                    progress.update(game_task, advance=1)

        # 3. 提交者任务：批量写入
        async def committer() -> None:
            """批量提交数据到数据库。

            从结果队列收集数据，满足批次大小或时间间隔后批量写入数据库，
            既能提高写入性能，又能减少磁盘 I/O 频率。
            """
            buffer_games: list[GameInfo] = []
            buffer_ids: list[int] = []  # 成功的 ID
            failed_ids: list[int] = []  # 失败的 ID

            # 定时提交或缓冲区满提交
            while True:
                # 获取结果，设置超时以便执行定期提交
                try:
                    # 500ms 超时，确保每秒至少检查两次是否需要提交
                    result = await asyncio.wait_for(result_queue.get(), timeout=0.5)

                    if result is None:
                        result_queue.task_done()
                        break

                    app_id, game_info, skipped = result
                    all_app_ids.append(app_id)  # 记录所有处理过的ID

                    if game_info:
                        buffer_games.append(game_info)
                        buffer_ids.append(app_id)
                    elif not skipped:
                        # 既无数据也非跳过，说明是失败
                        failed_ids.append(app_id)

                    result_queue.task_done()

                except asyncio.TimeoutError:
                    pass
                except asyncio.CancelledError:
                    break

                # 检查是否需要提交
                if len(buffer_games) >= 50 or (
                    buffer_games and id_queue.empty() and result_queue.empty()
                ):
                    try:
                        await _commit_batch_impl(buffer_games, buffer_ids, failed_ids)
                    except Exception as e:
                        self.ui.print_error(f"严重错误：批量提交到数据库失败: {e}")
                        commit_errors.append(e)
                        stop_event.set()
                    finally:
                        buffer_games.clear()
                        buffer_ids.clear()
                        failed_ids.clear()

            # 最后的提交
            if buffer_games or failed_ids:
                try:
                    await _commit_batch_impl(buffer_games, buffer_ids, failed_ids)
                except Exception as e:
                    self.ui.print_error(f"最后一次提交失败: {e}")
                    commit_errors.append(e)
                    stop_event.set()

        # 辅助：批量提交实现
        async def _commit_batch_impl(
            games: list[GameInfo], success_ids: list[int], fail_ids: list[int]
        ) -> None:
            """执行批量提交操作。

            Args:
                games: 要保存的游戏对象列表。
                success_ids: 处理成功的 AppID 列表（用于更新断点）。
                fail_ids: 处理失败的 AppID 列表（用于更新断点）。
            """
            if games:
                await asyncio.to_thread(self.db.save_games_batch, games, commit=True)

            if self.checkpoint:
                if success_ids:
                    self.checkpoint.mark_appids_completed(success_ids)
                if fail_ids:
                    for fid in fail_ids:
                        self.checkpoint.mark_appid_failed(fid)
                mark_ready_pages()
                # 每次批量操作后保存 Checkpoint 文件
                self.checkpoint.save()
            if self.failure_manager:
                for app_id in success_ids:
                    self.failure_manager.remove_failure("game", app_id)

        # --- 启动所有任务 ---

        try:
            total_pages = await self.get_total_pages()
            if max_pages:
                total_pages = min(total_pages, max_pages)
            self.ui.print_info(
                f"开始爬取 {total_pages} 页，并发数: {self.config.scraper.max_workers}"
            )

            with self.ui.create_progress() as progress:
                page_task = progress.add_task("[cyan]扫描页面...", total=total_pages)
                game_task = progress.add_task("[green]处理数据...", total=0)

                committer_task = asyncio.create_task(committer())
                workers = [
                    asyncio.create_task(worker())
                    for _ in range(self.config.scraper.max_workers)
                ]

                async def finish_pipeline() -> None:
                    """收回在途任务并等待 SQLite 写入结束，之后才允许关闭连接。"""
                    for worker_task in workers:
                        worker_task.cancel()
                    await asyncio.gather(*workers, return_exceptions=True)
                    if not committer_task.done():
                        await result_queue.put(None)
                    await asyncio.gather(committer_task, return_exceptions=True)

                try:
                    await producer()
                    await id_queue.join()

                    # 所有 Worker 已交出结果，哨兵保证提交者处理完最后一批才退出。
                    await result_queue.put(None)
                    await asyncio.shield(committer_task)
                finally:
                    # 页面失败后的清理也可能收到取消，不能把取消传给写入任务。
                    cleanup_task = asyncio.create_task(finish_pipeline())
                    try:
                        await asyncio.shield(cleanup_task)
                    except asyncio.CancelledError:
                        await cleanup_task
                        raise
        finally:
            await self.client.close()

        if commit_errors:
            raise commit_errors[0]
        self.db.commit()

        # 输出跳过的 AppID 汇总 (包括重复项和已完成项)
        if skipped_appids:
            self.ui.print_warning(
                f"跳过 {len(skipped_appids)} 个 AppID (重复出现或已完成): {skipped_appids}"
            )

        return all_app_ids

    def get_app_ids(self) -> list[int]:
        """从数据库获取全部 AppID。

        Returns:
            数据库当前保存的全部 AppID。
        """
        return self.db.get_all_app_ids()
