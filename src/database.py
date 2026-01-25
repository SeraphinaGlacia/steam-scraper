"""
数据库管理模块。

使用 SQLite 存储游戏信息和评价数据，并提供统一的 Excel 导出功能。
选择 SQLite 是因为它无需额外服务器，数据单文件存储，便于复制和分享。
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Optional

import pandas as pd

from src.models import GameInfo, ReviewSnapshot


class DatabaseManager:
    """数据库管理器。

    Attributes:
        db_path: 数据库文件路径。
        conn: SQLite 连接对象。
    """

    def __init__(self, db_path: str | Path):
        """初始化数据库管理器。

        Args:
            db_path: 数据库路径。
        """
        self.db_path = str(db_path)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.init_db()

    def init_db(self) -> None:
        """初始化数据库表结构。
        
        创建 games 和 reviews 两张表：
        - games: 存储游戏基础信息，以 app_id 为主键
        - reviews: 存储评价历史数据，使用 (app_id, date) 联合唯一约束
        """
        cursor = self.conn.cursor()

        # 创建游戏表
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS games (
                app_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                release_date TEXT,
                price TEXT,
                developers TEXT,  -- JSON 数组字符串，因为开发商可能有多个
                publishers TEXT,  -- JSON 数组字符串，因为发行商可能有多个
                genres TEXT,      -- JSON 数组字符串，因为游戏类型可能有多个
                description TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # 创建评价表
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                app_id INTEGER,
                date TEXT,
                recommendations_up INTEGER,
                recommendations_down INTEGER,
                FOREIGN KEY (app_id) REFERENCES games (app_id),
                -- 联合唯一约束防止重复插入同一天的评价数据
                -- 并且允许通过 INSERT OR REPLACE 更新已存在的记录
                UNIQUE(app_id, date)
            )
            """
        )

        self.conn.commit()

    def save_game(self, game: GameInfo) -> None:
        """保存或更新游戏信息。

        Args:
            game: 游戏信息对象。
        """
        cursor = self.conn.cursor()
        
        # 将列表转换为 JSON 字符串存储
        # 使用 JSON 而非逗号分隔，因为开发商/发行商名称本身可能包含逗号
        # ensure_ascii=False 保留中文字符的原始形式，提高可读性
        developers_json = json.dumps(game.developers, ensure_ascii=False)
        publishers_json = json.dumps(game.publishers, ensure_ascii=False)
        genres_json = json.dumps(game.genres, ensure_ascii=False)

        cursor.execute(
            """
            INSERT OR REPLACE INTO games 
            (app_id, name, release_date, price, developers, publishers, genres, description, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                game.app_id,
                game.name,
                game.release_date,
                game.price,
                developers_json,
                publishers_json,
                genres_json,
                game.description,
            ),
        )
        self.conn.commit()

    def save_reviews(self, app_id: int, reviews: list[ReviewSnapshot]) -> None:
        """保存评价历史数据。

        Args:
            app_id: 游戏 ID。
            reviews: 评价快照列表。
        """
        if not reviews:
            return

        cursor = self.conn.cursor()
        
        data = [
            (
                app_id,
                review.date.strftime("%Y-%m-%d"),
                review.recommendations_up,
                review.recommendations_down,
            )
            for review in reviews
        ]

        cursor.executemany(
            """
            INSERT OR REPLACE INTO reviews 
            (app_id, date, recommendations_up, recommendations_down)
            VALUES (?, ?, ?, ?)
            """,
            data,
        )
        self.conn.commit()

    def get_all_app_ids(self) -> list[int]:
        """获取数据库中所有已存在的 app_id。

        Returns:
            list[int]: app_id 列表。
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT app_id FROM games")
        return [row[0] for row in cursor.fetchall()]

    def is_game_exists(self, app_id: int) -> bool:
        """检查游戏是否存在。"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT 1 FROM games WHERE app_id = ?", (app_id,))
        return cursor.fetchone() is not None

    def export_to_excel(self, output_file: str | Path) -> None:
        """导出所有数据到 Excel。

        Args:
            output_file: 输出文件路径。
        """
        with pd.ExcelWriter(output_file, engine="openpyxl") as writer:
            # 导出游戏信息
            games_df = pd.read_sql_query("SELECT * FROM games", self.conn)
            
            # 处理 JSON 字段还原为逗号分隔字符串，以便于阅读
            # SQLite 中存储的是 JSON 数组（保留完整结构），
            # 但 Excel 中用户更希望看到易读的 "关卡, 动作, RPG" 格式
            for col in ["developers", "publishers", "genres"]:
                if col in games_df.columns:
                    games_df[col] = games_df[col].apply(
                        lambda x: ", ".join(json.loads(x)) if x else ""
                    )
            
            games_df.to_excel(writer, sheet_name="Games", index=False)

            # 导出评价信息
            reviews_df = pd.read_sql_query(
                """
                SELECT r.*, g.name as game_name 
                FROM reviews r 
                LEFT JOIN games g ON r.app_id = g.app_id
                ORDER BY r.app_id, r.date
                """, 
                self.conn
            )
            reviews_df.to_excel(writer, sheet_name="Reviews", index=False)

    def close(self) -> None:
        """关闭数据库连接。"""
        self.conn.close()
