# 平准基金观测站（国家队ETF监控）

仅以中国大陆A股为范围，观察中央汇金系（类“平准基金”）相关宽基ETF：
每日抓取ETF市场总份额，与基金定期报告披露的历史汇金持仓参考线比较；
叠加上证、深证、科创50上的政策/价格低点标注、纯A股事件研究和四模型会诊。
纯静态站点 + GitHub Actions，零服务器成本。

重要口径：ETF总份额变化来自全市场，不是中央汇金逐日持仓。总份额低于
历史汇金持仓参考线，只表示数学上的“低于历史参考线”，不再写成“确认减持”；
最终持仓变化要等基金定期报告确认。

## 本地预览（用种子数据即可看到页面效果）

```bash
cd etf-monitor
python3 -m http.server 8000
# 浏览器打开 http://localhost:8000
```

注意必须通过 HTTP 访问，直接双击 index.html 会因浏览器安全策略读不到 JSON。

## 离线可跑的部分

```bash
python3 -m unittest discover tests    # 22个测试，含评分组合、数据时效、买卖双向与模型门槛回归测试
python3 scripts/daily_comment.py      # 用现有历史数据生成当日解读
python3 scripts/daily_assessment.py   # 生成风险、修复和数据可信度评分JSON
```

## 部署为"永久网页"

1. 新建 GitHub 仓库，把本目录全部推上去
2. Settings → Pages → Source 选 `main` 分支根目录
3. Settings → Actions → General 里允许 workflow 写入（Read and write permissions）
4. Actions 页手动触发一次 `daily-update` 验证全流程
5. 之后每个交易日 15:40 自动抓数、生成解读、提交并刷新页面

## 数据源优先级

- ETF 份额每日更新首先查询上交所/深交所最近 7 天披露，并按返回记录的
  实际日期落盘；只有官方源失败时才使用东方财富 f84，且标记为未核验。
- 深交所159919嘉实沪深300ETF直接使用 `fund_jjgm` 基金规模报表的
  `current_size`（万份）字段，来源标记为 `szse_official`。
- 上交所 SCALE（亿元）优先除以同日单位净值反推亿份，来源标记为
  `sse_official_derived_nav`。净值不可得时使用未复权收盘价，标记为
  `sse_official_derived_px`；该路径会受到 ETF 折溢价影响，误差通常约
  ±0.5% 以内，但极端行情下可能更大。
- 首次联网运行 `python scripts/backfill_etf_shares.py`，可回补
  2026-01-23 至今的每日份额；指数回补使用 `fetch_index_daily.py`。

## 日常维护

- **更新汇金基线（最重要）**：每逢基金定期报告披露
  （1/4/7/10月下旬及3月底、8月底），把最新汇金系持仓写入
  `data/baselines.json` 并更新 `baseline_date`。页面会在基线超过
  120 天未更新时显示提醒。
- 新增监控标的：在 `baselines.json` 的 `etfs` 数组追加一项即可。
- 节假日表：`data/holidays.json` 每年初补充当年节假日（或改用
  chinese_calendar 库）。
- 事件库：`data/bottom_events.json`（图上标注）与
  `data/intervention_samples.json`（事件研究样本），标记
  `"verify": true` 的条目需核实后转为 false。
- 统计范围：`scripts/event_study.py` 与 `scripts/daily_assessment.py`
  都固定为 `CN`；即使样本档案中留有港台历史条目，也不会进入计算或页面。

## 目录结构

```
index.html / assets/        前端（ECharts, 深色模式自适应）
scripts/fetch_etf_shares.py 每日份额抓取（交易所官方优先 + 东财兜底）
scripts/backfill_etf_shares.py 回补2026-01-23至今的ETF份额历史
scripts/fetch_index_daily.py指数日线回补与增量（akshare）
scripts/daily_comment.py    规则引擎每日解读
scripts/event_study.py      事件研究（前瞻收益/回撤/bootstrap基准）
scripts/daily_assessment.py 每日评分（风险/修复/数据可信度）及四模型明细
scripts/import_history.py   历史份额CSV手动导入兜底
data/                       全部数据与配置（JSON）
report.html                 永久在线的模型评估报告
output/pdf/                 可转发的静态PDF评估指南
scripts/build_assessment_pdf.py 根据最新评估JSON生成PDF指南
MODEL_ASSESSMENT_REPORT.md  可下载/审阅的报告文本
tests/                      离线单元测试
.github/workflows/daily.yml 每日自动更新流水线
```

## 免责声明

个人研究工具。份额变化不能单独证明国家队买卖；事件研究只有7个纯A股样本，
存在内生性偏差；历史规律不保证未来重复。页面提供通用观察与风险提示，
不了解用户个人财务情况，不提供个性化买卖指令或投资建议。
