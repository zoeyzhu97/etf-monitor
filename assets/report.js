"use strict";

async function reportJSON(path) {
  try {
    const response = await fetch(path, { cache: "no-store" });
    return response.ok ? await response.json() : null;
  } catch (error) { return null; }
}

const reportPct = value => value === null || value === undefined
  ? "—" : `${(Number(value) * 100).toFixed(1)}%`;

(async function renderReport() {
  const [assessment, study] = await Promise.all([
    reportJSON("data/daily_assessment.json"),
    reportJSON("data/event_study_results.json")
  ]);
  const summary = document.getElementById("report-summary");
  if (!assessment || assessment.market_scope !== "CN") {
    summary.innerHTML = '<p class="empty">没有找到纯中国大陆A股口径的评估，报告停止展示。</p>';
    return;
  }
  document.getElementById("report-status").textContent =
    `报告数据截至 ${assessment.as_of} · 仅中国大陆A股 · 每日自动更新`;
  summary.innerHTML = `<article class="verdict ${assessment.verdict.state}">` +
    `<p class="verdict-k">最新结论</p><h3>${assessment.verdict.label}</h3>` +
    `<p>${assessment.verdict.plain}</p><p class="rule">四模型投票：偏暖${assessment.verdict.counts.support}、` +
    `警惕${assessment.verdict.counts.risk}、中性${assessment.verdict.counts.neutral}。${assessment.verdict.rule}。</p></article>` +
    `<div class="two-sided-grid"><article class="side-card buy"><h3>${assessment.two_sided.buy_side.label}</h3><ul>` +
    assessment.two_sided.buy_side.checks.map(item => `<li class="${item.met ? "met" : "not-met"}">${item.met ? "✓" : "○"} ${item.label}</li>`).join("") +
    `</ul><p class="term">${assessment.two_sided.buy_side.meaning}</p></article>` +
    `<article class="side-card sell"><h3>${assessment.two_sided.sell_side.label}</h3><ul>` +
    assessment.two_sided.sell_side.checks.map(item => `<li class="${item.met ? "met" : "not-met"}">${item.met ? "✓" : "○"} ${item.label}</li>`).join("") +
    `</ul><p class="term">${assessment.two_sided.sell_side.meaning}</p></article></div>` +
    `<p class="history-boundary">${assessment.two_sided.history_boundary}</p>` +
    `<article class="action-guide"><p class="verdict-k">通用行动框架</p>` +
    `<h3>${assessment.action_guide.level}</h3><ul>` +
    assessment.action_guide.checklist.map(item => `<li>${item}</li>`).join("") +
    `</ul><p class="boundary">${assessment.action_guide.boundary}</p></article>`;

  const history = document.getElementById("report-history");
  if (!study || JSON.stringify(study.markets_included) !== JSON.stringify(["CN"])) {
    history.innerHTML = "<p>历史结果不是纯A股口径，已停止展示。</p>";
    return;
  }
  const historyModel = assessment.models.find(model => model.id === "history");
  const horizons = Object.keys(study.summary || {});
  history.innerHTML = `<div class="table-scroll"><table class="study-table">` +
    `<tr><th>干预后</th>${horizons.map(h => `<th>${h}日</th>`).join("")}</tr>` +
    `<tr><td>上涨次数/样本</td>${horizons.map(h => {
      const item = study.summary[h];
      return `<td>${Math.round(item.win_rate * item.n)}/${item.n}</td>`;
    }).join("")}</tr>` +
    `<tr><td>表面胜率</td>${horizons.map(h => `<td>${reportPct(study.summary[h].win_rate)}</td>`).join("")}</tr>` +
    `<tr><td>95%不确定范围</td>${horizons.map(h => {
      const range = historyModel.metrics[h].wilson95;
      return `<td>${reportPct(range[0])}–${reportPct(range[1])}</td>`;
    }).join("")}</tr></table></div>`;
})();
