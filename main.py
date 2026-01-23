"""
Steam 爬虫统一入口。

提供命令行接口来运行爬虫，支持并发抓取和数据库存储。
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from src.config import Config
from src.database import DatabaseManager
from src.scrapers.game_scraper import GameScraper
from src.scrapers.review_scraper import ReviewScraper
from src.utils.checkpoint import Checkpoint
from src.utils.failure_manager import FailureManager


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
  python main.py export             # 重新导出数据库到 Excel
  python main.py clean              # 清理临时文件和缓存
  python main.py reset              # 重置项目（删除所有数据，慎用！）
  python main.py retry              # 重试所有失败的任务

输出:
  data/steam_data.db    (SQLite 数据库，核心存储)
  data/steam_data.xlsx  (Excel 导出文件，包含 Games 和 Reviews 两个工作表)
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="可用命令")

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

    if args.command == "games":
        run_games_scraper(config, args, failure_manager)
    elif args.command == "reviews":
        run_reviews_scraper(config, args, failure_manager)
    elif args.command == "all":
        run_all(config, args, failure_manager)
    elif args.command == "export":
        run_export(config, args)
    elif args.command == "clean":
        run_clean(failure_manager)
    elif args.command == "reset":
        run_reset(config, failure_manager)
    elif args.command == "retry":
        run_retry(config, args, failure_manager)

def run_reset(config: Config, failure_manager: FailureManager) -> None:
    """重置项目，清除所有数据。"""
    print("⚠️  危险操作：这将删除 data/ 目录下所有文件（数据库、Excel、日志等）以及所有临时文件。")
    print("⚠️  此操作不可恢复！")
    
    confirm1 = input("确认要重置吗？(y/N): ").strip().lower()
    if confirm1 != "y":
        print("操作已取消。")
        return

    confirm2 = input("再次确认：你真的要删除所有数据吗？(y/N): ").strip().lower()
    if confirm2 != "y":
        print("操作已取消。")
        return

    print("\n开始重置...")
    
    # 1. 清理 data 目录
    data_dir = Path(config.output.data_dir)
    if data_dir.exists():
        for item in data_dir.glob("*"):
            if item.name == ".gitkeep": # 保留 gitkeep
                continue
            try:
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)
                print(f"已删除: {item}")
            except Exception as e:
                print(f"删除失败 {item}: {e}")
    else:
        print(f"目录不存在: {data_dir}")

    # 2. 运行常规清理
    run_clean(failure_manager)

    print("\n✨ 项目已重置。")


def run_clean(failure_manager: FailureManager | None = None) -> None:
    """清理缓存和临时文件。"""
    project_root = Path(__file__).parent
    cleaned = 0

    # 删除 __pycache__ 目录
    for pycache in project_root.rglob("__pycache__"):
        if pycache.is_dir():
            shutil.rmtree(pycache)
            print(f"已删除: {pycache}")
            cleaned += 1

    # 删除 .pyc 文件
    for pyc in project_root.rglob("*.pyc"):
        pyc.unlink()
        print(f"已删除: {pyc}")
        cleaned += 1

    # 删除断点文件
    checkpoint_files = [
        project_root / ".checkpoint.json",
        project_root / "data" / ".checkpoint.json",
    ]
    for cp in checkpoint_files:
        if cp.exists():
            cp.unlink()
            print(f"已删除: {cp}")
            cleaned += 1

    # 清除失败日志
    if failure_manager:
        failure_manager.clear()
        cleaned += 1

    if cleaned:
        print(f"\n清理完成，共删除 {cleaned} 个文件/目录。")
    else:
        print("没有需要清理的文件。")


def run_games_scraper(
    config: Config, args: argparse.Namespace, failure_manager: FailureManager
) -> None:
    """运行游戏信息爬虫。"""
    checkpoint = Checkpoint(config=config) if args.resume else None

    scraper = GameScraper(
        config=config, checkpoint=checkpoint, failure_manager=failure_manager
    )
    scraper.run(max_pages=args.pages)

    print(f"游戏信息爬取完成！数据已存入 {config.output.db_path}")


def run_reviews_scraper(
    config: Config, args: argparse.Namespace, failure_manager: FailureManager
) -> None:
    """运行评价历史爬虫。"""
    checkpoint = Checkpoint(config=config) if args.resume else None
    
    scraper = ReviewScraper(
        config=config, checkpoint=checkpoint, failure_manager=failure_manager
    )

    if args.input:
        # 从文件读取
        scraper.scrape_from_file(args.input)
    else:
        # 从数据库读取所有 AppID
        db = DatabaseManager(config.output.db_path)
        app_ids = db.get_all_app_ids()
        db.close()
        
        if not app_ids:
            print("数据库中没有游戏数据，请先运行 'python main.py games'")
            return
            
        scraper.scrape_from_list(app_ids)

    print(f"评价数据爬取完成！数据已存入 {config.output.db_path}")


def run_all(
    config: Config, args: argparse.Namespace, failure_manager: FailureManager
) -> None:
    """运行完整爬取流程。"""
    checkpoint = Checkpoint(config=config) if args.resume else None
    
    # 第一步：爬取游戏信息
    print("=== 第一步：爬取游戏基础信息 ===")
    game_scraper = GameScraper(
        config=config, checkpoint=checkpoint, failure_manager=failure_manager
    )
    game_scraper.run(max_pages=args.pages)

    # 第二步：爬取评价信息
    print("\n=== 第二步：爬取评价历史信息 ===")
    # 获取刚刚爬取到的所有 AppID (从数据库)
    app_ids = game_scraper.get_app_ids()
    
    review_scraper = ReviewScraper(
        config=config, checkpoint=checkpoint, failure_manager=failure_manager
    )
    review_scraper.scrape_from_list(app_ids)

    # 第三步：导出
    print("\n=== 第三步：导出数据 ===")
    run_export(config, argparse.Namespace(output="data/steam_data.xlsx"))

    print(f"\n全部完成！数据已导出至 data/steam_data.xlsx")


def run_export(config: Config, args: argparse.Namespace) -> None:
    """导出数据。"""
    print(f"正在导出数据到 {args.output}...")
    db = DatabaseManager(config.output.db_path)
    try:
        db.export_to_excel(args.output)
        print("导出成功！")
    except Exception as e:
        print(f"导出失败: {e}")
    finally:
        db.close()


def run_retry(
    config: Config, args: argparse.Namespace, failure_manager: FailureManager
) -> None:
    """运行重试逻辑。"""
    print("开始重试失败项目...")

    failures = failure_manager.get_failures()
    if not failures:
        print("没有找到失败记录。")
        return

    game_scraper = GameScraper(config=config, failure_manager=failure_manager)
    review_scraper = ReviewScraper(config=config, failure_manager=failure_manager)

    retry_count = 0
    success_count = 0

    for failure in failures:
        item_type = failure["type"]
        item_id = int(failure["id"])

        # 根据参数过滤类型
        if args.type != "all" and item_type != args.type:
            continue

        print(f"正在重试: [{item_type}] ID={item_id}")
        retry_count += 1

        try:
            if item_type == "game":
                info = game_scraper.process_game(item_id)
                if info:
                    print(f"重试成功: {info.name}")
                    failure_manager.remove_failure(item_type, item_id)
                    success_count += 1
                else:
                    print("重试失败: 仍无法获取数据")

            elif item_type == "review":
                reviews = review_scraper.scrape_reviews(item_id)
                if reviews:
                    print(f"重试成功: 获取到 {len(reviews)} 条评价")
                    failure_manager.remove_failure(item_type, item_id)
                    success_count += 1
                else:
                    print("重试失败: 仍无评价数据")

        except Exception as e:
            print(f"重试异常: {e}")

    print(f"\n重试结束。共尝试 {retry_count} 个项目，成功恢复 {success_count} 个。")


if __name__ == "__main__":
    main()
