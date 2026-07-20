/* 平准基金观测站 前端逻辑
   纯静态: 读取 data/ 下的 JSON 渲染。本地预览: python3 -m http.server */
"use strict";

const INDEX_META = {
  "000001": "上证指数",
  "399001": "深证成指",
  "000688": "科创50"
};
const EVENT_STYLE = {
  buy:    { color: "#1f5fbf", label: "平准买入" },
  policy: { color: "#5b48b0", label: "政策底" },
  trough: { color: "#d23b3b", label: "恐慌底" },
  sell:   { color: "#d97b1f", label: "减持" }
};
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
      `<span>${etf.name} <code>${etf.code}</code></span><span class="badge"></span>`);
    const chartDiv = el("div", "chart");
    box.append(title, chartDiv);
    grid.append(box);
    if (!rows || !rows.length) {
      chartDiv.outerHTML = '<p class="empty" style="margin:12px">暂无份额数据，等待抓取脚本首次运行。</p>';
      continue;
    }
    const last = rows[rows.length - 1];
    if (!latestDate || last.date > latestDate) latestDate = last.date;
    const base = etf.huijin_shares_yi;
    const isInv = base !== null && last.total_shares_yi < base;
    if (isInv) {
      inverted++;
      title.querySelector(".badge").textContent =
        `倒挂 −${(base - last.total_shares_yi).toFixed(1)} 亿份`;
    }
    if (base !== null) { coreSum += last.total_shares_yi; coreCount++; }

    // 倒挂时间区间(签名元素: 红色色带)
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
      series: [{
        type: "line", data: rows.map(r => r.total_shares_yi),
        lineStyle: { color: INKLINE, width: 2 }, itemStyle: { color: INKLINE },
        symbolSize: 5,
        markLine: base === null ? undefined : {
          silent: true, symbol: "none",
          lineStyle: { color: "#1f5fbf", type: "dashed" },
          label: { formatter: `汇金基线 ${base}`, color: "#1f5fbf", position: "insideEndTop" },
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
    mk("出现倒挂的标的", String(inverted), inverted > 0),
    mk("核心宽基合计份额", coreCount ? fmt(coreSum, 1) + " 亿份" : "—"),
    mk("基线截止", conf.baseline_date)
  );
  document.getElementById("statusline").textContent =
    `最新份额日期 ${latestDate || "—"} · 基线来源 ${conf.updated_from}（${conf.baseline_date}）` +
    (inverted ? ` · ${inverted} 只标的处于倒挂(确认减持)状态` : " · 未见倒挂");

  // 基线过期提醒(>120天)
  const ageDays = (Date.now() - new Date(conf.baseline_date)) / 864e5;
  if (ageDays > 120) {
    const w = document.getElementById("baseline-warn");
    w.hidden = false;
    w.textContent = `提醒：汇金持仓基线已 ${Math.floor(ageDays)} 天未更新，` +
      "请在最新基金定期报告披露后更新 data/baselines.json，否则倒挂判断会失真。";
  }
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
async function renderStudy() {
  const res = await fetchJSON("data/event_study_results.json");
  if (!res) return;
  const wrap = document.getElementById("study");
  wrap.innerHTML = "";
  const horizons = Object.keys(res.summary || {});
  const sum = el("table", "study-table");
  sum.innerHTML = "<caption>买入干预后持有N个交易日的历史胜率（收益>0的比例）。" +
    "样本量小，仅为条件分布描述。</caption>" +
    "<tr><th>持有期</th>" + horizons.map(h => `<th>${h}日</th>`).join("") + "</tr>" +
    "<tr><td>胜率(样本数)</td>" + horizons.map(h => {
      const s = res.summary[h];
      return `<td>${s.win_rate === null ? "—" : (s.win_rate * 100).toFixed(0) + "%"} (n=${s.n})</td>`;
    }).join("") + "</tr>";
  wrap.append(sum);

  const tbl = el("table", "study-table");
  const hasPendingVerification = res.buy_events.some(ev => ev.verify);
  let rows = "<tr><th>干预日</th><th>市场</th>" +
    horizons.map(h => `<th>+${h}日</th>`).join("") +
    "<th>其后最大回撤</th><th>至底天数</th></tr>";
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
async function renderComments() {
  const manifest = await fetchJSON("data/comments/manifest.json");
  if (!manifest || !manifest.length) return;
  const wrap = document.getElementById("comments");
  wrap.innerHTML = "";
  for (const date of manifest.slice(0, 10)) {
    const md = await fetchText(`data/comments/${date}.md`);
    if (!md) continue;
    const html = md
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
  await renderIndexSection();
  await renderStudy();
  await renderComments();
})();
