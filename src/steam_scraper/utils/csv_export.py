"""安全导出两份 CSV，并在可捕获的发布失败后恢复原有文件。

两次文件替换不是文件系统事务：进程被强制终止、断电及其他进程同时写入
不在回滚保证范围内。回滚本身失败时保留备份，供调用方报告并人工恢复。
"""

from __future__ import annotations

import csv
import os
import shutil
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd


def _spreadsheet_text(value: object) -> object:
    """为可能被电子表格解释为公式的文本添加显式文本前缀。

    Returns:
        危险字符串的文本形式；其他值原样返回。
    """
    if not isinstance(value, str) or not value:
        return value

    stripped = value.lstrip()
    leading_space = value[: len(value) - len(stripped)]
    if stripped.startswith(("=", "+", "-", "@", "＝", "＋", "－", "＠")) or any(
        character in leading_space for character in "\t\r\n"
    ):
        # CSV 没有单元格类型；普通引号只负责转义分隔符，不能阻止公式解释。
        return "'" + value
    return value


def _check_writable(path: Path) -> None:
    """尊重只读目标，避免 os.replace 在某些平台绕过文件的只读标志。

    Raises:
        PermissionError: 路径没有写权限或明确没有任何写入权限位。
    """
    if not os.access(path, os.W_OK) or not path.stat().st_mode & 0o222:
        raise PermissionError(f"CSV 输出路径不可写: {path}")


def write_csv_pair(
    games: pd.DataFrame,
    reviews: pd.DataFrame,
    output_dir: str | Path,
    *,
    spreadsheet_safe: bool = True,
) -> None:
    """先生成两份 CSV，再发布；发布异常时恢复本次已替换的文件。

    默认导出适合在电子表格中打开的文本：危险文本添加单引号前缀，数值
    保持原类型。原始数据分析可关闭该选项。不会修改传入的 DataFrame。
    电子表格重新保存 CSV 可能改变文本转义，不能把后续文件视为仍受保护。

    Args:
        games: 已整理字段的游戏表，写入 steam_games.csv。
        reviews: 已整理字段的评价表，写入 steam_reviews.csv。
        output_dir: 两份 CSV 的输出目录。
        spreadsheet_safe: 是否给可能触发公式的字符串添加文本前缀。

    Raises:
        IsADirectoryError: 正式 CSV 输出路径已经被目录占用。
        OSError: 输出路径不可写，或生成、备份、发布文件失败。
        RuntimeError: 发布失败且无法完整回滚；错误信息包含保留的备份目录。
    """
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    _check_writable(directory)
    targets = (directory / "steam_games.csv", directory / "steam_reviews.csv")
    for target in targets:
        if target.exists():
            if not target.is_file():
                raise IsADirectoryError(f"CSV 输出路径不是文件: {target}")
            _check_writable(target)

    temporary_dir = Path(tempfile.mkdtemp(dir=directory, prefix=".steam-csv-"))
    backups: dict[Path, Path] = {}
    published: list[Path] = []
    retain_backups = False
    try:
        for frame, target in zip((games, reviews), targets, strict=True):
            exported = frame.map(_spreadsheet_text) if spreadsheet_safe else frame
            exported.to_csv(
                temporary_dir / target.name,
                index=False,
                encoding="utf-8-sig",
                # 所有文本都加 CSV 引号，防止独立 CR 被读成新的记录。
                quoting=csv.QUOTE_NONNUMERIC,
            )

        # 两份新文件均生成成功之后才备份和替换正式文件。
        for target in targets:
            if target.exists() or target.is_symlink():
                backup = temporary_dir / f"{target.name}.bak"
                shutil.copy2(target, backup, follow_symlinks=False)
                backups[target] = backup

        try:
            for target in targets:
                os.replace(temporary_dir / target.name, target)
                published.append(target)
        except BaseException as error:
            rollback_errors: list[OSError] = []
            for target in reversed(published):
                try:
                    if target in backups:
                        os.replace(backups[target], target)
                    else:
                        target.unlink(missing_ok=True)
                except OSError as rollback_error:
                    rollback_errors.append(rollback_error)
            if rollback_errors:
                retain_backups = True
                raise RuntimeError(
                    f"CSV 导出失败且回滚不完整；恢复备份保留在 {temporary_dir}"
                ) from error
            raise
    finally:
        if not retain_backups:
            shutil.rmtree(temporary_dir)
