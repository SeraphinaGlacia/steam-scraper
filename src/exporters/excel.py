"""
Excel 导出模块。

将爬取的数据导出为 Excel 文件。
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import openpyxl
import pandas as pd

from src.config import Config, get_config
from src.models import GameInfo, ReviewSnapshot


class ExcelExporter:
    """Excel 导出器。

    将游戏信息和评价数据导出为 Excel 文件。

    Attributes:
        config: 配置对象。
        output_dir: 输出目录。
    """

    def __init__(
        self,
        output_dir: Optional[str | Path] = None,
        config: Optional[Config] = None,
    ):
        """初始化导出器。

        Args:
            output_dir: 可选的输出目录。
            config: 可选的配置对象。
        """
        self.config = config or get_config()

        if output_dir:
            self.output_dir = Path(output_dir)
        else:
            self.output_dir = Path(self.config.output.data_dir)

        self.output_dir.mkdir(parents=True, exist_ok=True)

    def export_games(
        self,
        games: list[GameInfo],
        filename: Optional[str] = None,
    ) -> Path:
        """导出游戏信息到 Excel 文件。

        Args:
            games: 游戏信息列表。
            filename: 可选的文件名。

        Returns:
            Path: 导出文件的路径。
        """
        if not filename:
            filename = f'steam_games_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'

        # 转换为字典列表
        games_data = [game.to_dict() for game in games]

        df = pd.DataFrame(games_data)

        # 确保列顺序
        desired_columns = [
            "id",
            "name",
            "release_date",
            "price",
            "developers",
            "publishers",
            "genres",
            "description",
        ]
        existing_columns = [col for col in desired_columns if col in df.columns]
        df = df[existing_columns]

        file_path = self.output_dir / filename
        df.to_excel(file_path, index=False)
        print(f"游戏数据已保存到 {file_path}")

        return file_path

    def export_games_legacy(
        self,
        games_data: list[dict],
        filename: Optional[str] = None,
    ) -> Path:
        """导出游戏信息（兼容原有数据格式）。

        Args:
            games_data: 游戏信息字典列表（原有格式）。
            filename: 可选的文件名。

        Returns:
            Path: 导出文件的路径。
        """
        if not filename:
            filename = f'steam_games_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'

        df = pd.DataFrame(games_data)

        desired_columns = [
            "id",
            "name",
            "release_date",
            "price",
            "developers",
            "publishers",
            "genres",
            "description",
        ]
        existing_columns = [col for col in desired_columns if col in df.columns]
        df = df[existing_columns]

        file_path = self.output_dir / filename
        df.to_excel(file_path, index=False)
        print(f"游戏数据已保存到 {file_path}")

        return file_path

    def export_reviews(
        self,
        app_id: int,
        reviews: list[ReviewSnapshot],
        output_subdir: str = "steam_recommendations_data",
    ) -> Path:
        """导出单个游戏的评价数据到 Excel 文件。

        Args:
            app_id: Steam 游戏 ID。
            reviews: 评价快照列表。
            output_subdir: 输出子目录名。

        Returns:
            Path: 导出文件的路径。
        """
        # 创建子目录
        subdir = self.output_dir / output_subdir
        subdir.mkdir(parents=True, exist_ok=True)

        # 创建工作簿
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = f"AppID_{app_id}"

        # 写表头
        ws.append(["id", "date", "recommendations_up", "recommendations_down"])

        # 写数据
        for review in reviews:
            ws.append(
                [
                    review.app_id,
                    review.date.strftime("%Y-%m-%d"),
                    review.recommendations_up,
                    review.recommendations_down,
                ]
            )

        file_path = subdir / f"steam_recommendations_{app_id}.xlsx"
        wb.save(file_path)
        print(f"评价数据已保存到 {file_path}")

        return file_path

    def export_reviews_legacy(
        self,
        app_id: int,
        rollups: list[dict],
        output_subdir: str = "steam_recommendations_data",
    ) -> Path:
        """导出评价数据（兼容原有数据格式）。

        Args:
            app_id: Steam 游戏 ID。
            rollups: 原始 API 返回的 rollups 数据。
            output_subdir: 输出子目录名。

        Returns:
            Path: 导出文件的路径。
        """
        import datetime as dt

        subdir = self.output_dir / output_subdir
        subdir.mkdir(parents=True, exist_ok=True)

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = f"AppID_{app_id}"

        ws.append(["id", "date", "recommendations_up", "recommendations_down"])

        for item in rollups:
            ts = item["date"]
            positive = item["recommendations_up"]
            negative = item["recommendations_down"]

            dt_utc = dt.datetime.utcfromtimestamp(ts)
            dt_local = dt_utc + dt.timedelta(hours=8)
            date_str = dt_local.strftime("%Y-%m-%d")

            ws.append([app_id, date_str, positive, negative])

        file_path = subdir / f"steam_recommendations_{app_id}.xlsx"
        wb.save(file_path)
        print(f"评价数据已保存到 {file_path}")

        return file_path


def save_appids_to_file(
    app_ids: list[int],
    filename: str = "steam_appids.txt",
    directory: Optional[str | Path] = None,
    config: Optional[Config] = None,
) -> Path:
    """将 app_id 列表保存到文件。

    Args:
        app_ids: app_id 列表。
        filename: 文件名。
        directory: 可选的目录路径。
        config: 可选的配置对象。

    Returns:
        Path: 保存文件的路径。
    """
    if directory:
        dir_path = Path(directory)
    else:
        cfg = config or get_config()
        dir_path = Path(cfg.output.data_dir)

    dir_path.mkdir(parents=True, exist_ok=True)
    file_path = dir_path / filename

    with open(file_path, "w", encoding="utf-8") as f:
        for app_id in app_ids:
            f.write(str(app_id) + "\n")

    print(f"App IDs 已保存到 {file_path}")

    return file_path
