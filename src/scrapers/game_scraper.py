"""
游戏信息爬虫模块。

从 Steam 商店爬取游戏基础信息，支持异步并发爬取和数据库存储。
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any, Optional

from bs4 import BeautifulSoup

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
            soup = await asyncio.to_thread(BeautifulSoup, response.text, "html.parser")

            search_results = soup.find("div", {"class": "search_pagination_left"})
            if search_results:
                # 示例文本: "Showing 1 - 25 of 69792"
                # 使用正则提取所有数字，假设最后一个数字是总记录数
                import re
                numbers = re.findall(r"\d+", search_results.text.strip().replace(",", ""))
                if numbers:
                    total_results = int(numbers[-1])
                    return (total_results // 25) + 1  # Steam 每页显示 25 个游戏
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
            soup = await asyncio.to_thread(BeautifulSoup, response.text, "html.parser")

            games = soup.find_all("a", {"class": "search_result_row"})

            for game in games:
                # data-ds-appid 是 Steam 搜索结果页面中的自定义属性
                # 它存储了游戏的 AppID，用于后续获取详细信息
                # 注意：捆绑包/合集可能包含逗号分隔的多个 AppID（如 "123,456,789"）
                # 此时只取第一个 AppID
                app_id_str = game.get("data-ds-appid")
                if app_id_str:
                    # 处理逗号分隔的多 AppID 情况（捆绑包）
                    first_id = app_id_str.split(",")[0]
                    app_ids.append(int(first_id))

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
        """运行爬虫（异步并发模式）。

        使用 asyncio.Semaphore 控制并发数，避免同时发起过多请求导致被限流。
        相比 ThreadPoolExecutor，异步模式能更高效地利用系统资源。

        Args:
            max_pages: 可选的最大页数限制。

        Returns:
            list[int]: 所有处理过的 app_id。
        """
        total_pages = await self.get_total_pages()
        if max_pages:
            total_pages = min(total_pages, max_pages)

        print(
            f"开始爬取 {total_pages} 页，并发数: {self.config.scraper.max_workers}"
        )

        all_app_ids: list[int] = []
        skipped_appids: list[int] = []  # 收集跳过的重复 AppID
        seen_appids: set[int] = set()   # 追踪已见过的 AppID（用于本轮去重）
        
        # 使用信号量限制并发数，避免同时发起过多请求
        # 这是 asyncio 中控制并发度的标准方式
        semaphore = asyncio.Semaphore(self.config.scraper.max_workers)

        async def limited_process(app_id: int) -> tuple[int, Optional[GameInfo], bool]:
            """带并发限制的游戏处理函数。
            
            使用信号量确保同时进行的请求数不超过 max_workers。
            
            Args:
                app_id (int): Steam 游戏 ID。
                
            Returns:
                tuple[int, Optional[GameInfo], bool]: (app_id, 游戏详情或 None, 是否跳过重复)
            """
            async with semaphore:
                # 批量运行时 commit_db=False, save_to_db=False
                # 由 run 方法收集 GameInfo 后批量提交 DB 和更新断点
                # 确保高性能和数据一致性
                result, skipped = await self.process_game(app_id, commit_db=False, save_to_db=False)
                return app_id, result, skipped

        with self.ui.create_progress() as progress:
            # 采用双进度条设计：
            # 1. page_task: 显示页面扫描进度（快速）
            # 2. game_task: 显示游戏详情抓取进度（较慢，因为需要请求 API）
            # 这种设计让用户能同时看到宏观和微观进度
            page_task = progress.add_task("[cyan]扫描页面...", total=total_pages)
            # game_task 的 total 初始为 0，会在扫描过程中动态增加
            game_task = progress.add_task("[green]抓取详情...", total=0)

            for page in range(1, total_pages + 1):
                # 检查停止信号
                if self.stop_event and self.stop_event.is_set():
                    break

                if self.checkpoint and self.checkpoint.is_page_completed(page):
                    progress.update(page_task, advance=1)
                    continue

                # 爬取当前页面的游戏列表
                app_ids = await self.scrape_page_games(page)
                progress.update(page_task, advance=1)

                if not app_ids:
                    continue

                # 在创建任务前进行去重
                unique_app_ids = []
                for app_id in app_ids:
                    # 情况1：本轮内已出现过（动态 sort 重复）→ 汇报
                    if app_id in seen_appids:
                        skipped_appids.append(app_id)
                        continue
                    seen_appids.add(app_id)
                    # 情况2：断点中已完成 → 静默跳过，不汇报（这是 --resume 的预期行为）
                    if self.checkpoint and self.checkpoint.is_appid_completed(app_id):
                        continue
                    unique_app_ids.append(app_id)

                # 动态更新游戏任务总量，因为每页返回的游戏数不固定
                progress.update(
                    game_task, total=progress.tasks[game_task].total + len(unique_app_ids)
                )

                # 创建并发任务（只处理不重复的）
                tasks = [limited_process(app_id) for app_id in unique_app_ids]
                
                # 用于收集本页成功抓取的 GameInfo，以便在数据库提交后统一更新断点
                batch_games: list[GameInfo] = []
                pending_commit_appids: list[int] = []

                # 使用 asyncio.as_completed 实现实时进度更新
                for future in asyncio.as_completed(tasks):
                    try:
                        result = await future
                        app_id, game_info, skipped = result
                        all_app_ids.append(app_id)
                        
                        if skipped:
                            skipped_appids.append(app_id)
                        elif game_info:
                            # 收集成功抓取的 GameInfo 对象，用于批量插入
                            batch_games.append(game_info)
                            pending_commit_appids.append(app_id)
                        elif game_info is None and self.checkpoint:
                            # 如果返回 None 且不是因为已完成/跳过，则标记为失败
                            # 失败状态不需要等待数据库提交，因为没有数据入库
                            if not self.checkpoint.is_appid_completed(app_id):
                                self.checkpoint.mark_appid_failed(app_id)
                    except Exception as e:
                        self.ui.print_error(f"处理游戏异常: {e}")
                    finally:
                        progress.update(game_task, advance=1)

                # 批量插入本页游戏数据
                if batch_games:
                    await asyncio.to_thread(self.db.save_games_batch, batch_games, commit=True)

                # 关键修复：确保数据库提交成功后再更新断点
                if self.checkpoint:
                    if pending_commit_appids:
                        self.checkpoint.mark_appids_completed(pending_commit_appids)
                    self.checkpoint.mark_page_completed(page)

        # 输出跳过的重复 AppID 汇总
        if skipped_appids:
            self.ui.print_warning(
                f"跳过 {len(skipped_appids)} 个重复 AppID: {skipped_appids}"
            )

        # 关闭 HTTP 客户端释放资源
        await self.client.close()
        
        # 确保所有剩余数据已提交
        self.db.commit()

        # 最终不再返回 GameInfo 对象列表，而是 AppID 列表，因为数据已入库
        return all_app_ids

    def get_app_ids(self) -> list[int]:
        """从数据库获取所有 app_id。"""
        return self.db.get_all_app_ids()
