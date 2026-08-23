"""Steam 爬虫统一入口。

提供命令行接口来运行爬虫，支持异步并发抓取和数据库存储。
本模块是整个项目的 CLI 入口点，负责解析命令行参数并分发到对应的处理函数。
"""

from __future__ import annotations

import argparse
import asyncio
import shutil
import signal
import threading
import time
from collections.abc import Sequence
from datetime import timedelta
from pathlib import Path
from types import FrameType

import pyfiglet

from steam_scraper.config import Config
from steam_scraper.database import DatabaseManager
from steam_scraper.scrapers.game_scraper import GameScraper
from steam_scraper.scrapers.review_scraper import ReviewScraper
from steam_scraper.utils.checkpoint import Checkpoint
from steam_scraper.utils.failure_manager import FailureManager, FailureRecord
from steam_scraper.utils.ui import UIManager

_COMMAND = "uv run steam-scraper"


def build_parser() -> argparse.ArgumentParser:
    """构建 Steam Scraper 命令行解析器。

    Returns:
        配置完成、可独立用于帮助输出和参数解析的解析器。
    """
    parser = argparse.ArgumentParser(
        description="Steam 游戏数据爬虫 (AsyncIO 版)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""\
示例:
  # 基础用法
  {_COMMAND} games              # 爬取所有游戏基础信息
  {_COMMAND} reviews            # 爬取已有游戏的评价历史

  # 高级用法
  {_COMMAND} all                # 完整流程：爬取游戏 -> 爬取评价 -> 导出
  {_COMMAND} all --resume       # 从上次中断处继续
  {_COMMAND} games --pages 10   # 仅测试爬取前 10 页

  # 数据管理
  {_COMMAND} export             # 导出数据库到 Excel
  {_COMMAND} export --format csv # 导出数据库到 CSV (适合大数据量)
  {_COMMAND} clean              # 清理临时文件和缓存
  {_COMMAND} reset              # 重置项目（删除所有数据，慎用！）
  {_COMMAND} retry              # 重试所有失败的任务

断点恢复机制:
  不带 --resume: 清除断点，从头开始爬取
  带   --resume: 保留断点，跳过已完成/已失败的项目继续爬取
  失败的项目会被记录，可通过 retry 命令专门处理

输出:
  data/steam_data.db    (SQLite 数据库，核心存储)
  data/steam_data.xlsx  (Excel 导出文件，包含 Games 和 Reviews 两个工作表)
  data/steam_games.csv  (游戏信息 CSV；使用 --format csv 时生成)
  data/steam_reviews.csv (评价历史 CSV；使用 --format csv 时生成)
  data/steam_*.csv      (CSV 导出文件，UTF-8-SIG 编码)
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # 启动界面命令
    subparsers.add_parser(
        "start",
        help="显示启动页并验证运行环境",
    )

    # 游戏信息爬取命令
    games_parser = subparsers.add_parser(
        "games",
        help="爬取游戏基础信息",
        description="从 Steam 商店爬取游戏基础信息（异步并发）",
    )
    games_parser.add_argument(
        "--pages",
        type=int,
        default=None,
        metavar="N",
        help="爬取页数，不指定则爬取全部",
    )
    games_parser.add_argument(
        "--resume",
        action="store_true",
        help="从断点恢复爬取",
    )

    # 评价信息爬取命令
    reviews_parser = subparsers.add_parser(
        "reviews",
        help="爬取评价历史信息",
        description="根据已爬取的最新的游戏列表，异步并发爬取评价历史",
    )
    reviews_parser.add_argument(
        "--input",
        type=str,
        default=None,
        metavar="FILE",
        help="可选：指定 app_id 列表文件（如果不指定则从数据库读取）",
    )
    reviews_parser.add_argument(
        "--resume",
        action="store_true",
        help="从断点恢复爬取",
    )

    # 完整流程命令
    all_parser = subparsers.add_parser(
        "all",
        help="运行完整爬取流程",
        description="先爬取游戏基础信息，再自动爬取所有游戏的评价历史，最后导出",
    )
    all_parser.add_argument(
        "--pages",
        type=int,
        default=None,
        metavar="N",
        help="爬取页数限制",
    )
    all_parser.add_argument(
        "--resume",
        action="store_true",
        help="从断点恢复",
    )

    # 导出命令
    export_parser = subparsers.add_parser(
        "export",
        help="导出数据到 Excel 或 CSV",
        description="将数据库中的数据导出为 Excel 文件",
    )
    export_parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="输出文件名。默认值将根据 config.yaml 中的 data_dir 动态生成。",
    )
    export_parser.add_argument(
        "--format",
        choices=["excel", "csv"],
        default="excel",
        help="导出格式 (默认: excel)",
    )

    # 清理命令
    subparsers.add_parser(
        "clean",
        help="清理缓存和临时文件",
    )

    # 重置命令
    subparsers.add_parser(
        "reset",
        help="重置项目（删除所有生成的数据，慎用）",
    )

    # 重试命令
    retry_parser = subparsers.add_parser(
        "retry",
        help="重试失败的项目",
    )
    retry_parser.add_argument(
        "--type",
        choices=["game", "review", "all"],
        default="all",
        help="重试类型",
    )

    return parser


def _install_uvloop() -> None:
    """在当前平台可用时启用 uvloop。"""
    try:
        import uvloop
    except ImportError:
        return

    uvloop.install()


def main(argv: Sequence[str] | None = None) -> None:
    """解析参数并分发到对应命令。

    Args:
        argv: 待解析的参数；省略时读取当前进程命令行。
    """
    parser = build_parser()

    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return

    _install_uvloop()
    config = Config.load()
    failure_manager = FailureManager(config)
    ui = UIManager()

    # 显示 Banner
    ui.print_panel(
        "[bold white]Simple Steam Scraper (AsyncIO)[/bold white]\n"
        "[dim]github.com/SeraphinaGlacia/steam-scraper[/dim]",
        style="header",
    )

    stop_event = threading.Event()

    def signal_handler(signum: int, frame: FrameType | None) -> None:
        """处理信号（如 Ctrl+C）。

        通过设置 stop_event 标志来优雅地停止所有正在运行的爬虫线程/任务，
        而不是直接强制终止进程，这样可以确保数据完整性和断点保存。
        """
        print("\n")
        print("⚠️  接收到停止信号，正在停止... / Stopping...")
        # 设置事件标志通知所有工作线程/协程停止
        stop_event.set()

    signal.signal(signal.SIGINT, signal_handler)

    if args.command == "games":
        run_games_scraper(config, args, failure_manager, ui, stop_event)
    elif args.command == "start":
        run_start(ui)
    elif args.command == "reviews":
        run_reviews_scraper(config, args, failure_manager, ui, stop_event)
    elif args.command == "all":
        run_all(config, args, failure_manager, ui, stop_event)
    elif args.command == "export":
        run_export(config, args, ui)
    elif args.command == "clean":
        run_clean(config, failure_manager, ui)
    elif args.command == "reset":
        run_reset(config, failure_manager, ui)
    elif args.command == "retry":
        run_retry(config, args, failure_manager, ui)


def run_reset(config: Config, failure_manager: FailureManager, ui: UIManager) -> None:
    """重置项目，清除所有数据。"""
    output = config.output
    ui.print_panel(
        "[bold red]⚠️  危险操作警告 / DANGER ZONE[/bold red]\n\n"
        f"此操作将 [bold red]永久删除[/bold red] `{output.data_path}/` 目录下所有文件：\n"
        f" - 数据库文件 ({output.database_file})\n"
        " - 导出文件 (Excel/CSV)\n"
        f" - 失败日志 ({output.failure_log_file})\n"
        f" - 断点文件 ({output.checkpoint_file})\n\n"
        "此操作不可恢复！",
        title="重置项目 Reset Project",
        style="red",
    )

    if not ui.confirm("[bold red]确认要重置吗？[/bold red]"):
        ui.print("操作已取消。")
        return

    if not ui.confirm("[bold red]再次确认：真的要删除所有数据吗？[/bold red]"):
        ui.print("操作已取消。")
        return

    ui.print("\n[bold yellow]开始重置...[/bold yellow]")

    # 1. 清理 data 目录
    data_dir = output.data_path
    if data_dir.exists():
        for item in data_dir.glob("*"):
            if item.name == ".gitkeep":
                continue
            try:
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)
                ui.print(f"已删除: [dim]{item}[/dim]")
            except Exception as e:
                ui.print_error(f"删除失败 {item}: {e}")
    else:
        ui.print_warning(f"目录不存在: {data_dir}")

    # 2. 运行常规清理
    run_clean(config, failure_manager, ui)

    ui.print_success("✨ 项目已重置 / Project Reset Completed")


def run_start(ui: UIManager) -> None:
    """显示启动界面。"""
    # 1. Big ASCII Art
    try:
        title = pyfiglet.figlet_format("Steam Scraper", font="slant")
        ui.print(title, style="bold cyan")
    except Exception:
        ui.print_panel("[bold cyan]Steam Scraper[/bold cyan]", style="cyan")

    # 2. Welcome Panel
    ui.print_panel(
        "[bold white]快速开始指南 / Getting Started:[/bold white]\n"
        f"1. 运行 [cyan]{_COMMAND} --help[/cyan] 查看所有可用命令。\n"
        f"2. 运行 [cyan]{_COMMAND} games[/cyan] 抓取游戏基础数据。\n"
        f"3. 运行 [cyan]{_COMMAND} reviews[/cyan] 抓取评价历史数据。\n"
        f"4. 运行 [cyan]{_COMMAND} export[/cyan] 导出 Excel 或 CSV 报表。\n\n"
        "[dim]项目地址: github.com/SeraphinaGlacia/steam-scraper[/dim]",
        title="欢迎使用 Simple Steam Scraper",
        style="blue",
    )


def run_clean(config: Config, failure_manager: FailureManager, ui: UIManager) -> None:
    """清理运行目录中的缓存以及配置指定的状态文件。"""
    # 数据、断点和配置都以运行目录为边界；不能清理已安装包所在的 site-packages。
    project_root = Path.cwd()
    cleaned = 0

    # 删除 __pycache__ 目录
    for pycache in project_root.rglob("__pycache__"):
        if pycache.is_dir():
            shutil.rmtree(pycache)
            ui.print(f"已删除: [dim]{pycache}[/dim]")
            cleaned += 1

    # 删除 .pyc 文件
    for pyc in project_root.rglob("*.pyc"):
        pyc.unlink()
        ui.print(f"已删除: [dim]{pyc}[/dim]")
        cleaned += 1

    # 删除断点文件
    checkpoint_path = config.output.checkpoint_path
    if checkpoint_path.exists():
        checkpoint_path.unlink()
        ui.print(f"已删除: [dim]{checkpoint_path}[/dim]")
        cleaned += 1

    # 清除失败日志
    if failure_manager.path.exists():
        failure_manager.clear()
        cleaned += 1

    if cleaned:
        ui.print_success(f"清理完成，共删除 {cleaned} 个文件/目录。")
    else:
        ui.print_info("没有需要清理的文件。")


def _get_game_failures(
    failure_manager: FailureManager, checkpoint: Checkpoint
) -> list[FailureRecord]:
    """获取所有 games 类型的失败记录（合并两个来源）。

    Args:
        failure_manager: 失败记录管理器。
        checkpoint: 断点管理器。

    Returns:
        合并并去重后的失败记录列表。
    """
    failures = failure_manager.get_failures("game")
    existing_ids = {f["id"] for f in failures}

    for app_id in checkpoint.get_failed_appids("game"):
        if app_id not in existing_ids:
            failures.append(
                {
                    "type": "game",
                    "id": app_id,
                    "reason": "从断点记录恢复（无详细原因）",
                }
            )
            existing_ids.add(app_id)

    return failures


async def run_games_scraper_async(
    config: Config,
    args: argparse.Namespace,
    failure_manager: FailureManager,
    ui: UIManager,
    stop_event: threading.Event,
) -> None:
    """异步运行游戏信息爬虫逻辑。

    Args:
        config: 配置对象。
        args: 命令行参数。
        failure_manager: 失败管理器。
        ui: UI 管理器。
        stop_event: 停止事件标志。
    """
    checkpoint = Checkpoint(config=config)
    if not args.resume:
        checkpoint.clear_task("game")  # 只清除 games 状态

    scraper = GameScraper(
        config=config,
        checkpoint=checkpoint,
        failure_manager=failure_manager,
        ui_manager=ui,
        stop_event=stop_event,
    )

    start_time = time.time()
    try:
        await scraper.run(max_pages=args.pages)
    finally:
        checkpoint.save()

    elapsed = time.time() - start_time
    duration = str(timedelta(seconds=int(elapsed)))

    # 为路径添加前缀，确保终端输出中点击行为一致且美观
    db_path = str(config.output.db_path)
    if not db_path.startswith("./") and not db_path.startswith("/"):
        db_path = f"./{db_path}"

    ui.print_success(
        f"游戏信息爬取完成！数据已存入: [bold]{db_path}[/bold] (耗时: {duration})"
    )


def run_games_scraper(
    config: Config,
    args: argparse.Namespace,
    failure_manager: FailureManager,
    ui: UIManager,
    stop_event: threading.Event,
) -> None:
    """运行游戏信息爬虫（入口包装）。"""
    asyncio.run(run_games_scraper_async(config, args, failure_manager, ui, stop_event))


async def run_reviews_scraper_async(
    config: Config,
    args: argparse.Namespace,
    failure_manager: FailureManager,
    ui: UIManager,
    stop_event: threading.Event,
) -> None:
    """异步运行评价历史爬虫逻辑。

    Args:
        config: 配置对象。
        args: 命令行参数。
        failure_manager: 失败管理器。
        ui: UI 管理器。
        stop_event: 停止事件标志。
    """
    checkpoint = Checkpoint(config=config)

    # 确保在爬取评价前游戏数据完整，避免外键约束错误或数据缺失
    game_failures = _get_game_failures(failure_manager, checkpoint)
    if game_failures:
        ui.print_warning(
            f"检测到 {len(game_failures)} 个游戏爬取失败记录。\n"
            "这可能导致 reviews 爬取时缺少对应的游戏表数据。\n"
            f"建议先运行 [cyan]{_COMMAND} retry --type game[/cyan] 处理失败项目。"
        )
        if not ui.confirm("是否忽略警告，继续爬取 reviews？", default=False):
            ui.print("操作已取消。请先处理 games 失败记录。")
            return

    if not args.resume:
        checkpoint.clear_task("review")  # 只清除 reviews 状态

    scraper = ReviewScraper(
        config=config,
        checkpoint=checkpoint,
        failure_manager=failure_manager,
        ui_manager=ui,
        stop_event=stop_event,
    )

    start_time = time.time()
    try:
        if args.input:
            await scraper.scrape_from_file(args.input)
        else:
            db = DatabaseManager(config.output.db_path)
            app_ids = db.get_all_app_ids()
            db.close()

            if not app_ids:
                ui.print_warning(f"数据库中没有游戏数据，请先运行 '{_COMMAND} games'")
                return

            await scraper.scrape_from_list(app_ids)
    finally:
        checkpoint.save()

    elapsed = time.time() - start_time
    duration = str(timedelta(seconds=int(elapsed)))

    # 为路径添加前缀，确保终端输出中点击行为一致且美观
    db_path = str(config.output.db_path)
    if not db_path.startswith("./") and not db_path.startswith("/"):
        db_path = f"./{db_path}"

    ui.print_success(
        f"评价数据爬取完成！数据已存入: [bold]{db_path}[/bold] (耗时: {duration})"
    )


def run_reviews_scraper(
    config: Config,
    args: argparse.Namespace,
    failure_manager: FailureManager,
    ui: UIManager,
    stop_event: threading.Event,
) -> None:
    """运行评价历史爬虫（入口包装）。"""
    asyncio.run(
        run_reviews_scraper_async(config, args, failure_manager, ui, stop_event)
    )


async def run_all_async(
    config: Config,
    args: argparse.Namespace,
    failure_manager: FailureManager,
    ui: UIManager,
    stop_event: threading.Event,
) -> None:
    """异步运行完整爬取流程逻辑。

    Args:
        config: 配置对象。
        args: 命令行参数。
        failure_manager: 失败管理器。
        ui: UI 管理器。
        stop_event: 停止事件标志。
    """
    checkpoint = Checkpoint(config=config)
    if not args.resume:
        checkpoint.clear()

    start_time = time.time()
    try:
        ui.print_panel("Step 1/3: 爬取游戏基础信息", style="blue")
        game_scraper = GameScraper(
            config=config,
            checkpoint=checkpoint,
            failure_manager=failure_manager,
            ui_manager=ui,
            stop_event=stop_event,
        )
        await game_scraper.run(max_pages=args.pages)
        # 阶段性保存，防止Step 2崩溃导致Step 1进度丢失
        checkpoint.save()

        # 为路径添加前缀，确保终端输出中点击行为一致且美观
        db_path = str(config.output.db_path)
        if not db_path.startswith("./") and not db_path.startswith("/"):
            db_path = f"./{db_path}"
        ui.print_success(f"游戏信息爬取完成！数据已存入: [bold]{db_path}[/bold]")

        if stop_event.is_set():
            return

        # 检查 games 是否有失败记录
        game_failures = _get_game_failures(failure_manager, checkpoint)
        if game_failures:
            ui.print_warning(
                f"\n游戏爬取阶段有 {len(game_failures)} 个失败项目。\n"
                "继续爬取 reviews 可能导致数据不完整。"
            )
            if not ui.confirm(
                "是否继续爬取 reviews？（建议先处理失败项目）", default=True
            ):
                ui.print(
                    f"已停止。请使用 [cyan]{_COMMAND} retry --type game[/cyan] "
                    "处理失败项目后重试。"
                )
                return

        ui.print("\n")
        ui.print_panel("Step 2/3: 爬取评价历史信息", style="blue")
        app_ids = game_scraper.get_app_ids()

        review_scraper = ReviewScraper(
            config=config,
            checkpoint=checkpoint,
            failure_manager=failure_manager,
            ui_manager=ui,
            stop_event=stop_event,
        )
        await review_scraper.scrape_from_list(app_ids)
        checkpoint.save()

        # 为路径添加前缀，确保终端输出中点击行为一致且美观
        db_path = str(config.output.db_path)
        if not db_path.startswith("./") and not db_path.startswith("/"):
            db_path = f"./{db_path}"
        ui.print_success(f"评价数据爬取完成！数据已存入: [bold]{db_path}[/bold]")

        if stop_event.is_set():
            return

        ui.print("\n")
        ui.print_panel("Step 3/3: 导出数据", style="blue")

        # 同时导出 Excel 和 CSV 两种格式
        # 使用 None 作为 output，让 run_export 内部根据 config 动态生成默认路径
        await asyncio.to_thread(
            run_export, config, argparse.Namespace(output=None, format="excel"), ui
        )
        await asyncio.to_thread(
            run_export, config, argparse.Namespace(output=None, format="csv"), ui
        )

        elapsed = time.time() - start_time
        duration = str(timedelta(seconds=int(elapsed)))
        ui.print_success(f"🎉 全部完成！Enjoy your data. (总耗时: {duration})")
    finally:
        checkpoint.save()


def run_all(
    config: Config,
    args: argparse.Namespace,
    failure_manager: FailureManager,
    ui: UIManager,
    stop_event: threading.Event,
) -> None:
    """运行完整爬取流程（入口包装）。"""
    asyncio.run(run_all_async(config, args, failure_manager, ui, stop_event))


def run_export(config: Config, args: argparse.Namespace, ui: UIManager) -> None:
    """导出数据。"""
    ui.print_info(f"正在导出数据 ({args.format})...")

    if not config.output.db_path.exists():
        ui.print_error(
            f"数据库文件不存在: {config.output.db_path}\n"
            f"请先运行 '{_COMMAND} games' 等相关命令抓取数据。"
        )
        return

    db = DatabaseManager(config.output.db_path)
    try:
        with ui.create_progress() as progress:
            # 导出操作较快，使用模拟进度条提升用户体验
            task = progress.add_task("导出中...", total=100)
            progress.update(task, advance=50)

            if args.format == "csv":
                # CSV 模式下，args.output 被视为目录
                if args.output:
                    output_dir = Path(args.output)
                else:
                    # 默认使用 config 中的 data_dir
                    output_dir = config.output.data_path

                db.export_to_csv(output_dir)

                # 格式化路径显示
                path_str = str(output_dir)
                if not path_str.startswith("./") and not path_str.startswith("/"):
                    path_str = f"./{path_str}"

                ui.print_success(
                    f"导出成功！文件保存在: [bold]{path_str}/steam_games.csv[/bold] & [bold]{path_str}/steam_reviews.csv[/bold]"
                )
            else:
                # Excel 模式
                output_file = args.output or config.output.data_path / "steam_data.xlsx"

                db.export_to_excel(output_file)

                # 格式化路径显示
                path_str = str(output_file)
                if not path_str.startswith("./") and not path_str.startswith("/"):
                    path_str = f"./{path_str}"

                ui.print_success(f"导出成功！文件保存在: [bold]{path_str}[/bold]")

            progress.update(task, completed=100)

    except Exception as e:
        ui.print_error(f"导出失败: {e}")
    finally:
        db.close()


async def run_retry_async(
    config: Config,
    args: argparse.Namespace,
    failure_manager: FailureManager,
    ui: UIManager,
) -> None:
    """异步运行重试逻辑。

    Args:
        config: 配置对象。
        args: 命令行参数。
        failure_manager: 失败管理器。
        ui: UI 管理器。
    """
    ui.print_info("开始检查失败项目...")

    # 1. 从 FailureManager 获取失败记录
    failures = failure_manager.get_failures()

    # 2. 从 Checkpoint 获取 failed_appids（合并到 failures 列表）
    checkpoint = Checkpoint(config=config)

    # 2.1 Games 失败记录
    existing_ids = {(f["type"], f["id"]) for f in failures}
    for app_id in checkpoint.get_failed_appids("game"):
        if ("game", app_id) not in existing_ids:
            failures.append(
                {
                    "type": "game",
                    "id": app_id,
                    "reason": "从断点记录恢复（无详细原因）",
                }
            )
            existing_ids.add(("game", app_id))

    # 2.2 Reviews 失败记录
    for app_id in checkpoint.get_failed_appids("review"):
        if ("review", app_id) not in existing_ids:
            failures.append(
                {
                    "type": "review",
                    "id": app_id,
                    "reason": "从断点记录恢复（无详细原因）",
                }
            )
            existing_ids.add(("review", app_id))

    if not failures:
        ui.print_success("没有找到失败记录，Perfect!")
        return

    # 创建表格展示失败项目
    table = ui.create_table(title="失败任务清单")
    table.add_column("Type", style="cyan")
    table.add_column("ID", style="magenta")
    table.add_column("Reason", style="red")

    for f in failures:
        table.add_row(f["type"], str(f["id"]), f["reason"][:50])

    ui.console.print(table)

    if not ui.confirm("是否立即重试这些项目？", default=True):
        ui.print("操作已取消。")
        return

    # 使用同一个 checkpoint 实例，确保 retry 成功后状态被正确更新
    game_scraper = GameScraper(
        config=config,
        checkpoint=checkpoint,
        failure_manager=failure_manager,
        ui_manager=ui,
    )
    review_scraper = ReviewScraper(
        config=config,
        checkpoint=checkpoint,
        failure_manager=failure_manager,
        ui_manager=ui,
    )

    # 先处理 games，再处理 reviews
    failures.sort(key=lambda f: 0 if f["type"] == "game" else 1)

    retry_count = 0
    success_count = 0

    try:
        with ui.create_progress() as progress:
            task = progress.add_task("重试中...", total=len(failures))

            for failure in failures:
                item_type = failure["type"]
                item_id = int(failure["id"])

                if args.type != "all" and item_type != args.type:
                    progress.update(task, advance=1)
                    continue

                retry_count += 1
                is_success = False

                try:
                    if item_type == "game":
                        info, _ = await game_scraper.process_game(item_id, force=True)
                        if info:
                            is_success = True
                    elif item_type == "review":
                        reviews, _ = await review_scraper.scrape_reviews(
                            item_id, force=True
                        )
                        if reviews:
                            is_success = True
                except Exception:
                    pass

                if is_success:
                    failure_manager.remove_failure(item_type, item_id)
                    success_count += 1

                progress.update(task, advance=1)
    finally:
        checkpoint.save()

    # 最后关闭客户端连接
    await game_scraper.client.close()
    await review_scraper.client.close()

    ui.print_panel(
        f"重试结束。\n"
        f"尝试: {retry_count}\n"
        f"成功: [green]{success_count}[/green]\n"
        f"剩余: [red]{retry_count - success_count}[/red]",
        title="重试报告",
    )


def run_retry(
    config: Config,
    args: argparse.Namespace,
    failure_manager: FailureManager,
    ui: UIManager,
) -> None:
    """运行重试逻辑（入口包装）。"""
    asyncio.run(run_retry_async(config, args, failure_manager, ui))


if __name__ == "__main__":
    main()
