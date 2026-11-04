# CSV 导出与原始文本

默认 CSV 适合在电子表格中打开：可能被识别为公式的外部文本会添加单引号文本前缀。
例如游戏名 `=1+1` 在 CSV 中保存为 `'=1+1`。数值列不添加前缀，数据库原值不变。
所有文本使用正确的 CSV 引号转义，包括逗号、引号及换行。

```bash
uv run steam-scraper export --format csv
```

如果 CSV 仅供程序分析，需要保留字段的原始字符串，可以显式选择原始模式：

```bash
uv run steam-scraper export --format csv --raw-csv --output exports/raw/
```

`--raw-csv` 只能与 `--format csv` 一起使用。原始模式的文件不提供公式防护；
若要在电子表格中查看，使用默认模式，或通过导入功能将文本列明确设为文本。
不同电子表格对 CSV 的解释可能不同，重新保存 CSV 后也不能假定转义仍保持不变。

导出先完整生成 Games 和 Reviews 两份临时文件，再发布正式文件。生成失败不会
覆盖旧文件；可捕获的发布异常会恢复已经替换的文件，首次导出失败也不会留下半套。
如果连回滚操作都失败，会保留备份并在错误信息中给出路径。

两次文件替换不是文件系统事务，因此进程被强制终止、断电或其他进程同时写入
不在成对回滚保证范围内。请勿同时向同一目录导出。

## English

CSV export defaults to spreadsheet-safe text: potentially executable text fields
receive a leading apostrophe, while numeric values and database contents are
unchanged. Use `export --format csv --raw-csv` only when original strings are needed
for programmatic analysis. Raw CSV does not provide formula protection.

Both CSV files are generated before publication. A caught publication failure
restores previously replaced files; failed rollbacks retain backups and report
their location. This is not an atomic filesystem transaction across both files:
power loss, forced process termination, and concurrent writers are outside the
rollback guarantee.
