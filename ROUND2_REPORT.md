# etf-monitor 第二轮执行报告

执行日期：2026-07-21。审查方提供的三个最终文件先覆盖，随后立即运行
`python3 -m unittest discover tests`，结果为 12/12 通过。三个文件此后
未再修改。

## A. f84 校验矛盾

第一轮确实存在记录不充分和表述不严谨：当时代码只返回解析后的数字，
没有打印或保存 `response.text`，所以只留下了
`f84=19,701,487,616份（197.01487616亿份）`。`stock/get` 是快照接口，
不支持事后按 2026-07-16 回查；因此无法诚实地补出当时的完整原始 JSON，
也不会根据现有字段结构伪造一份。审计状态见
`data/audit/eastmoney_510300_2026-07-16_capture_status.json`。

2026-07-21 重新请求可用的东财延迟快照接口，完整原始响应如下（文件见
`data/audit/eastmoney_510300_latest_raw.json`）：

```json
{"rc":0,"rt":4,"svr":177542536,"lt":2,"full":1,"dlmkts":"8,10,128","dsc":"0","data":{"f57":"510300","f58":"沪深300ETF华泰柏瑞","f84":21716587776.0,"f85":21716587776.0,"f116":100982133158.40001,"f117":100982133158.40001,"f124":0.0,"f297":"-"}}
```

矛盾的原因是 **f84 有滞后且该响应没有可靠数据日期**：

- 7月16日：上交所 SCALE 936.4117亿元 / 单位净值4.7485 =
  197.2016亿份，与第一轮 f84 的197.0149亿份相差-0.095%。第一轮据数值
  倒推出它约对应7月16日，但错误地把这个推断写成了接口自带的日期证据。
- 7月17日：996.5742 / 4.5827 = 217.4644亿份，与最新 f84 的
  217.1659亿份相差-0.137%。
- 7月20日：1135.6224 / 4.6512 = 244.1569亿份。此时最新 f84 仍接近
  7月17日而不是7月20日，说明其份额字段至少滞后一至两个交易日。

因此删除第一轮关于“f84 已与最新官方值一致”的注释，并按 B 将其降为
未核验兜底源。

## B–D. 数据源与日常抓取修正

- B：`fetch_official()` 先执行；官方成功时不再请求 f84。仅有东财时
  `source=eastmoney_f84`、`verified=false`，并删除
  `FIELD_MAPPING_VERIFIED`。
- C：上交所和深交所均查询 `[今天-7天, 今天]`，取最新返回记录，并用
  `TRADE_DATE` / `size_date` 的实际日期落盘。
- D：上交所 SCALE 优先除以东财同日单位净值，标记
  `sse_official_derived_nav`；净值缺失才用未复权收盘价并标记
  `sse_official_derived_px`。README 已注明价格路径存在折溢价误差。

2026-07-21 盘前实测：

```text
510300 (244.156862745098, 'sse_official_derived_nav', '2026-07-20')
159919 (63.740166, 'szse_official', '2026-07-20')
```

## E. 2026年1–7月份额回补

新增 `scripts/backfill_etf_shares.py`。8只ETF均回补116个交易日
（2026-01-23至2026-07-20）；6只沪市ETF的116条记录全部使用单位净值
反推，价格兜底为0条；2只深市ETF全部使用深交所直接份额。

回补后的 `data/history/510300.json` 前5条：

```json
{"date":"2025-12-31","total_shares_yi":888.3,"source":"fund_q4_report","verified":true}
{"date":"2026-01-21","total_shares_yi":719.78,"source":"media_wind","verified":true}
{"date":"2026-01-22","total_shares_yi":685.35,"source":"media_wind","verified":true}
{"date":"2026-01-23","total_shares_yi":643.21,"source":"sse_official_derived_nav","verified":true}
{"date":"2026-01-26","total_shares_yi":604.78,"source":"sse_official_derived_nav","verified":true}
```

后5条：

```json
{"date":"2026-07-14","total_shares_yi":184.59,"source":"sse_official_derived_nav","verified":true}
{"date":"2026-07-15","total_shares_yi":184.12,"source":"sse_official_derived_nav","verified":true}
{"date":"2026-07-16","total_shares_yi":197.2,"source":"sse_official_derived_nav","verified":true}
{"date":"2026-07-17","total_shares_yi":217.46,"source":"sse_official_derived_nav","verified":true}
{"date":"2026-07-20","total_shares_yi":244.16,"source":"sse_official_derived_nav","verified":true}
```

回补后已重跑 `daily_comment.py` 与 `event_study.py`。当前系统日期为7月21日，
交易所最新记录仍为7月20日，因此7月21日解读不把前一交易日数据冒充为
当日数据；网站倒挂色带已从1月下旬开始。

## 本地验收与 F

- `fetch_etf_shares → fetch_index_daily → daily_comment → event_study`
  四个脚本退出码均为0，12项单元测试通过。
- 页面实测8张ETF图、3张指数图、20行事件研究和3篇解读均正常；免责声明
  保留，无横向溢出。
- F 尚未执行推送：本地仓库没有 remote，环境没有 `gh`，并且交付要求明确
  为本轮先由审查方检查，通过后再上线。当前分支已是 `main`。
