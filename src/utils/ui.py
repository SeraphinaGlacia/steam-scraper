"""
UI 管理模块。

基于 rich 库封装统一的控制台输出、进度条和表格展示。
此模块确保整个项目的 CLI 输出风格统一，并提供一致的用户体验。
"""

from __future__ import annotations

from typing import Any, Optional

from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeRemainingColumn,
)
from rich.prompt import Confirm
from rich.style import Style
from rich.table import Table
from rich.theme import Theme


class UIManager:
    """统一的 UI 管理器，负责所有控制台输出。

    封装了 rich 库的 Console、Progress、Table 等功能，
    提供统一的样式主题和便捷的输出方法。

    Attributes:
        theme: rich 主题配置，定义了 info/warning/error 等样式。
        console: rich Console 实例，用于实际输出。
    """

    def __init__(self) -> None:
        """初始化 UI 管理器，配置默认主题。"""
        self.theme = Theme(
            {
                "info": "cyan",
                "warning": "yellow",
                "error": "red bold",
                "success": "green",
                "header": "blue bold",
            }
        )
        self.console = Console(theme=self.theme)
        self._progress: Optional[Progress] = None

    def print(self, message: str, style: str = "") -> None:
        """打印消息。"""
        self.console.print(message, style=style)

    def print_success(self, message: str) -> None:
        """打印成功消息（绿色带对勾图标）。

        Args:
            message: 成功消息内容。
        """
        self.console.print(f"✅ {message}", style="success")

    def print_error(self, message: str) -> None:
        """打印错误消息（红色加粗带叉号图标）。

        Args:
            message: 错误消息内容。
        """
        self.console.print(f"❌ {message}", style="error")

    def print_warning(self, message: str) -> None:
        """打印警告消息（黄色带警告图标）。

        Args:
            message: 警告消息内容。
        """
        self.console.print(f"⚠️  {message}", style="warning")
        
    def print_info(self, message: str) -> None:
        """打印普通信息（青色带信息图标）。

        Args:
            message: 信息内容。
        """
        self.console.print(f"ℹ️  {message}", style="info")

    def print_panel(self, content: str, title: str = "", style: str = "header") -> None:
        """打印带边框的面板。

        Args:
            content: 面板内容，支持 rich 标记。
            title: 可选的面板标题。
            style: 面板样式，默认为 "header"。
        """
        self.console.print(Panel(content, title=title, expand=False, style=style))

    def confirm(self, message: str, default: bool = False) -> bool:
        """发起确认请求。

        Args:
            message: 确认提示消息。
            default: 默认值，True 表示默认确认。

        Returns:
            bool: 用户的确认结果。
        """
        return Confirm.ask(message, default=default, console=self.console)

    def create_progress(self) -> Progress:
        """创建新的进度条实例。

        Returns:
            Progress: 配置好的 rich Progress 实例。
        """
        return Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TextColumn("•"),
            TimeRemainingColumn(),
            console=self.console,
        )

    def create_table(self, title: str = "") -> Table:
        """创建表格。

        Args:
            title: 可选的表格标题。

        Returns:
            Table: 配置好的 rich Table 实例。
        """
        table = Table(title=title, show_header=True, header_style="bold magenta")
        return table
