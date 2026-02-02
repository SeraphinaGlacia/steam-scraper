"""
游戏信息爬虫模块。

从 Steam 商店爬取游戏基础信息，支持异步并发爬取和数据库存储。
"""

from __future__ import annotations

import re
import asyncio
import threading
from typing import Any, Optional

from src.config import Config, get_config
from src.database import DatabaseManager
from src.models import GameInfo
from src.utils.checkpoint import Checkpoint
from src.utils.http_client import AsyncHttpClient
from src.utils.ui import UIManager


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
        config: Optional[Config] = None,
        checkpoint: Optional[Checkpoint] = None,
        failure_manager: Optional[Any] = None,
        ui_manager: Optional[UIManager] = None,
        stop_event: Optional[threading.Event] = None,
    ):
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

        # 构建基础 URL
        self.base_url = (
            f"https://store.steampowered.com/search/"
            f"?l={self.config.scraper.language}"
            f"&cc={self.config.scraper.currency}"
        )

    async def get_total_pages(self) -> int:
        """获取搜索结果的总页数。

        Returns:
            int: 总页数。
        """
        params = {"category1": self.config.scraper.category, "page": "1"}

        try:
            response = await self.client.get(self.base_url, params=params, delay=False)
            # 使用正则直接提取，避免 BeautifulSoup 的解析开销
            # 目标文本: "Showing 1 - 25 of 69792"
            # 搜索 <div class="search_pagination_left">
            html = response.text
            match = re.search(r'class="search_pagination_left"[^>]*>.*?of\s+(\d+)', html, re.DOTALL)
            
            if match:
                total_results = int(match.group(1))
                return (total_results // 25) + 1
            else:
                # 备用方案：尝试匹配单纯的数字结构
                matches = re.findall(r'Showing \d+ - \d+ of (\d+)', html)
                if matches:
                    total_results = int(matches[0])
                    return (total_results // 25) + 1
                    
        except Exception as e:
            self.ui.print_error(f"获取总页数失败: {e}")

        # 默认值 5000 是 Steam 商店游戏总量的保守估计
        # 实际分页数会从 API 响应中获取，此值仅在解析失败时作为兜底
        return 5000

    async def get_game_details(self, app_id: int) -> Optional[GameInfo]:
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
            list[int]: 该页面的 AppID 列表。
        """
        params = {
            "category1": self.config.scraper.category,
            "sort_by": "_ASC",
            "page": str(page),
        }

        app_ids = []

        try:
            response = await self.client.get(self.base_url, params=params, delay=False)
            html = response.text
            
            # 使用正则直接提取 data-ds-appid
            # <a ... data-ds-appid="123456" ...
            # 或者 data-ds-appid="123,456" (捆绑包)
            matches = re.finditer(r'data-ds-appid="([^"]+)"', html)
            
            for match in matches:
                app_ids_str = match.group(1)
                # 处理逗号分隔的多 AppID 情况（捆绑包），只取第一个
                if ',' in app_ids_str:
                    first_id = app_ids_str.split(",")[0]
                    app_ids.append(int(first_id))
                else:
                    app_ids.append(int(app_ids_str))

        except Exception as e:
            self.ui.print_error(f"爬取第 {page} 页列表失败: {e}")

        except Exception as e:
            self.ui.print_error(f"爬取第 {page} 页列表失败: {e}")

        return app_ids

    async def process_game(
        self, app_id: int, force: bool = False, commit_db: bool = True, save_to_db: bool = True
    ) -> tuple[Optional[GameInfo], bool]:
        """处理单个游戏：获取详情并保存。

        此方法会先检查断点状态，跳过已完成或已失败的 AppID。
        无论爬取成功还是失败，都会更新断点状态，确保：
        - 成功的 AppID 不会重复爬取
        - 失败的 AppID 被标记，避免无限重试

        Args:
            app_id (int): Steam 游戏 ID。
            force (bool): 强制模式，跳过失败标记检查（用于 retry 场景）。默认为 False。
            commit_db (bool): 是否立即提交数据库事务和更新断点。默认为 True。
                - 单个处理（如 retry）时应为 True，确保数据安全。
                - 批量处理（如 run）时应为 False，由调用方统一提交以提升性能。
            save_to_db (bool): 是否保存到数据库。默认为 True。
                - 批量处理时设为 False，由调用方收集后批量插入。

        Returns:
            tuple[Optional[GameInfo], bool]: (游戏详情, 是否跳过重复)
                - 成功时返回 (游戏详情对象, False)
                - 跳过重复时返回 (None, True)
                - 失败时返回 (None, False)
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
                # 使用 to_thread 避免阻塞事件循环
                await asyncio.to_thread(self.db.save_game, details, commit=commit_db)
            
            # 如果是立即提交模式（如 retry），则立即更新断点
            # 否则（如 run 批量模式），由调用方确认 DB 提交后再更新断点
            if commit_db and self.checkpoint:
                self.checkpoint.mark_appid_completed(app_id)
        else:
            # 失败：标记为失败，避免后续死循环重试
            # 这些 ID 可通过 `python main.py retry` 命令专门处理
            if self.checkpoint:
                self.checkpoint.mark_appid_failed(app_id)

        return details, False

    async def run(
        self,
        max_pages: Optional[int] = None,
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
        """
        total_pages = await self.get_total_pages()
        if max_pages:
            total_pages = min(total_pages, max_pages)

        self.ui.print_info(
            f"开始爬取 {total_pages} 页，并发数: {self.config.scraper.max_workers}"
        )

        id_queue = asyncio.Queue(maxsize=self.config.scraper.max_workers * 2)
        result_queue = asyncio.Queue()
        
        # 统计数据
        # 统计数据
        seen_appids: set[int] = set()
        skipped_appids: list[int] = []  # 收集跳过的重复 AppID
        all_app_ids: list[int] = []
        
        # 1. 生产者任务：扫描页面
        async def producer():
            for page in range(1, total_pages + 1):
                if self.stop_event and self.stop_event.is_set():
                    break
                    
                if self.checkpoint and self.checkpoint.is_page_completed(page):
                    # 如果页面已标记完成，但我们需要知道这一页有哪些ID才能确保数据完整性？
                    # 不，如果页面完成了，说明里面的游戏都处理了（理想情况下）。
                    # 但为了安全，我们还是应该扫描它吗？
                    # Checkpoint 的定义是：该页面的所有游戏都已经*尝试*过处理。
                    # 所以我们可以通过。
                    progress.update(page_task, advance=1)
                    continue

                app_ids = await self.scrape_page_games(page)
                progress.update(page_task, advance=1)
                
                if not app_ids:
                    continue
                
                # 推送 ID 到队列
                # 推送 ID 到队列
                for app_id in app_ids:
                    if app_id in seen_appids:
                        skipped_appids.append(app_id)
                        continue
                        
                    seen_appids.add(app_id)
                    # 如果已经在 checkpoint 中完成，则不加入队列（完全跳过）
                    if self.checkpoint and self.checkpoint.is_appid_completed(app_id):
                        continue
                    
                    await id_queue.put(app_id)
                    progress.update(game_task, total=progress.tasks[game_task].total + 1)
                
                # 页面完成标记应该在所含游戏都处理完后吗？
                # 由于是异步流，我们不能立即标记页面完成。
                # 我们改为在 Committer 中不处理页面级 Checkpoint？
                # 或者：我们可以简化逻辑，不再使用 Page 级 Checkpoint，只依赖 AppID 级 Checkpoint。
                # 但为了兼容性，我们可以在 producer 结束时，或者 Committer 确认所有当前任务都完成时...
                # 实际上，Page Checkpoint 在流式架构下很难精确维护。
                # 建议：仅使用 AppID Checkpoint。Page Checkpoint 仅用于跳过完全扫描过的页。
                # 这里我们假设：如果 Producer 成功把 AppID 放入队列，该页就算“扫描”过了。
                if self.checkpoint:
                    self.checkpoint.mark_page_completed(page)
            
            # 生产者结束，放入 None 标记给 Consumers（每个 consumer 一个）
            # 或者更简单的：Producer 结束后，等待 Queue join
            pass

        # 2. 消费者任务：处理游戏
        async def worker():
            while True:
                app_id = await id_queue.get()
                try:
                    if self.stop_event and self.stop_event.is_set():
                        id_queue.task_done()
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
        async def committer():
            buffer_games: list[GameInfo] = []
            buffer_ids: list[int] = []  # 成功的 ID
            failed_ids: list[int] = []  # 失败的 ID
            
            # 定时提交或缓冲区满提交
            while True:
                # 获取结果，设置超时以便执行定期提交
                try:
                    # 500ms 超时，确保每秒至少检查两次是否需要提交
                    result = await asyncio.wait_for(result_queue.get(), timeout=0.5)
                    
                    app_id, game_info, skipped = result
                    all_app_ids.append(app_id) # 记录所有处理过的ID
                    
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
                if len(buffer_games) >= 50 or (buffer_games and id_queue.empty() and result_queue.empty()):
                    await self._commit_batch(buffer_games, buffer_ids, failed_ids)
                    buffer_games.clear()
                    buffer_ids.clear()
                    failed_ids.clear()
                    
                if self.stop_event and self.stop_event.is_set() and result_queue.empty():
                    break

            # 最后的提交
            if buffer_games or failed_ids:
                await self._commit_batch(buffer_games, buffer_ids, failed_ids)

        # 辅助：批量提交实现
        async def _commit_batch_impl(games, success_ids, fail_ids):
            if games:
                await asyncio.to_thread(self.db.save_games_batch, games, commit=True)
            
            if self.checkpoint:
                if success_ids:
                    self.checkpoint.mark_appids_completed(success_ids)
                if fail_ids:
                    for fid in fail_ids:
                        self.checkpoint.mark_appid_failed(fid)
                # 每次批量操作后保存 Checkpoint 文件
                self.checkpoint.save()

        self._commit_batch = _commit_batch_impl

        # --- 启动所有任务 ---
        
        with self.ui.create_progress() as progress:
            page_task = progress.add_task("[cyan]扫描页面...", total=total_pages)
            game_task = progress.add_task("[green]处理数据...", total=0)
            
            # 启动 Result Committer
            committer_task = asyncio.create_task(committer())
            
            # 启动 Workers
            workers = [
                asyncio.create_task(worker()) 
                for _ in range(self.config.scraper.max_workers)
            ]
            
            # 启动 Producer
            # 我们直接 await producer，因为它是主要的驱动力
            # 当 producer 完成后，意味着只有队列里的剩余任务了
            await producer()
            
            # 等待所有任务处理完毕
            await id_queue.join()
            
            # 发送 Cancel 信号给 Workers (通过取消任务)
            for w in workers:
                w.cancel()
            
            # 等待 Result Queue 处理完毕
            await result_queue.join()
            
            # 停止 Committer
            committer_task.cancel()
            try:
                await committer_task
            except asyncio.CancelledError:
                pass

        # 清理
        # 清理
        await self.client.close()
        self.db.commit()
        
        # 输出跳过的重复 AppID 汇总
        if skipped_appids:
            self.ui.print_warning(
                f"跳过 {len(skipped_appids)} 个重复 AppID (本轮内重复): {skipped_appids}"
            )
        
        return all_app_ids

    def get_app_ids(self) -> list[int]:
        """从数据库获取所有 app_id。"""
        return self.db.get_all_app_ids()
