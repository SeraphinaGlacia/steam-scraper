# 采集失败与断点恢复

搜索总数请求或任意搜索页失败时，`games` / `all` 会以非零退出码停止。
已提交的游戏信息及断点保留，失败页和未完成页不会被当作完整成功。
网络恢复后，使用与原任务相同的配置和页数限制继续：

```bash
uv run steam-scraper games --resume
# 原先运行完整流程时：
uv run steam-scraper all --resume
```

搜索页失败尚未取得完整 AppID 列表，需使用上述恢复命令；`retry` 用于已经记录了
AppID 的游戏详情或评价失败。获取不到可靠总数时，程序不再猜测一个固定页数。

`reviews --input FILE` 会先读取并验证输入，再清理本次评价断点。文件不存在、不可读、
编码错误或没有有效 AppID 时返回非零退出码，原断点保持不变。空行跳过，非法文本、
零和负数给出提示后跳过；其余有效 AppID 继续采集。

HTTPS 默认验证服务器证书与主机名。如果使用自定义 CA 的网络环境，可以通过 HTTPX
支持的 `SSL_CERT_FILE` / `SSL_CERT_DIR` 配置信任链；应修复证书配置，而不是关闭验证。

## English

Search-count or page failures stop `games` / `all` with a nonzero exit code. Committed
records are retained; incomplete pages remain eligible for `--resume`. Resume using
the same configuration and page limit. `retry` handles known AppID failures, while
search-page failures require `games --resume` or `all --resume`.

Input files are read before clearing review checkpoints. Missing, unreadable,
incorrectly encoded, or entirely invalid input files leave the checkpoint intact
and fail with a nonzero exit code. Invalid lines and nonpositive IDs are skipped.

HTTPS uses certificate and hostname verification. Configure `SSL_CERT_FILE` or
`SSL_CERT_DIR` if a custom CA is required; do not disable verification.
