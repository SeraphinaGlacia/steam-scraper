"""
UI 管理模块。

基于 rich 库封装统一的控制台输出、进度条和表格展示。
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
    """UI 管理器，负责所有控制台输出。"""

    def __init__(self) -> None:
        """初始化 UI 管理器。"""
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
        """打印成功消息。"""
        self.console.print(f"✅ {message}", style="success")

    def print_error(self, message: str) -> None:
        """打印错误消息。"""
        self.console.print(f"❌ {message}", style="error")

    def print_warning(self, message: str) -> None:
        """打印警告消息。"""
        self.console.print(f"⚠️  {message}", style="warning")
        
    def print_info(self, message: str) -> None:
        """打印普通信息。"""
        self.console.print(f"ℹ️  {message}", style="info")

    def print_panel(self, content: str, title: str = "", style: str = "header") -> None:
        """打印面板。"""
        self.console.print(Panel(content, title=title, expand=False, style=style))

    def confirm(self, message: str, default: bool = False) -> bool:
        """发起确认请求。"""
        return Confirm.ask(message, default=default, console=self.console)

    def create_progress(self) -> Progress:
        """创建新的进度条实例。"""
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
        """创建表格。"""
        table = Table(title=title, show_header=True, header_style="bold magenta")
        return table
