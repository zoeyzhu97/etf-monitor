# 交给 Codex 的任务清单（联网调试部分）

框架代码已写好并通过离线测试。以下任务需要联网环境完成。
**总原则：所有接口参数以实际抓包/实测为准，禁止凭记忆编造 URL 与字段名；
每完成一项，在本文件对应条目打勾并注明实测结果，最后把改动交回检查。**

## 1. 核实东方财富份额字段（最高优先级）
- [x] 运行 `python scripts/fetch_etf_shares.py`，人工核对输出量级：
      510300 应为数百亿份（2026年1月下旬约685亿份）
      - 2026-07-16 实测 f84=19,701,487,616份，即197.01亿份；量纲正确。
- [x] 第二轮已删除 `FIELD_MAPPING_VERIFIED`：官方源始终优先，只有
      官方失败才使用 f84，且东财单源记录固定 `verified=false`。
- [x] 若 f84 不对，用浏览器打开 quote.eastmoney.com 任一ETF页抓包，
      找到正确字段并修改 `fetch_eastmoney()`，同步更新注释
      - f84字段正确，无需更换；已补充HTTP状态检查与实测注释。东方财富接口后续出现间歇性502，脚本会回退官方源。

## 2. 实现交易所官方校验源 `fetch_official()`
- [x] 深交所（159919 嘉实沪深300ETF 必须覆盖）：在 fund.szse.cn
      "基金数据"页开发者工具抓包，确认
      `api/report/ShowReport/data` 的 CATALOGID / TABKEY / 字段名，
      实现按代码+日期查询份额；把实测到的完整请求样例写进代码注释
      - 实测 CATALOGID=fund_jjgm、TABKEY=tab1、字段 current_size（万份）；159919于2026-07-20为637,401.66万份=63.740166亿份。
- [x] 上交所：在 www.sse.com.cn 基金频道抓包 query.sse.com.cn 的
      commonQuery 接口（需 Referer 头），同上实现
      - 实测SCALE字段为亿元规模，配合同日上交所行情价格反推亿份；完整请求样例与单位说明已写入代码。
- [x] 跑通"主源 vs 官方源差异>1% 时采用官方"的逻辑并附一次对比输出
      - 第二轮复核：东财 f84 响应不带可靠日期且存在滞后；2026-07-20上交所SCALE配合同日单位净值反推244.1569亿份，采用`sse_official_derived_nav`；159919采用深交所63.740166亿份。

## 3. 指数日线回补
- [x] `pip install -r requirements-backfill.txt`
      - 已安装akshare 1.18.64与pandas 3.0.3。
- [x] 实测 akshare 当前版本正确函数（stock_zh_index_daily 或
      index_zh_a_hist），修正 `fetch_index_daily.py` 的字段映射
      - stock_zh_index_daily实测可用，字段为date/open/high/low/close/volume；index_zh_a_hist实测被远端断开，未采用。
- [x] 回补 000001/399001/000688 至 2005 年（000688 自 2020-07），
      核对几个锚点：上证 2024-02-05 低点约 2635、2024-09-18 约 2689
      - 000001/399001各5231条（2005-01-04至2026-07-20），000688共1468条（2020-07-01至2026-07-20）；锚点低点为2635.09、2689.70。
- [x] 增补台湾加权指数 TWII 与恒生 HSI 日线（stooq CSV 或 akshare
      国际指数接口，实测后实现），存为 data/index/TWII.json、HSI.json
      - Stooq受JavaScript挑战、akshare恒指历史仅到2013年，改用实测可用的Yahoo Chart JSON：TWII 7116条（1997-07-02起），HSI 9016条（1990-01-02起）。

## 4. 核实事件样本（data/ 下所有 "verify": true 条目）
- [x] intervention_samples.json：逐条核实 A股 2008/2011/2015/2018 的
      日期与点位；台湾国安基金9次进场日以财政部/国安基金官方公告为准
      （第9次已确认：2025-04-08决议、护盘279天、报酬率约81%）
      - 已逐条核验；第7次台湾样本由决议日2020-03-19修正为实际进场日2020-03-20；第9次净报酬率约81%、2026-05-06完成出清。A股2026卖出样本明确标为份额倒挂推算而非官方公告。
- [x] bottom_events.json：同上核实后把 verify 改为 false
      - 15条记录verify均为false，并用回补日线复核所列上证点位。
- [x] 每条补充 source_url 字段（官方公告或权威媒体链接）
      - intervention_samples 18条、bottom_events 15条均已补齐，无缺失。

## 5. 全流程验证与部署
- [x] 依次运行 fetch_etf_shares → fetch_index_daily → daily_comment →
      event_study，确认四个脚本退出码均为 0
      - 2026-07-20全流程复跑，四个脚本退出码依次为0/0/0/0；联网修改后单元测试仍为10/10通过。
- [x] `python3 -m http.server` 本地检查页面：ETF图有红色倒挂色带、
      指数图有事件圆点、历史规律表有数据、解读列表正常
      - 浏览器实测：8张ETF图红色倒挂区正常、3张指数图事件圆点正常、事件研究2张表共20行、解读2篇、免责声明保留且无横向溢出；同时修复顶部最新份额日期与已核验脚注显示。
- [ ] 推送 GitHub，启用 Pages（main 分支根目录）与 Actions 写权限，
      手动触发一次 workflow 验证自动提交
      - 当前压缩包没有Git远端，环境也没有GitHub CLI，无法在未知目标仓库上安全创建/推送；待提供仓库地址或完成GitHub连接后执行。
- [x] 检查 Actions 的 UTC 时区 cron 是否按预期在北京时间 15:40 触发
      - `.github/workflows/daily.yml` 为 `40 7 * * 1-5`，UTC 07:40即北京时间15:40；另有UTC 12:00（北京时间20:00）兜底重试。尚未在GitHub Actions线上观测实际触发。

## 6. 交回检查时请附上
- 修改过的文件列表与每处修改的一句话说明
- 一次真实抓取的控制台输出
- 部署后的 Pages 地址

## 明确禁止
- 不要改动 tests/ 中已通过的测试断言来"让测试变绿"
- 不要在解读文案中加入任何买卖建议
- 不要移除页面与解读中的免责声明
