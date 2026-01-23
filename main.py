"""
Steam 爬虫统一入口。

提供命令行接口来运行爬虫，支持并发抓取和数据库存储。
"""

from __future__ import annotations

import argparse
import shutil
import sys
import pyfiglet
from pathlib import Path


# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from src.config import Config
from src.database import DatabaseManager
from src.scrapers.game_scraper import GameScraper
from src.scrapers.review_scraper import ReviewScraper
from src.utils.checkpoint import Checkpoint
from src.utils.failure_manager import FailureManager
from src.utils.ui import UIManager


def main() -> None:
    """主入口函数。"""
    parser = argparse.ArgumentParser(
        description="Steam 游戏数据爬虫",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 基础用法
  python main.py games              # 爬取所有游戏基础信息
  python main.py reviews            # 爬取已有游戏的评价历史

  # 高级用法
  python main.py all                # 完整流程：爬取游戏 -> 爬取评价 -> 导出
  python main.py games --pages 10   # 仅测试爬取前 10 页
  python main.py all --resume       # 从上次中断处继续

  # 数据管理
  python main.py export             # 导出数据库到 Excel
  python main.py clean              # 清理临时文件和缓存
  python main.py reset              # 重置项目（删除所有数据，慎用！）
  python main.py retry              # 重试所有失败的任务

输出:
  data/steam_data.db    (SQLite 数据库，核心存储)
  data/steam_data.xlsx  (Excel 导出文件，包含 Games 和 Reviews 两个工作表)
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # 启动界面命令
    subparsers.add_parser(
        "start",
        help=argparse.SUPPRESS,  # 在帮助中隐藏
    )

    # 游戏信息爬取命令
    games_parser = subparsers.add_parser(
        "games",
        help="爬取游戏基础信息",
        description="从 Steam 商店爬取游戏基础信息（并发）",
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
        description="根据已爬取的最新的游戏列表，并发爬取评价历史",
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
        help="导出数据到 Excel",
        description="将数据库中的数据导出为 Excel 文件",
    )
    export_parser.add_argument(
        "--output",
        type=str,
        default="data/steam_data.xlsx",
        help="输出文件名（默认：data/steam_data.xlsx）",
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

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return

    config = Config.load()
    failure_manager = FailureManager(config)
    ui = UIManager()

    # 显示 Banner
    ui.print_panel(
        "[bold white]Simple Steam Scraper[/bold white]\n"
        "[dim]github.com/SeraphinaGlacia/simple-steam-scraper[/dim]",
        style="header",
    )

    if args.command == "games":
        run_games_scraper(config, args, failure_manager, ui)
    elif args.command == "start":
        run_start(ui)
    elif args.command == "reviews":
        run_reviews_scraper(config, args, failure_manager, ui)
    elif args.command == "all":
        run_all(config, args, failure_manager, ui)
    elif args.command == "export":
        run_export(config, args, ui)
    elif args.command == "clean":
        run_clean(failure_manager, ui)
    elif args.command == "reset":
        run_reset(config, failure_manager, ui)
    elif args.command == "retry":
        run_retry(config, args, failure_manager, ui)


def run_reset(config: Config, failure_manager: FailureManager, ui: UIManager) -> None:
    """重置项目，清除所有数据。"""
    ui.print_panel(
        "[bold red]⚠️  危险操作警告 / DANGER ZONE[/bold red]\n\n"
        "此操作将 [bold red]永久删除[/bold red] `data/` 目录下所有文件：\n"
        " - 数据库文件 (steam_data.db)\n"
        " - 导出文件 (Excel)\n"
        " - 失败日志 (failures.json)\n"
        " - 断点文件 (.checkpoint.json)\n\n"
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
    data_dir = Path(config.output.data_dir)
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
    run_clean(failure_manager, ui)

    ui.print_success("✨ 项目已重置 / Project Reset Completed")


def run_start(ui: UIManager) -> None:
    """显示启动界面。"""
    # 1. Big ASCII Art
    try:
        title = pyfiglet.figlet_format("Steam Scraper", font="slant")
        ui.print(title, style="bold cyan")
    except Exception:
        # Fallback if font missing or error
        ui.print_panel("[bold cyan]Steam Scraper[/bold cyan]", style="cyan")

    # 2. Welcome Panel
    ui.print_panel(
        "[bold white]快速开始指南 / Getting Started:[/bold white]\n"
        "1. 运行 [cyan]python main.py --help[/cyan] 查看所有可用命令。\n"
        "2. 运行 [cyan]python main.py games[/cyan] 抓取游戏基础数据。\n"
        "3. 运行 [cyan]python main.py reviews[/cyan] 抓取评价历史数据。\n"
        "4. 运行 [cyan]python main.py export[/cyan] 导出最终 Excel 报表。\n\n"
        "[dim]项目地址: github.com/SeraphinaGlacia/simple-steam-scraper[/dim]",
        title="欢迎使用 Simple Steam Scraper",
        style="blue",
    )


def run_clean(failure_manager: FailureManager | None = None, ui: Optional[UIManager] = None) -> None:
    """清理缓存和临时文件。"""
    if ui is None:
        ui = UIManager()
        
    project_root = Path(__file__).parent
    cleaned = 0

    # ... (原有清理逻辑保持不变，但使用 ui.print) -> 这里为了简洁，直接全量替换函数体
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
    checkpoint_files = [
        project_root / ".checkpoint.json",
        project_root / "data" / ".checkpoint.json",
    ]
    for cp in checkpoint_files:
        if cp.exists():
            cp.unlink()
            ui.print(f"已删除: [dim]{cp}[/dim]")
            cleaned += 1

    # 清除失败日志
    if failure_manager:
        failure_manager.clear()
        cleaned += 1

    if cleaned:
        ui.print_success(f"清理完成，共删除 {cleaned} 个文件/目录。")
    else:
        ui.print_info("没有需要清理的文件。")


def run_games_scraper(
    config: Config, args: argparse.Namespace, failure_manager: FailureManager, ui: UIManager
) -> None:
    """运行游戏信息爬虫。"""
    checkpoint = Checkpoint(config=config) if args.resume else None

    scraper = GameScraper(
        config=config, 
        checkpoint=checkpoint, 
        failure_manager=failure_manager,
        ui_manager=ui
    )
    scraper.run(max_pages=args.pages)

    ui.print_success(f"游戏信息爬取完成！数据已存入 [bold]{config.output.db_path}[/bold]")


def run_reviews_scraper(
    config: Config, args: argparse.Namespace, failure_manager: FailureManager, ui: UIManager
) -> None:
    """运行评价历史爬虫。"""
    checkpoint = Checkpoint(config=config) if args.resume else None
    
    scraper = ReviewScraper(
        config=config, 
        checkpoint=checkpoint, 
        failure_manager=failure_manager,
        ui_manager=ui
    )

    if args.input:
        scraper.scrape_from_file(args.input)
    else:
        db = DatabaseManager(config.output.db_path)
        app_ids = db.get_all_app_ids()
        db.close()
        
        if not app_ids:
            ui.print_warning("数据库中没有游戏数据，请先运行 'python main.py games'")
            return
            
        scraper.scrape_from_list(app_ids)

    ui.print_success(f"评价数据爬取完成！数据已存入 [bold]{config.output.db_path}[/bold]")


def run_all(
    config: Config, args: argparse.Namespace, failure_manager: FailureManager, ui: UIManager
) -> None:
    """运行完整爬取流程。"""
    checkpoint = Checkpoint(config=config) if args.resume else None
    
    ui.print_panel("Step 1/3: 爬取游戏基础信息", style="blue")
    game_scraper = GameScraper(
        config=config, 
        checkpoint=checkpoint, 
        failure_manager=failure_manager,
        ui_manager=ui
    )
    game_scraper.run(max_pages=args.pages)

    ui.print("\n")
    ui.print_panel("Step 2/3: 爬取评价历史信息", style="blue")
    app_ids = game_scraper.get_app_ids()
    
    review_scraper = ReviewScraper(
        config=config, 
        checkpoint=checkpoint, 
        failure_manager=failure_manager,
        ui_manager=ui
    )
    review_scraper.scrape_from_list(app_ids)

    ui.print("\n")
    ui.print_panel("Step 3/3: 导出数据", style="blue")
    run_export(config, argparse.Namespace(output="data/steam_data.xlsx"), ui)

    ui.print_success("🎉 全部完成！Enjoy your data.")


def run_export(config: Config, args: argparse.Namespace, ui: UIManager) -> None:
    """导出数据。"""
    ui.print_info(f"正在导出数据到 [bold]{args.output}[/bold]...")
    
    if not Path(config.output.db_path).exists():
        ui.print_error(f"数据库文件不存在: {config.output.db_path}\n请先运行 'python main.py games' 等相关命令抓取数据。")
        return

    db = DatabaseManager(config.output.db_path)
    try:
        with ui.create_progress() as progress:
            task = progress.add_task("导出中...", total=100) # 假进度条，因为导出是阻塞的
            progress.update(task, advance=50)
            db.export_to_excel(args.output)
            progress.update(task, completed=100)
            
        ui.print_success("导出成功！")
    except Exception as e:
        ui.print_error(f"导出失败: {e}")
    finally:
        db.close()
        
def run_retry(
    config: Config, args: argparse.Namespace, failure_manager: FailureManager, ui: UIManager
) -> None:
    """运行重试逻辑。"""
    ui.print_info("开始检查失败项目...")

    failures = failure_manager.get_failures()
    if not failures:
        ui.print_success("没有找到失败记录，Perfect!")
        return

    # 创建表格展示失败项目
    table = ui.create_table(title="失败任务清单")
    table.add_column("Type", style="cyan")
    table.add_column("ID", style="magenta")
    table.add_column("Reason", style="red")
    
    for f in failures:
         table.add_row(f["type"], str(f["id"]), f["reason"][:50]) # 截断原因
         
    ui.console.print(table)
    
    if not ui.confirm("是否立即重试这些项目？", default=True):
         ui.print("操作已取消。")
         return

    game_scraper = GameScraper(config=config, failure_manager=failure_manager, ui_manager=ui)
    review_scraper = ReviewScraper(config=config, failure_manager=failure_manager, ui_manager=ui)

    retry_count = 0
    success_count = 0

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
                    info = game_scraper.process_game(item_id)
                    if info:
                        is_success = True
                elif item_type == "review":
                    reviews = review_scraper.scrape_reviews(item_id)
                    if reviews:
                        is_success = True
            except Exception:
                pass
            
            if is_success:
                failure_manager.remove_failure(item_type, item_id)
                success_count += 1
                
            progress.update(task, advance=1)

    ui.print_panel(
        f"重试结束。\n"
        f"尝试: {retry_count}\n"
        f"成功: [green]{success_count}[/green]\n"
        f"剩余: [red]{retry_count - success_count}[/red]",
        title="重试报告"
    )



if __name__ == "__main__":
    main()
