# -*- coding: utf-8 -*-
"""根据站点最新JSON生成可转发的中文评估指南PDF。"""
import datetime as dt
import html
import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (KeepTogether, PageBreak, Paragraph,
                                SimpleDocTemplate, Spacer, Table, TableStyle)


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "pdf" / "etf-monitor-assessment-guide.pdf"
FONT_REGULAR = "/System/Library/Fonts/STHeiti Light.ttc"
FONT_BOLD = "/System/Library/Fonts/STHeiti Medium.ttc"

INK = colors.HexColor("#17181c")
MUTED = colors.HexColor("#6f6d68")
LINE = colors.HexColor("#dedbd3")
PAPER = colors.HexColor("#f7f6f2")
BLUE = colors.HexColor("#1f5fbf")
RED = colors.HexColor("#c43c3c")
ORANGE = colors.HexColor("#c5741c")
VIOLET = colors.HexColor("#5b48b0")


def load_json(relative_path):
    with (ROOT / relative_path).open(encoding="utf-8") as handle:
        return json.load(handle)


def safe(value):
    return html.escape(str(value))


def register_fonts():
    pdfmetrics.registerFont(TTFont("GuideSans", FONT_REGULAR,
                                   subfontIndex=0))
    pdfmetrics.registerFont(TTFont("GuideBold", FONT_BOLD,
                                   subfontIndex=0))


def make_styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "GuideTitle", parent=base["Title"], fontName="GuideBold",
            fontSize=25, leading=32, textColor=INK, alignment=TA_LEFT,
            spaceAfter=5 * mm),
        "subtitle": ParagraphStyle(
            "GuideSubtitle", parent=base["Normal"], fontName="GuideSans",
            fontSize=11, leading=18, textColor=MUTED, spaceAfter=7 * mm),
        "h1": ParagraphStyle(
            "GuideH1", parent=base["Heading1"], fontName="GuideBold",
            fontSize=16, leading=22, textColor=INK, spaceBefore=3 * mm,
            spaceAfter=3 * mm),
        "h2": ParagraphStyle(
            "GuideH2", parent=base["Heading2"], fontName="GuideBold",
            fontSize=11.5, leading=16, textColor=INK, spaceBefore=2 * mm,
            spaceAfter=1.5 * mm),
        "body": ParagraphStyle(
            "GuideBody", parent=base["BodyText"], fontName="GuideSans",
            fontSize=9.5, leading=15, textColor=INK, spaceAfter=2 * mm),
        "small": ParagraphStyle(
            "GuideSmall", parent=base["BodyText"], fontName="GuideSans",
            fontSize=8, leading=12, textColor=MUTED, spaceAfter=1 * mm),
        "card_label": ParagraphStyle(
            "CardLabel", parent=base["Normal"], fontName="GuideSans",
            fontSize=8.5, leading=12, textColor=MUTED),
        "card_value": ParagraphStyle(
            "CardValue", parent=base["Normal"], fontName="GuideBold",
            fontSize=22, leading=27, textColor=INK),
        "card_meta": ParagraphStyle(
            "CardMeta", parent=base["Normal"], fontName="GuideSans",
            fontSize=8, leading=11, textColor=MUTED),
        "table_head": ParagraphStyle(
            "TableHead", parent=base["Normal"], fontName="GuideBold",
            fontSize=8.5, leading=12, textColor=colors.white,
            alignment=TA_LEFT),
        "table": ParagraphStyle(
            "TableBody", parent=base["Normal"], fontName="GuideSans",
            fontSize=8.2, leading=12, textColor=INK),
        "table_bold": ParagraphStyle(
            "TableBold", parent=base["Normal"], fontName="GuideBold",
            fontSize=8.2, leading=12, textColor=INK),
        "callout": ParagraphStyle(
            "Callout", parent=base["BodyText"], fontName="GuideBold",
            fontSize=11, leading=17, textColor=INK, spaceAfter=1 * mm),
        "center_small": ParagraphStyle(
            "CenterSmall", parent=base["Normal"], fontName="GuideSans",
            fontSize=8, leading=11, textColor=MUTED, alignment=TA_CENTER),
    }


def paragraph(text, style):
    return Paragraph(safe(text), style)


def score_card(label, item, color, styles):
    content = [
        paragraph(label, styles["card_label"]),
        Paragraph(f'<font color="{color.hexval()}">{item["score"]}</font>'
                  f'<font size="9" color="#6f6d68"> /100</font>',
                  styles["card_value"]),
        paragraph(item["level"], styles["card_meta"]),
    ]
    table = Table([[content]], colWidths=[51 * mm], rowHeights=[31 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("BOX", (0, 0), (-1, -1), 0.8, color),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4 * mm),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 2 * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2 * mm),
    ]))
    return table


def component_table(title, item, color, styles):
    rows = [[Paragraph(safe(title), styles["table_head"]),
             Paragraph("得分", styles["table_head"]),
             Paragraph("当前数据", styles["table_head"])]]
    for component in item.get("components", []):
        rows.append([
            paragraph(component["label"], styles["table"]),
            paragraph(f'{component["points"]}/{component["max"]}',
                      styles["table_bold"]),
            paragraph(component["detail"], styles["table"]),
        ])
    table = Table(rows, colWidths=[100 * mm, 22 * mm, 50 * mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), color),
        ("GRID", (0, 0), (-1, -1), 0.45, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2.5 * mm),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2.5 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 2 * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2 * mm),
        ("BACKGROUND", (0, 1), (-1, -1), colors.white),
    ]))
    return table


def alert_card(title, body, color, styles):
    content = [paragraph(title, styles["h2"]), paragraph(body, styles["body"])]
    table = Table([[content]], colWidths=[83 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("BOX", (0, 0), (-1, -1), 0.6, LINE),
        ("LINEABOVE", (0, 0), (-1, 0), 2.5, color),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4 * mm),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 3 * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3 * mm),
    ]))
    return table


def history_table(study, history_model, styles):
    horizons = ["20", "60", "120", "250"]
    rows = [[paragraph("持有期", styles["table_head"])] +
            [paragraph(f"{item}日", styles["table_head"])
             for item in horizons]]
    rows.append([paragraph("上涨比例", styles["table_bold"])] + [
        paragraph(f'{study["summary"][item]["win_rate"] * 100:.1f}% '
                  f'(n={study["summary"][item]["n"]})', styles["table"])
        for item in horizons
    ])
    rows.append([paragraph("95%不确定范围", styles["table_bold"])] + [
        paragraph(f'{history_model["metrics"][item]["wilson95"][0] * 100:.1f}% - '
                  f'{history_model["metrics"][item]["wilson95"][1] * 100:.1f}%',
                  styles["table"])
        for item in horizons
    ])
    table = Table(rows, colWidths=[36 * mm] + [34 * mm] * 4, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BLUE),
        ("GRID", (0, 0), (-1, -1), 0.45, LINE),
        ("BACKGROUND", (0, 1), (-1, -1), colors.white),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2 * mm),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 2.2 * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2 * mm),
    ]))
    return table


def page_decor(canvas, document):
    canvas.saveState()
    width, height = A4
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.5)
    canvas.line(18 * mm, 16 * mm, width - 18 * mm, 16 * mm)
    canvas.setFont("GuideSans", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(18 * mm, 10 * mm, "A股国家队ETF观察 · 评估指南")
    canvas.drawRightString(width - 18 * mm, 10 * mm,
                           f"第 {document.page} 页")
    if document.page > 1:
        canvas.setFont("GuideBold", 8)
        canvas.setFillColor(INK)
        canvas.drawString(18 * mm, height - 12 * mm, "ETF MONITOR")
        canvas.setStrokeColor(INK)
        canvas.line(18 * mm, height - 15 * mm, width - 18 * mm,
                    height - 15 * mm)
    canvas.restoreState()


def build_pdf():
    register_fonts()
    styles = make_styles()
    assessment = load_json("data/daily_assessment.json")
    study = load_json("data/event_study_results.json")
    score = assessment["scorecard"]
    history_model = next(item for item in assessment["models"]
                         if item["id"] == "history")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    document = SimpleDocTemplate(
        str(OUTPUT), pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm,
        topMargin=21 * mm, bottomMargin=21 * mm,
        title="A股国家队ETF观察 - 评估指南",
        author="ETF Monitor",
        subject="公开数据风险与修复评分说明",
    )

    story = []
    story.append(Paragraph("A股国家队ETF观察", styles["title"]))
    story.append(Paragraph("评估指南与当前信号", ParagraphStyle(
        "CoverSub", parent=styles["h1"], fontSize=20, leading=26,
        textColor=BLUE, spaceAfter=3 * mm)))
    story.append(paragraph(
        f'数据截至 {assessment.get("as_of") or "-"} · PDF生成于 '
        f'{dt.date.today().isoformat()}', styles["subtitle"]))

    cards = Table([[
        score_card("风险/卖出警报", score["market_risk"], RED, styles),
        score_card("修复/买入准备度", score["repair_readiness"], BLUE, styles),
        score_card("数据可信度", score["data_confidence"], VIOLET, styles),
    ]], colWidths=[57 * mm] * 3)
    cards.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3 * mm),
    ]))
    story.extend([cards, Spacer(1, 7 * mm)])

    signal = score["general_signal"]
    callout = Table([[
        [paragraph("当前提示", styles["small"]),
         paragraph(signal["headline"], styles["callout"]),
         paragraph(signal["guidance"], styles["body"])]
    ]], colWidths=[172 * mm])
    callout.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("BOX", (0, 0), (-1, -1), 0.7, LINE),
        ("LINEBEFORE", (0, 0), (0, -1), 3.5, RED),
        ("LEFTPADDING", (0, 0), (-1, -1), 5 * mm),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 4 * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4 * mm),
    ]))
    story.extend([callout, Spacer(1, 6 * mm)])

    story.append(paragraph("这份指南回答什么？", styles["h1"]))
    story.append(paragraph(
        "它把ETF份额、指数趋势、恐慌压力和数据质量放在同一张表里，"
        "帮助判断当前更接近风险释放、等待确认，还是右侧修复。它不预测最低点，"
        "也不把ETF总份额变化直接等同于中央汇金的每日买卖。", styles["body"]))
    story.append(paragraph("怎样使用三个分数？", styles["h1"]))
    usage_rows = [
        ["风险/卖出警报", "分数越高，连续流出、弱趋势与恐慌同时出现得越完整。高分意味着先检查风险暴露，不等于所有人都必须卖。"],
        ["修复/买入准备度", "分数越高，连续流入、均线修复与压力缓和越完整。高分意味着可按既定计划分批验证，不等于保证上涨。"],
        ["数据可信度", "核对交易所数据、最新日期和持仓参考线的新鲜程度。数据分偏低时，应先修数据，再加强交易判断。"],
    ]
    for title, body in usage_rows:
        story.append(KeepTogether([
            paragraph(title, styles["h2"]), paragraph(body, styles["body"])
        ]))
    story.append(Spacer(1, 2 * mm))
    story.append(paragraph(signal["boundary"], styles["small"]))

    story.append(PageBreak())
    story.append(paragraph("评分规则与当前得分", styles["h1"]))
    story.append(paragraph(
        "风险分和修复分各由三项基础条件组成，每项最高25分；三项同时满足时再加25分。"
        "连续是指最近3个相邻更新间隔，而不是只看一天。", styles["body"]))
    story.extend([
        component_table("风险/卖出警报", score["market_risk"], RED, styles),
        Spacer(1, 5 * mm),
        component_table("修复/买入准备度", score["repair_readiness"], BLUE, styles),
        Spacer(1, 5 * mm),
        component_table("数据可信度", score["data_confidence"], VIOLET, styles),
        Spacer(1, 4 * mm),
    ])
    story.append(paragraph(
        "当前读数的关键矛盾：ETF连续增加，显示有承接；但三个指数均处于弱趋势且恐慌压力仍高。"
        "因此页面给出偏防守，而不是直接给出买入。持仓参考线已经超过120天未更新，"
        "这会降低关于国家队持仓变化的判断强度。", styles["body"]))

    story.append(PageBreak())
    story.append(paragraph("什么情况会触发提醒？", styles["h1"]))
    alert_grid = Table([
        [alert_card(
            "高风险组合", "多数ETF连续3个更新间隔份额减少，同时至少两个指数跌破20日和60日均线，且恐慌压力达到门槛。三项同现时风险分额外增加25分。",
            RED, styles),
         alert_card(
             "修复组合", "多数ETF连续3个更新间隔份额增加，同时至少两个指数站上20日和60日均线，且波动与回撤趋于平稳。三项同现时修复分额外增加25分。",
             BLUE, styles)],
        [alert_card(
            "数据警报", "最新记录未核验、日期滞后，或持仓参考线已超过四个月未更新时，数据可信度下降。此时不应把结论说得更确定。",
            ORANGE, styles),
         alert_card(
             "不能误读", "指数大跌时ETF份额激增可能表示承接、套利或机构配置，也可能与稳定行动重合；它不是当天必然见底的证据。",
             VIOLET, styles)],
    ], colWidths=[86 * mm, 86 * mm])
    alert_grid.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4 * mm),
    ]))
    story.extend([alert_grid, Spacer(1, 3 * mm)])
    story.append(paragraph("几个容易混淆的概念", styles["h1"]))
    concepts = [
        ("政策底与恐慌底", "政策底是政策行动或公开增持出现的时点；恐慌底是价格在抛售中形成、通常只能事后确认的低点。政策可能先于、同日或晚于价格低点，没有固定顺序。"),
        ("救市与抄底", "救市强调稳定流动性、信心和市场功能；抄底强调在较低价格承接。一次ETF增持可以同时具有两种特征，但公开日线无法读取真实动机。"),
        ("左侧与右侧", "趋势仍弱时提前承接属于左侧，价格可能更低但误判风险更高；重新站稳均线后再确认属于右侧，可能更稳但也会更晚。"),
        ("份额与持仓", "ETF总份额是全市场投资者合计，不是中央汇金的每日持仓。只有基金定期报告能离散确认特定持有人的持仓变化。"),
    ]
    for title, body in concepts:
        story.append(KeepTogether([
            paragraph(title, styles["h2"]), paragraph(body, styles["body"])
        ]))

    story.append(PageBreak())
    story.append(paragraph("历史统计怎样理解？", styles["h1"]))
    story.append(history_table(study, history_model, styles))
    story.append(Spacer(1, 4 * mm))
    story.append(paragraph(
        "20日85.7%表示7次样本中有6次在20个交易日后上涨，不表示下一次有85.7%的确定概率。"
        "一个反例就会让比例变化约14个百分点，95%不确定范围也很宽。60日是当前样本中最弱的窗口，"
        "但样本不足以证明这是稳定规律。", styles["body"]))

    story.append(paragraph("网页与PDF分别有什么用？", styles["h1"]))
    comparison = Table([
        [paragraph("每日网页", styles["table_head"]),
         paragraph("这份PDF", styles["table_head"])],
        [paragraph("每天自动更新份额、指数、评分和解读，适合查看最新状态。", styles["table"]),
         paragraph("解释评分方法和风险边界，适合转发、留存和讨论。PDF中的当前分数不会自动刷新。", styles["table"])],
    ], colWidths=[86 * mm, 86 * mm])
    comparison.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), INK),
        ("BACKGROUND", (0, 1), (-1, -1), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3 * mm),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5 * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5 * mm),
    ]))
    story.extend([comparison, Spacer(1, 5 * mm)])

    story.append(paragraph("查看最新数据", styles["h1"]))
    story.append(Paragraph(
        '<link href="https://zoeyzhu97.github.io/etf-monitor/" color="#1f5fbf">'
        'https://zoeyzhu97.github.io/etf-monitor/</link>', styles["body"]))
    story.append(paragraph(
        "主要数据来源：上海证券交易所、深圳证券交易所、基金定期报告和中央汇金公开公告。"
        "官方源失败时的兜底数据会在网页上标记为未核验。", styles["body"]))
    disclaimer = Table([[
        [paragraph("重要说明", styles["h2"]),
         paragraph(
             "本指南只根据公开市场数据提供通用观察和风险提示。它不了解读者的财务状况、资金用途、"
             "投资期限和承受亏损能力，因此不构成个性化买卖指令、收益承诺或投资建议。",
             styles["body"])]
    ]], colWidths=[172 * mm])
    disclaimer.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PAPER),
        ("BOX", (0, 0), (-1, -1), 0.7, ORANGE),
        ("LEFTPADDING", (0, 0), (-1, -1), 4 * mm),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 3 * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3 * mm),
    ]))
    story.append(disclaimer)

    document.build(story, onFirstPage=page_decor, onLaterPages=page_decor)
    return OUTPUT


if __name__ == "__main__":
    result = build_pdf()
    print(result)
