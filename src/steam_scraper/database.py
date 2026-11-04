"""数据库管理模块。

使用 SQLite 存储游戏信息和评价数据，并提供统一的 Excel 导出功能。
选择 SQLite 是因为它无需额外服务器，数据单文件存储，便于复制和分享。
"""

import json
import sqlite3
import tempfile
from pathlib import Path

from steam_scraper.models import GameInfo, ReviewSnapshot

_REVIEWS_SCHEMA = """
    CREATE TABLE IF NOT EXISTS reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        app_id INTEGER,
        date TEXT,
        recommendations_up INTEGER,
        recommendations_down INTEGER,
        granularity TEXT NOT NULL DEFAULT 'unknown'
            CHECK (granularity IN ('day', 'week', 'month', 'unknown')),
        FOREIGN KEY (app_id) REFERENCES games (app_id),
        UNIQUE(app_id, date, granularity)
    )
"""

try:
    import orjson
except ImportError:

    def _json_dumps(value: object) -> str:
        return json.dumps(value, ensure_ascii=False)

else:

    def _json_dumps(value: object) -> str:
        return orjson.dumps(value).decode("utf-8")


def _format_json_list(value: object) -> str:
    if not value:
        return ""
    if not isinstance(value, str):
        return str(value)

    decoded: object = json.loads(value)
    if not isinstance(decoded, list):
        return value
    return ", ".join(str(item) for item in decoded)


class DatabaseManager:
    """数据库管理器。

    Attributes:
        db_path: 数据库文件路径。
        conn: SQLite 连接对象。
    """

    def __init__(self, db_path: str | Path) -> None:
        """初始化数据库管理器。

        Args:
            db_path: 数据库路径。
        """
        db_file = Path(db_path)
        if str(db_file) != ":memory:":
            db_file.parent.mkdir(parents=True, exist_ok=True)

        self.db_path = str(db_file)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.init_db()

    def init_db(self) -> None:
        """初始化数据库表结构。

        创建 games 和 reviews 两张表：
        - games: 存储游戏基础信息，以 app_id 为主键
        - reviews: 按 (app_id, date, granularity) 区分日、周、月统计桶

        旧评价表缺少粒度时，事务性迁移并保留为 unknown，等待重新采集替换。
        """
        cursor = self.conn.cursor()

        # 开启 WAL 模式 (Write-Ahead Logging)
        # 1. 提高并发性能：读写操作不再相互阻塞
        # 2. 提升写入速度：减少 fsync 次数
        cursor.execute("PRAGMA journal_mode=WAL")

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

        self._init_reviews()
        self.conn.commit()

    def _init_reviews(self) -> None:
        """迁移旧唯一约束，同时保留无法确定粒度的历史数据。

        Raises:
            sqlite3.Error: 迁移失败；原表及其数据保持不变。
        """
        columns = {row[1] for row in self.conn.execute("PRAGMA table_info(reviews)")}
        self.conn.execute("SAVEPOINT review_schema")
        try:
            if columns and "granularity" not in columns:
                self.conn.execute("ALTER TABLE reviews RENAME TO reviews_legacy")
                self.conn.execute(_REVIEWS_SCHEMA)
                self.conn.execute(
                    """
                    INSERT INTO reviews
                        (id, app_id, date, recommendations_up,
                         recommendations_down, granularity)
                    SELECT id, app_id, date, recommendations_up,
                           recommendations_down, 'unknown'
                    FROM reviews_legacy
                    """
                )
                self.conn.execute("DROP TABLE reviews_legacy")
            else:
                self.conn.execute(_REVIEWS_SCHEMA)
        except sqlite3.Error:
            self.conn.execute("ROLLBACK TO review_schema")
            self.conn.execute("RELEASE review_schema")
            raise
        self.conn.execute("RELEASE review_schema")

    def save_game(self, game: GameInfo, commit: bool = True) -> None:
        """保存或更新游戏信息。

        Args:
            game: 游戏信息对象。
            commit: 是否立即提交事务。默认为 True。
        """
        cursor = self.conn.cursor()

        # 将列表转换为 JSON 字符串存储
        # 使用 JSON 而非逗号分隔，因为开发商/发行商名称本身可能包含逗号
        # ensure_ascii=False 保留中文字符的原始形式，提高可读性
        # 使用 helper 函数进行统一序列化
        developers_json = _json_dumps(game.developers)
        publishers_json = _json_dumps(game.publishers)
        genres_json = _json_dumps(game.genres)

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
        if commit:
            self.conn.commit()

    def save_games_batch(self, games: list[GameInfo], commit: bool = True) -> None:
        """批量保存或更新游戏信息。

        Args:
            games: 游戏信息对象列表。
            commit: 是否立即提交事务。默认为 True。
        """
        if not games:
            return

        cursor = self.conn.cursor()

        data = []
        for game in games:
            developers_json = _json_dumps(game.developers)
            publishers_json = _json_dumps(game.publishers)
            genres_json = _json_dumps(game.genres)

            data.append(
                (
                    game.app_id,
                    game.name,
                    game.release_date,
                    game.price,
                    developers_json,
                    publishers_json,
                    genres_json,
                    game.description,
                )
            )

        cursor.executemany(
            """
            INSERT OR REPLACE INTO games 
            (app_id, name, release_date, price, developers, publishers, genres, description, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            data,
        )
        if commit:
            self.conn.commit()

    def commit(self) -> None:
        """提交当前事务。"""
        self.conn.commit()

    def save_reviews(
        self, app_id: int, reviews: list[ReviewSnapshot], commit: bool = True
    ) -> None:
        """原子替换一个游戏的完整评价接口快照。

        空快照清除该游戏旧记录；日、周、月桶可以并存，不可跨粒度相加。
        写入失败时保留替换前的数据，延迟提交时仍由调用方提交整个事务。

        Args:
            app_id: 游戏 ID。
            reviews: 本次接口返回的全部统计桶，包括近期日桶。
            commit: 是否立即提交事务。默认为 True。

        Raises:
            ValueError: 记录所属 AppID 与目标游戏不一致。
        """
        if any(review.app_id != app_id for review in reviews):
            raise ValueError("评价记录的 AppID 必须与目标游戏一致")

        data = [
            (
                app_id,
                review.date.strftime("%Y-%m-%d"),
                review.recommendations_up,
                review.recommendations_down,
                review.granularity,
            )
            for review in reviews
        ]

        # 外层事务使 RELEASE 不会提前提交 commit=False 的批次。
        if not self.conn.in_transaction:
            self.conn.execute("BEGIN")
        self.conn.execute("SAVEPOINT replace_reviews")
        try:
            self.conn.execute("DELETE FROM reviews WHERE app_id = ?", (app_id,))
            self.conn.executemany(
                """
                INSERT INTO reviews
                    (app_id, date, recommendations_up, recommendations_down, granularity)
                VALUES (?, ?, ?, ?, ?)
                """,
                data,
            )
            if commit:
                # COMMIT 失败时仍保留保存点，避免后续任务意外提交本次失败的替换。
                self.conn.commit()
            else:
                self.conn.execute("RELEASE replace_reviews")
        except Exception:
            # 某些 SQLite 错误会自动回滚整个事务，此时保存点已不存在。
            if self.conn.in_transaction:
                self.conn.execute("ROLLBACK TO replace_reviews")
                self.conn.execute("RELEASE replace_reviews")
            raise

    def get_all_app_ids(self) -> list[int]:
        """获取数据库中所有已存在的 app_id。

        Returns:
            list[int]: app_id 列表。
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT app_id FROM games")
        return [row[0] for row in cursor.fetchall()]

    def is_game_exists(self, app_id: int) -> bool:
        """检查游戏是否存在。

        Returns:
            指定 AppID 已存在时返回 True。
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT 1 FROM games WHERE app_id = ?", (app_id,))
        return cursor.fetchone() is not None

    def export_to_excel(self, output_file: str | Path) -> None:
        """导出所有数据到 Excel。

        完整写出后才替换目标文件；导出失败时保留原有文件。

        Args:
            output_file: 输出文件路径。
        """
        import pandas as pd

        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            dir=output_path.parent, prefix=".steam-export-"
        ) as temporary_dir:
            temporary_file = Path(temporary_dir) / output_path.name
            with pd.ExcelWriter(temporary_file, engine="openpyxl") as writer:
                games_df = pd.read_sql_query("SELECT * FROM games", self.conn)

                # 数据库保留 JSON 结构，表格中用逗号分隔以方便阅读。
                for col in ["developers", "publishers", "genres"]:
                    if col in games_df.columns:
                        games_df[col] = games_df[col].apply(_format_json_list)

                games_df.to_excel(writer, sheet_name="Games", index=False)

                reviews_df = pd.read_sql_query(
                    """
                    SELECT r.*, g.name as game_name
                    FROM reviews r
                    LEFT JOIN games g ON r.app_id = g.app_id
                    ORDER BY r.app_id, r.date
                    """,
                    self.conn,
                )
                reviews_df.to_excel(writer, sheet_name="Reviews", index=False)

                # 商店文案是普通文本；openpyxl 默认把以等号开头的字符串识别为公式。
                for sheet in writer.sheets.values():
                    for row in sheet.iter_rows():
                        for cell in row:
                            if cell.data_type == "f":
                                cell.data_type = "s"

            temporary_file.replace(output_path)

    def export_to_csv(
        self, output_dir: str | Path, *, spreadsheet_safe: bool = True
    ) -> None:
        """导出所有数据到 CSV 文件。

        生成两个文件：
        - steam_games.csv
        - steam_reviews.csv

        Args:
            output_dir: 输出目录。
            spreadsheet_safe: 是否保护可能被电子表格解释为公式的文本；
                设为 False 可保留机器分析使用的原始值。
        """
        import pandas as pd

        from steam_scraper.utils.csv_export import write_csv_pair

        # 1. 导出 Games
        games_df = pd.read_sql_query("SELECT * FROM games", self.conn)

        # 处理 JSON 字段还原为逗号分隔字符串
        for col in ["developers", "publishers", "genres"]:
            if col in games_df.columns:
                games_df[col] = games_df[col].apply(_format_json_list)

        # 2. 导出 Reviews
        reviews_df = pd.read_sql_query(
            """
            SELECT r.*, g.name as game_name 
            FROM reviews r 
            LEFT JOIN games g ON r.app_id = g.app_id
            ORDER BY r.app_id, r.date
            """,
            self.conn,
        )
        write_csv_pair(
            games_df, reviews_df, output_dir, spreadsheet_safe=spreadsheet_safe
        )

    def close(self) -> None:
        """关闭数据库连接。"""
        self.conn.close()
