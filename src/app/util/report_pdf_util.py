import io
from datetime import datetime, timedelta, timezone
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from pathlib import Path

from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.schema.report_ai_schema import ReportAiResult

# 한글 폰트
# data/fonts/NanumGothic-Regular.ttf 가 있으면 PDF 안에 글꼴을 넣어서(임베드) 어느 컴퓨터에서나 똑같이 보이게 한다.
# 파일이 없으면 reportlab 내장 한글 글꼴을 쓴다 (PDF 뷰어에 따라 글자가 다르게 보이거나 안 보일 수 있음).
FONT_PATH = Path(__file__).resolve().parent.parent / "data" / "fonts" / "NanumGothic-Regular.ttf"
if FONT_PATH.exists():
    FONT = "NanumGothic"
    pdfmetrics.registerFont(TTFont(FONT, str(FONT_PATH)))
else:
    FONT = "HYGothic-Medium"
    pdfmetrics.registerFont(UnicodeCIDFont(FONT))

KST = timezone(timedelta(hours=9))

NAVY = colors.HexColor("#14213D")
MINT = colors.HexColor("#1F8A7A")
GRAY = colors.HexColor("#6B7280")
LINE = colors.HexColor("#E5E7EB")
LIGHT = colors.HexColor("#F3F6F8")

ITEM_LABELS = {
    "item_differentiation": "사업 아이템 및 차별성",
    "market_customer": "시장성 및 고객 분석",
    "business_model_profit": "사업 모델 및 수익성",
    "marketing": "마케팅 전략",
    "operation_plan": "운영 및 실행 계획",
    "risk_management": "위험 관리",
}

STYLES = {
    "title": ParagraphStyle("title", fontName=FONT, fontSize=20, leading=28, textColor=NAVY),
    "meta": ParagraphStyle("meta", fontName=FONT, fontSize=9, leading=14, textColor=GRAY),
    "h2": ParagraphStyle("h2", fontName=FONT, fontSize=13, leading=20, textColor=NAVY, spaceBefore=14, spaceAfter=6),
    "h3": ParagraphStyle("h3", fontName=FONT, fontSize=11, leading=17, textColor=MINT, spaceBefore=8, spaceAfter=3),
    "body": ParagraphStyle("body", fontName=FONT, fontSize=9.5, leading=15, alignment=TA_LEFT),
    "small": ParagraphStyle("small", fontName=FONT, fontSize=8.5, leading=13, textColor=GRAY),
    "cell": ParagraphStyle("cell", fontName=FONT, fontSize=8.5, leading=12.5),
    "cell_head": ParagraphStyle("cell_head", fontName=FONT, fontSize=8.5, leading=12.5, textColor=colors.white),
}


def _p(text, style="body"):
    return Paragraph(escape(str(text or "")).replace("\n", "<br/>"), STYLES[style])


def _bullets(lines, style="body"):
    return [_p(f"· {line}", style) for line in lines if line]


def _table(header, rows, col_widths):
    data = [[_p(h, "cell_head") for h in header]] + [[_p(c, "cell") for c in row] for row in rows]
    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("GRID", (0, 0), (-1, -1), 0.5, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
    ]))
    return table


# Gemini 검토 결과 → 검토 보고서 PDF (bytes)
def build_report_pdf(result: ReportAiResult, source_file_name: str) -> bytes:
    llm = result.llm
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm, topMargin=18 * mm, bottomMargin=18 * mm,
        title="StartFit 기획서 AI 검토 보고서",
    )
    width = A4[0] - 36 * mm
    grades = {g.item_key: g.grade for g in result.grades}
    created = datetime.now(KST).strftime("%Y.%m.%d %H:%M")

    story = [
        _p("StartFit 기획서 AI 검토 보고서", "title"),
        _p(f"검토 파일: {source_file_name}  ·  검토 일시: {created}  ·  프롬프트 {result.prompt_version}", "meta"),
        Spacer(1, 6 * mm),
    ]

    # 1. 개요
    story += [_p("1. 개요", "h2")]
    if llm.business_item:
        story += [_p(f"사업 아이템: {llm.business_item}")]
    if llm.startup_type:
        story += [_p(f"창업 유형: {llm.startup_type}")]
    if llm.summary:
        story += [Spacer(1, 2 * mm), _p(llm.summary)]
    if llm.key_strengths:
        story += [_p("핵심 강점", "h3")] + _bullets(llm.key_strengths)

    # 2. 항목별 평가 요약
    if llm.items:
        rows = [
            [ITEM_LABELS.get(item.item_key, item.item_key), grades.get(item.item_key, "-"), item.evidence.judgment]
            for item in llm.items
        ]
        story += [_p("2. 항목별 평가", "h2"),
                  _table(["평가 항목", "등급", "평가 의견"], rows, [width * 0.26, width * 0.12, width * 0.62])]

        # 항목별 상세
        for item in llm.items:
            story += [_p(f"{ITEM_LABELS.get(item.item_key, item.item_key)} · {grades.get(item.item_key, '-')}", "h3")]
            if item.evidence.quote:
                page = f" (p.{item.evidence.page})" if item.evidence.page else ""
                story += [_p(f"원문 근거{page}: “{item.evidence.quote}”", "small")]
            if item.strengths:
                story += [_p("잘된 점")] + _bullets(item.strengths)
            if item.gaps:
                story += [_p("보완할 점")] + _bullets(item.gaps)

    # 3. 재무 검산
    if result.finance_checks:
        rows = [[c.label, c.original or "-", c.formula or "-", c.result] for c in result.finance_checks]
        story += [_p("3. 재무 수치 검산", "h2"),
                  _p("기획서에 적힌 수치를 다시 계산해 맞는지 확인한 결과입니다.", "small"),
                  Spacer(1, 2 * mm),
                  _table(["구분", "원문 수치", "검산", "결과"], rows,
                         [width * 0.2, width * 0.22, width * 0.43, width * 0.15])]

    # 4. 개선 제안
    if llm.suggestions:
        rows = [[s.priority, s.problem, s.action] for s in llm.suggestions]
        story += [_p("4. 개선 제안", "h2"),
                  _table(["우선순위", "문제", "개선 방법"], rows, [width * 0.13, width * 0.35, width * 0.52])]

    # 5. 최종 의견
    if llm.final_opinion:
        story += [_p("5. 최종 의견", "h2"), _p(llm.final_opinion)]

    story += [Spacer(1, 8 * mm),
              _p("이 보고서는 AI가 사업계획서의 완성도를 검토한 참고 자료이며, 창업 성공이나 지원사업 선정 결과를 보장하지 않습니다.", "small")]

    doc.build(story)
    return buffer.getvalue()
