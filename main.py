"""
Steam 爬虫统一入口。

提供命令行接口来运行爬虫。
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from src.config import Config
from src.exporters.excel import ExcelExporter, save_appids_to_file
from src.scrapers.game_scraper import GameScraper
from src.scrapers.review_scraper import ReviewScraper
from src.utils.checkpoint import Checkpoint


def main() -> None:
    """主入口函数。"""
    parser = argparse.ArgumentParser(
        description="Steam 游戏数据爬虫",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py games              爬取全部游戏基础信息
  python main.py games --pages 10   只爬取前 10 页
  python main.py games --resume     从断点恢复爬取
  python main.py reviews            爬取评价历史
  python main.py all                完整流程（游戏+评价）
  python main.py all --resume       完整流程，从断点恢复
  python main.py clean              清理缓存和临时文件

输出目录: data/
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # 游戏信息爬取命令
    games_parser = subparsers.add_parser(
        "games",
        help="爬取游戏基础信息",
        description="从 Steam 商店爬取游戏基础信息（名称、价格、开发商等）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py games              爬取全部页面
  python main.py games --pages 50   只爬取前 50 页
  python main.py games --resume     从断点恢复
        """,
    )
    games_parser.add_argument(
        "--pages",
        type=int,
        default=None,
        metavar="N",
        help="爬取页数，不指定则爬取全部（每页约 25 款游戏）",
    )
    games_parser.add_argument(
        "--output",
        type=str,
        default=None,
        metavar="FILE",
        help="输出文件名（默认：steam_games_时间戳.xlsx）",
    )
    games_parser.add_argument(
        "--resume",
        action="store_true",
        help="从断点恢复爬取，适用于中途中断的情况",
    )

    # 评价信息爬取命令
    reviews_parser = subparsers.add_parser(
        "reviews",
        help="爬取评价历史信息",
        description="根据 app_id 列表爬取每个游戏的评价历史曲线",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py reviews                          使用默认输入文件
  python main.py reviews --input my_appids.txt    使用自定义文件
  python main.py reviews --resume                 从断点恢复
        """,
    )
    reviews_parser.add_argument(
        "--input",
        type=str,
        default="data/steam_appids.txt",
        metavar="FILE",
        help="app_id 列表文件（默认：data/steam_appids.txt）",
    )
    reviews_parser.add_argument(
        "--resume",
        action="store_true",
        help="从断点恢复爬取，跳过已完成的游戏",
    )

    # 完整流程命令
    all_parser = subparsers.add_parser(
        "all",
        help="运行完整爬取流程（游戏信息 + 评价历史）",
        description="先爬取游戏基础信息，再自动爬取所有游戏的评价历史",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py all              爬取全部游戏及评价
  python main.py all --pages 100  只爬取前 100 页的游戏及评价
  python main.py all --resume     从断点恢复
        """,
    )
    all_parser.add_argument(
        "--pages",
        type=int,
        default=None,
        metavar="N",
        help="爬取页数，不指定则爬取全部（每页约 25 款游戏）",
    )
    all_parser.add_argument(
        "--resume",
        action="store_true",
        help="从断点恢复爬取，适用于中途中断的情况",
    )

    # 清理命令
    subparsers.add_parser(
        "clean",
        help="清理缓存和临时文件",
        description="删除 __pycache__、.pyc 文件和断点文件",
    )

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return

    config = Config.load()

    if args.command == "games":
        run_games_scraper(config, args)
    elif args.command == "reviews":
        run_reviews_scraper(config, args)
    elif args.command == "all":
        run_all(config, args)
    elif args.command == "clean":
        run_clean()


def run_clean() -> None:
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

    if cleaned:
        print(f"\n清理完成，共删除 {cleaned} 个文件/目录。")
    else:
        print("没有需要清理的文件。")


def run_games_scraper(config: Config, args: argparse.Namespace) -> None:
    """运行游戏信息爬虫。

    Args:
        config: 配置对象。
        args: 命令行参数。
    """
    checkpoint = Checkpoint(config=config) if args.resume else None

    scraper = GameScraper(config=config, checkpoint=checkpoint)
    games = scraper.run(max_pages=args.pages)

    exporter = ExcelExporter(config=config)
    exporter.export_games(games, filename=args.output)

    # 保存 app_id 列表
    save_appids_to_file(scraper.get_app_ids())

    print(f"完成！共爬取 {len(games)} 款游戏。")


def run_reviews_scraper(config: Config, args: argparse.Namespace) -> None:
    """运行评价历史爬虫。

    Args:
        config: 配置对象。
        args: 命令行参数。
    """
    checkpoint = Checkpoint(config=config) if args.resume else None
    exporter = ExcelExporter(config=config)

    scraper = ReviewScraper(config=config, checkpoint=checkpoint)

    def on_complete(app_id: int, reviews: list) -> None:
        """每个游戏完成后的回调。"""
        if reviews:
            exporter.export_reviews(app_id, reviews)

    scraper.scrape_from_file(args.input, on_complete=on_complete)

    print("评价数据爬取完成！")


def run_all(config: Config, args: argparse.Namespace) -> None:
    """运行完整爬取流程。

    Args:
        config: 配置对象。
        args: 命令行参数。
    """
    checkpoint = Checkpoint(config=config) if args.resume else None
    exporter = ExcelExporter(config=config)

    # 第一步：爬取游戏信息
    print("=== 第一步：爬取游戏基础信息 ===")
    game_scraper = GameScraper(config=config, checkpoint=checkpoint)
    games = game_scraper.run(max_pages=args.pages)
    exporter.export_games(games)

    app_ids = game_scraper.get_app_ids()
    save_appids_to_file(app_ids)

    # 第二步：爬取评价信息
    print("\n=== 第二步：爬取评价历史信息 ===")
    review_scraper = ReviewScraper(config=config, checkpoint=checkpoint)

    def on_review_complete(app_id: int, reviews: list) -> None:
        """评价完成回调。"""
        if reviews:
            exporter.export_reviews(app_id, reviews)

    review_scraper.scrape_from_list(app_ids, on_complete=on_review_complete)

    print(f"\n完成！共爬取 {len(games)} 款游戏的信息和评价数据。")


if __name__ == "__main__":
    main()
