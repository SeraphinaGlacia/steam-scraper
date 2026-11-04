# 评价数据的统计口径与升级

Steam 的评价历史接口不保证提供全历史日频数据。它通常返回按月或按周聚合的
`rollups`，另有一个近期逐日窗口 `recent`。本工具保存接口实际提供的两部分，
不把整月数量当作单日数量，也不从月度数据推算日度数据。

`reviews` 表及 Excel / CSV 导出的 `granularity` 列表示统计粒度：

| 值 | 含义 |
| --- | --- |
| `day` | 一个 UTC 日期的评价数量 |
| `week` | 接口返回的一周统计桶 |
| `month` | 接口返回的一月统计桶，当前月可能尚未结束 |
| `unknown` | 旧数据或接口未提供足够信息，不能确定统计粒度 |

`date` 表示统计桶的 UTC 起点。日桶与月桶、周桶可能覆盖同一段时间，**不能跨粒度
直接求和**。例如查询逐日数据应加 `WHERE granularity = 'day'`；需要更长时期的趋势，
应选择相同聚合粒度，检查所需时间范围是否完整。

每次成功采集会替换该游戏的整份接口快照，包括合法的空快照；失败不会覆盖原有快照。
这是接口当前快照，不是不断累积的日频档案：此前保存的近期日桶移出接口窗口后，
下一次刷新会移除它们。需要长期完整日频数据时，应另外建立持续采集和归档方案。

升级后首次打开旧数据库会迁移表结构，保留原记录并标记为 `unknown`。旧评价断点会
失效，游戏 AppID 的完成状态保留。运行以下命令可以重新采集评价，逐个替换旧记录：

```bash
uv run steam-scraper reviews --resume
```

在某个游戏成功重抓前，它的旧数据仍保留为 `unknown`。不要把它当作已经修正的日频
数据。数据库唯一键改为 `(app_id, date, granularity)`；外部程序的查询与去重逻辑也应
纳入 `granularity`，不能继续假定同一游戏、同一日期只存在一条记录。

## English

The histogram endpoint provides weekly or monthly rollups and a recent daily window,
not necessarily a complete daily history. Exports now include `granularity`
(`day`, `week`, `month`, or `unknown`), and `date` is the UTC bucket start.
Different granularities overlap: filter to one granularity before aggregating.

Successful fetches replace each game's complete API snapshot, including empty
snapshots. Daily rows that leave the API's recent window are removed on refresh;
this is not a continuously accumulated daily archive. Failed fetches preserve the
previous snapshot.

Legacy rows are retained as `unknown` until successfully refreshed. Old review
checkpoints are invalidated so `reviews --resume` refetches them. The review unique
key is now `(app_id, date, granularity)`; downstream consumers must include the
granularity rather than assuming one row per game and date.
