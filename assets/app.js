/* 平准基金观测站 前端逻辑
   纯静态: 读取 data/ 下的 JSON 渲染。本地预览: python3 -m http.server */
"use strict";

const INDEX_META = {
  "000001": "上证指数",
  "399001": "深证成指",
  "000688": "科创50"
};
const EVENT_STYLE = {
  buy:    { color: "#1f5fbf", label: "公开增持" },
  policy: { color: "#5b48b0", label: "政策出台" },
  trough: { color: "#d23b3b", label: "事后价格低点" },
  sell:   { color: "#d97b1f", label: "推算的份额减少窗口" }
};
const SOURCE_LABEL = {
  szse_official: "深交所官方份额",
  sse_official_derived_nav: "上交所规模反推份额",
  sse_official_derived_px: "上交所规模/价格估算",
  eastmoney_f84: "兜底数据·未核验"
};
const VOTE_LABEL = { support: "偏暖", risk: "警惕", neutral: "中性" };
const dark = matchMedia("(prefers-color-scheme: dark)").matches;
const AXIS = dark ? "#9a9891" : "#787672";
const GRIDLINE = dark ? "#2b2d33" : "#e3e1da";
const INKLINE = dark ? "#c9c8c2" : "#44454a";

async function fetchJSON(path) {
  try {
    const r = await fetch(path, { cache: "no-store" });
    if (!r.ok) return null;
    return await r.json();
  } catch (e) { return null; }
}
async function fetchText(path) {
  try {
    const r = await fetch(path, { cache: "no-store" });
    if (!r.ok) return null;
    return await r.text();
  } catch (e) { return null; }
}
const fmt = (x, d = 2) => (x === null || x === undefined) ? "—" : Number(x).toFixed(d);
const pct = x => (x === null || x === undefined) ? "—" : (x * 100).toFixed(1) + "%";
const el = (tag, cls, html) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (html !== undefined) n.innerHTML = html;
  return n;
};
function baseChartOpts() {
  return {
    animation: false,
    grid: { left: 56, right: 18, top: 26, bottom: 32 },
    textStyle: { fontFamily: "system-ui, PingFang SC, Microsoft YaHei" },
    tooltip: { trigger: "axis", confine: true }
  };
}

/* ---------- 总览卡片 + ETF份额图 ---------- */
async function renderEtfSection(conf) {
  const grid = document.getElementById("etf-charts");
  const cards = document.getElementById("cards");
  let inverted = 0, watched = 0, latestDate = null;
  let coreSum = 0, coreCount = 0;

  for (const etf of conf.etfs) {
    const rows = await fetchJSON(`data/history/${etf.code}.json`);
    watched++;
    const box = el("div", "chart-box");
    const title = el("div", "chart-title",
      `<span>${etf.name} <code>${etf.code}</code></span>` +
      `<span class="chart-meta"><span class="badge"></span><span class="source-note"></span></span>`);
    const chartDiv = el("div", "chart");
    box.append(title, chartDiv);
    grid.append(box);
    if (!rows || !rows.length) {
      chartDiv.outerHTML = '<p class="empty" style="margin:12px">暂无份额数据，等待抓取脚本首次运行。</p>';
      continue;
    }
    const last = rows[rows.length - 1];
    title.querySelector(".source-note").textContent = SOURCE_LABEL[last.source] || last.source || "来源未知";
    if (!latestDate || last.date > latestDate) latestDate = last.date;
    const base = etf.huijin_shares_yi;
    const isInv = base !== null && last.total_shares_yi < base;
    if (isInv) {
      inverted++;
      title.querySelector(".badge").textContent =
        `低于参考线 ${(base - last.total_shares_yi).toFixed(1)} 亿份`;
    }
    if (base !== null) { coreSum += last.total_shares_yi; coreCount++; }

    // 低于历史持仓参考线的时间区间（红色色带）
    const areas = [];
    if (base !== null) {
      let start = null;
      rows.forEach((r, i) => {
        const below = r.total_shares_yi < base;
        if (below && start === null) start = r.date;
        if ((!below || i === rows.length - 1) && start !== null) {
          areas.push([{ xAxis: start }, { xAxis: below ? r.date : rows[Math.max(i - 1, 0)].date }]);
          start = null;
        }
      });
    }
    const chart = echarts.init(chartDiv, null, { renderer: "svg" });
    chart.setOption(Object.assign(baseChartOpts(), {
      xAxis: { type: "category", data: rows.map(r => r.date),
               axisLabel: { color: AXIS }, axisLine: { lineStyle: { color: GRIDLINE } } },
      yAxis: { type: "value", scale: true, name: "亿份",
               axisLabel: { color: AXIS },
               splitLine: { lineStyle: { color: GRIDLINE } } },
      tooltip: {
        trigger: "axis", confine: true,
        formatter: params => {
          const i = params[0] ? params[0].dataIndex : 0;
          const row = rows[i];
          const line = base === null ? "本ETF暂无可靠的汇金持仓参考线"
            : (row.total_shares_yi < base
              ? `低于历史参考线 ${(base - row.total_shares_yi).toFixed(1)} 亿份（不能据此确认是谁卖的）`
              : `高于历史参考线 ${(row.total_shares_yi - base).toFixed(1)} 亿份`);
          return `${row.date}<br>市场总份额 ${fmt(row.total_shares_yi)} 亿份<br>${line}<br>` +
                 `来源：${SOURCE_LABEL[row.source] || row.source || "未知"}`;
        }
      },
      series: [{
        type: "line", data: rows.map(r => r.total_shares_yi),
        lineStyle: { color: INKLINE, width: 2 }, itemStyle: { color: INKLINE },
        symbolSize: 5,
        markLine: base === null ? undefined : {
          silent: true, symbol: "none",
          lineStyle: { color: "#1f5fbf", type: "dashed" },
          label: { formatter: `历史持仓参考线 ${base}`, color: "#1f5fbf", position: "insideEndTop" },
          data: [{ yAxis: base }]
        },
        markArea: areas.length ? {
          silent: true,
          itemStyle: { color: "rgba(210,59,59,0.13)" },
          data: areas
        } : undefined
      }]
    }));
  }

  const mk = (k, v, red) => {
    const c = el("div", "card");
    c.append(el("p", "k", k), el("p", "v" + (red ? " red" : ""), v));
    return c;
  };
  cards.append(
    mk("监控标的", String(watched)),
    mk("低于历史参考线", String(inverted), inverted > 0),
    mk("可比宽基总份额", coreCount ? fmt(coreSum, 1) + " 亿份" : "—"),
    mk("持仓参考日", conf.baseline_date)
  );
  document.getElementById("statusline").textContent =
    `最新份额日期 ${latestDate || "—"} · 持仓参考来源 ${conf.updated_from}（${conf.baseline_date}）` +
    (inverted ? ` · ${inverted}只ETF总份额低于历史参考线，原因要等定期报告确认` : " · 暂无ETF低于历史参考线");

  // 基线过期提醒(>120天)
  const ageDays = (Date.now() - new Date(conf.baseline_date)) / 864e5;
  if (ageDays > 120) {
    const w = document.getElementById("baseline-warn");
    w.hidden = false;
    w.textContent = `提醒：持仓参考线已 ${Math.floor(ageDays)} 天未更新。` +
      "参考线不是每日持仓；请等待最新基金定期报告后更新，否则比较会失真。";
  }
}

/* ---------- 小白版多模型会诊 ---------- */
function renderAssessment(data) {
  const wrap = document.getElementById("assessment");
  if (!data || data.market_scope !== "CN") {
    wrap.innerHTML = '<p class="empty">今日评估尚未生成，或统计口径不是纯中国大陆A股，页面已停止展示。</p>';
    return;
  }
  wrap.innerHTML = "";
  const verdict = el("article", `verdict ${data.verdict.state}`);
  verdict.innerHTML = `<p class="verdict-k">${data.market_scope_label} · 数据截至 ${data.as_of || "—"}</p>` +
    `<h3>${data.verdict.label}</h3><p>${data.verdict.plain}</p>` +
    `<p class="rule">判定规则：${data.verdict.rule}。当前：偏暖${data.verdict.counts.support}、` +
    `警惕${data.verdict.counts.risk}、中性${data.verdict.counts.neutral}。</p>`;
  wrap.append(verdict);

  const modelGrid = el("div", "model-grid");
  for (const model of data.models || []) {
    const card = el("article", `model-card ${model.vote}`);
    card.innerHTML = `<div class="model-head"><h3>${model.name}</h3>` +
      `<span class="vote">${VOTE_LABEL[model.vote] || model.vote}</span></div>` +
      `<p class="model-title">${model.title}</p><p>${model.explanation}</p>`;
    modelGrid.append(card);
  }
  wrap.append(modelGrid);

  const sides = el("div", "two-sided-grid");
  for (const [key, side] of Object.entries({
    buy: data.two_sided.buy_side,
    sell: data.two_sided.sell_side
  })) {
    const card = el("article", `side-card ${key}`);
    card.innerHTML = `<h3>${side.label}</h3><ul>` +
      side.checks.map(item => `<li class="${item.met ? "met" : "not-met"}">` +
        `${item.met ? "✓" : "○"} ${item.label}</li>`).join("") +
      `</ul><p class="term">${side.meaning}</p>`;
    sides.append(card);
  }
  wrap.append(sides);
  wrap.append(el("p", "history-boundary", data.two_sided.history_boundary));

  const guide = el("article", "action-guide");
  guide.innerHTML = `<p class="verdict-k">通用行动框架（不是个性化买卖指令）</p>` +
    `<h3>${data.action_guide.level}</h3>` +
    `<ul>${data.action_guide.checklist.map(item => `<li>${item}</li>`).join("")}</ul>` +
    `<p class="boundary">${data.action_guide.boundary}</p>`;
  wrap.append(guide);

  const star = el("article", "star-note");
  star.innerHTML = `<h3>国家队以前买过科创板股票吗？</h3><p>${data.star_market.answer}</p>` +
    `<p>${data.star_market.distinction}</p><p class="term">本站跟踪：${data.star_market.tracked_etf}；` +
    `当前没有可靠汇金持仓参考线，所以只画走势，不判断国家队增减持。</p>`;
  wrap.append(star);
}

/* ---------- 指数 + 政策底/恐慌底标注 ---------- */
async function renderIndexSection() {
  const grid = document.getElementById("index-charts");
  const events = (await fetchJSON("data/bottom_events.json")) || [];
  for (const code of Object.keys(INDEX_META)) {
    const rows = await fetchJSON(`data/index/${code}.json`);
    const box = el("div", "chart-box");
    box.append(el("div", "chart-title", `<span>${INDEX_META[code]} <code>${code}</code></span>`));
    const chartDiv = el("div", "chart tall");
    box.append(chartDiv);
    grid.append(box);
    if (!rows || !rows.length) {
      chartDiv.outerHTML = '<p class="empty" style="margin:12px">暂无指数日线。运行 <code>python scripts/fetch_index_daily.py</code> 回补后自动显示。</p>';
      continue;
    }
    const dateIdx = new Map(rows.map((r, i) => [r.date, i]));
    const nearest = d => { // 事件日若非交易日, 取其后首个交易日
      if (dateIdx.has(d)) return d;
      const later = rows.find(r => r.date > d);
      return later ? later.date : null;
    };
    const markData = events
      .filter(ev => ev.scope.includes(code))
      .map(ev => {
        const d = nearest(ev.date);
        if (!d) return null;
        const s = EVENT_STYLE[ev.type] || EVENT_STYLE.policy;
        return {
          coord: [d, rows[dateIdx.get(d)].close],
          itemStyle: { color: s.color },
          name: `${ev.date} ${ev.title}`,
          value: s.label,
          label: { show: false },
          tooltipText: `${ev.date} · ${s.label}<br>${ev.title}${ev.note ? "<br>" + ev.note : ""}` +
                       (ev.verify ? "<br><i>（日期/点位待核实）</i>" : "")
        };
      }).filter(Boolean);
    const chart = echarts.init(chartDiv, null, { renderer: "svg" });
    chart.setOption(Object.assign(baseChartOpts(), {
      tooltip: {
        trigger: "axis", confine: true,
        formatter: params => {
          const p = params.find(x => x.seriesType === "line");
          let t = p ? `${p.axisValue}<br>收盘 ${fmt(p.data)}` : "";
          return t;
        }
      },
      dataZoom: [{ type: "inside" }, { type: "slider", height: 16, bottom: 4 }],
      xAxis: { type: "category", data: rows.map(r => r.date),
               axisLabel: { color: AXIS }, axisLine: { lineStyle: { color: GRIDLINE } } },
      yAxis: { type: "value", scale: true,
               axisLabel: { color: AXIS }, splitLine: { lineStyle: { color: GRIDLINE } } },
      series: [{
        type: "line", data: rows.map(r => r.close), showSymbol: false,
        lineStyle: { color: INKLINE, width: 1.4 },
        markPoint: {
          symbol: "circle", symbolSize: 11,
          data: markData,
          tooltip: { formatter: p => p.data.tooltipText }
        }
      }]
    }));
  }
}

/* ---------- 事件研究结果 ---------- */
async function renderStudy(assessment) {
  const res = await fetchJSON("data/event_study_results.json");
  if (!res) return;
  const wrap = document.getElementById("study");
  wrap.innerHTML = "";
  const horizons = Object.keys(res.summary || {});
  const historyModel = (assessment && assessment.models || []).find(m => m.id === "history");
  const plain = el("div", "study-plain");
  const twenty = res.summary["20"];
  const wins20 = twenty ? Math.round(twenty.win_rate * twenty.n) : 0;
  plain.innerHTML = `<strong>先说人话：</strong>“20日胜率85.7%”只表示过去${twenty ? twenty.n : 0}次A股样本中，` +
    `${wins20}次在20个交易日后上涨；<strong>不是</strong>说明下一次有85.7%的确定上涨概率。` +
    `样本只有7次，一个反例就会让比例改变14.3个百分点。60个交易日大约3个月，是当前样本里最弱的窗口。`;
  wrap.append(plain);
  const sum = el("table", "study-table");
  const intervalCells = horizons.map(h => {
    const range = historyModel && historyModel.metrics[h] && historyModel.metrics[h].wilson95;
    return `<td>${range && range[0] !== null ? `${(range[0] * 100).toFixed(1)}%–${(range[1] * 100).toFixed(1)}%` : "—"}</td>`;
  }).join("");
  sum.innerHTML = "<caption>仅使用中国大陆A股事件。95%区间很宽，直观说明样本太少。</caption>" +
    "<tr><th>持有期</th>" + horizons.map(h => `<th>${h}日</th>`).join("") + "</tr>" +
    "<tr><td>胜率(样本数)</td>" + horizons.map(h => {
      const s = res.summary[h];
      return `<td>${s.win_rate === null ? "—" : (s.win_rate * 100).toFixed(1) + "%"} (n=${s.n})</td>`;
    }).join("") + `</tr><tr><td>不确定范围(95%)</td>${intervalCells}</tr>`;
  wrap.append(sum);

  const tbl = el("table", "study-table");
  const hasPendingVerification = res.buy_events.some(ev => ev.verify);
  let rows = "<tr><th>干预日</th><th>市场</th>" +
    horizons.map(h => `<th>+${h}日</th>`).join("") +
    "<th>之后最深还跌多少</th><th>多久后最低</th></tr>";
  for (const ev of res.buy_events) {
    rows += `<tr><td>${ev.date}${ev.verify ? " *" : ""} ${ev.note}</td><td>${ev.market}</td>` +
      horizons.map(h => {
        const r = ev.returns[h];
        const cls = r === null ? "" : (r > 0 ? "pos" : "neg");
        return `<td class="${cls}">${pct(r)}</td>`;
      }).join("") +
      `<td class="neg">${pct(ev.max_drawdown)}</td><td>${ev.days_to_trough ?? "—"}</td></tr>`;
  }
  const verificationNote = hasPendingVerification
    ? "* 带星号记录的日期/点位待核实。"
    : "样本日期与点位已按来源复核。";
  tbl.innerHTML = rows + `<caption>${verificationNote}${res.caveats}</caption>`;
  wrap.append(tbl);
}

/* ---------- 每日解读 ---------- */
function humanizeComment(md) {
  return md
    .replace(/倒挂\/减持确认/g, "历史参考线提示（需要定期报告确认）")
    .replace(/持续倒挂，确认减持下限/g, "当前仍低于历史参考线，差额")
    .replace(/新出现倒挂/g, "首次低于历史参考线")
    .replace(/倒挂差额/g, "低于历史参考线的差额")
    .replace(/倒挂/g, "低于历史参考线")
    .replace(/减持下限/g, "待确认差额");
}
async function renderComments() {
  const manifest = await fetchJSON("data/comments/manifest.json");
  if (!manifest || !manifest.length) return;
  const wrap = document.getElementById("comments");
  wrap.innerHTML = "";
  for (const date of manifest.slice(0, 10)) {
    const md = await fetchText(`data/comments/${date}.md`);
    if (!md) continue;
    const html = humanizeComment(md)
      .replace(/^# (.*)$/gm, "<h3>$1</h3>")
      .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
      .replace(/^- (.*)$/gm, "<li>$1</li>")
      .replace(/(<li>[\s\S]*?<\/li>)(?![\s\S]*<li>)/, "<ul>$1</ul>")
      .split(/\n{2,}/).map(p => /<h3|<ul|<li/.test(p) ? p : `<p>${p}</p>`).join("");
    wrap.append(el("article", "comment", html));
  }
}

(async function init() {
  const conf = await fetchJSON("data/baselines.json");
  if (!conf) {
    document.getElementById("statusline").textContent =
      "无法读取 data/baselines.json —— 请通过 HTTP 服务访问本页（python3 -m http.server），而非直接双击打开文件。";
    return;
  }
  await renderEtfSection(conf);
  const assessment = await fetchJSON("data/daily_assessment.json");
  renderAssessment(assessment);
  await renderIndexSection();
  await renderStudy(assessment);
  await renderComments();
})();
