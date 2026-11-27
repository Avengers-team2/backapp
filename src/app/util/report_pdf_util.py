import io
import unicodedata
from datetime import datetime, timedelta, timezone
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas as rl_canvas
from pathlib import Path

from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.schema.report_ai_schema import ReportAiResult
from app.util.report_score_util import item_score, total_grade

# 한글 폰트
# data/report_ai/fonts 의 나눔고딕(Regular/Bold)을 PDF 안에 넣어서(임베드) 어느 컴퓨터에서나 똑같이 보이게 한다.
# 파일이 없으면 reportlab 내장 한글 글꼴을 쓴다 (PDF 뷰어에 따라 글자가 다르게 보이거나 안 보일 수 있음).
FONT_DIR = Path(__file__).resolve().parent.parent / "data" / "report_ai" / "fonts"
FONT_REGULAR_PATH = FONT_DIR / "NanumGothic-Regular.ttf"
FONT_BOLD_PATH = FONT_DIR / "NanumGothic-Bold.ttf"

if FONT_REGULAR_PATH.exists():
    FONT = "NanumGothic"
    pdfmetrics.registerFont(TTFont(FONT, str(FONT_REGULAR_PATH)))
    if FONT_BOLD_PATH.exists():
        FONT_BOLD = "NanumGothic-Bold"
        pdfmetrics.registerFont(TTFont(FONT_BOLD, str(FONT_BOLD_PATH)))
    else:
        FONT_BOLD = FONT
else:
    FONT = FONT_BOLD = "HYGothic-Medium"
    pdfmetrics.registerFont(UnicodeCIDFont(FONT))

KST = timezone(timedelta(hours=9))

NAVY = colors.HexColor("#14213D")
MINT = colors.HexColor("#1F8A7A")
GRAY = colors.HexColor("#6B7280")
LINE = colors.HexColor("#E5E7EB")
LIGHT = colors.HexColor("#F3F6F8")
MINT_LIGHT = colors.HexColor("#E8F5F2")

# 등급·결과별 글자색 (한눈에 보기, 표에서 사용)
GRADE_COLORS = {
    "우수": "#1F8A7A",
    "보통": "#14213D",
    "미흡": "#C2410C",
    "매우 미흡": "#B91C1C",
}
RESULT_COLORS = {
    "일치": "#1F8A7A",
    "불일치": "#B91C1C",
    "근거 누락": "#C2410C",
}

ITEM_LABELS = {
    "item_differentiation": "사업 아이템 및 차별성",
    "market_customer": "시장성 및 고객 분석",
    "business_model_profit": "사업 모델 및 수익성",
    "marketing": "마케팅 전략",
    "operation_plan": "운영 및 실행 계획",
    "risk_management": "위험 관리",
}

STYLES = {
    "title": ParagraphStyle("title", fontName=FONT_BOLD, fontSize=20, leading=28, textColor=NAVY),
    "meta": ParagraphStyle("meta", fontName=FONT, fontSize=9, leading=14, textColor=GRAY),
    "h2": ParagraphStyle("h2", fontName=FONT_BOLD, fontSize=13, leading=20, textColor=NAVY, spaceBefore=14, spaceAfter=6),
    "h3": ParagraphStyle("h3", fontName=FONT_BOLD, fontSize=11, leading=17, textColor=MINT, spaceBefore=10, spaceAfter=3),
    "label": ParagraphStyle("label", fontName=FONT_BOLD, fontSize=9.5, leading=15, textColor=NAVY, spaceBefore=3),
    "body": ParagraphStyle("body", fontName=FONT, fontSize=9.5, leading=15, alignment=TA_LEFT),
    "small": ParagraphStyle("small", fontName=FONT, fontSize=8.5, leading=13, textColor=GRAY),
    "cell": ParagraphStyle("cell", fontName=FONT, fontSize=8.5, leading=12.5),
    "cell_bold": ParagraphStyle("cell_bold", fontName=FONT_BOLD, fontSize=8.5, leading=12.5),
    "cell_head": ParagraphStyle("cell_head", fontName=FONT_BOLD, fontSize=8.5, leading=12.5, textColor=colors.white),
    "glance_label": ParagraphStyle("glance_label", fontName=FONT, fontSize=8, leading=11, textColor=GRAY, alignment=TA_CENTER),
    "glance_value": ParagraphStyle("glance_value", fontName=FONT_BOLD, fontSize=11, leading=15, alignment=TA_CENTER),
    "glance_score": ParagraphStyle("glance_score", fontName=FONT, fontSize=8.5, leading=12, textColor=GRAY, alignment=TA_CENTER),
    "total_label": ParagraphStyle("total_label", fontName=FONT, fontSize=9, leading=13, textColor=GRAY),
    "total_value": ParagraphStyle("total_value", fontName=FONT_BOLD, fontSize=22, leading=28, textColor=NAVY),
}


def _nfc(text) -> str:
    # Mac 파일 이름처럼 자모가 쪼개진 한글(NFD)은 폰트에 글자 모양이 없어 빈칸이 되므로 NFC로 합친다.
    return unicodedata.normalize("NFC", str(text or ""))


def _p(text, style="body"):
    return Paragraph(escape(_nfc(text)).replace("\n", "<br/>"), STYLES[style])


def _colored(text, color_hex, style="cell_bold"):
    return Paragraph(f'<font color="{color_hex}">{escape(_nfc(text))}</font>', STYLES[style])


def _bullets(lines, style="body"):
    return [_p(f"· {line}", style) for line in lines if line]


def _table(header, rows, col_widths):
    # rows 안의 값은 글자(str)이거나 이미 만든 Paragraph
    data = [[_p(h, "cell_head") for h in header]]
    data += [[c if isinstance(c, Paragraph) else _p(c, "cell") for c in row] for row in rows]
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


# 한눈에 보기: 종합 점수·등급 + 6개 항목 등급·점수 + 개선 제안·재무 검산 요약
def _glance(result: ReportAiResult, width: float):
    llm = result.llm
    grades = {g.item_key: g.grade for g in result.grades}
    total = result.total_score
    t_grade = total_grade(total)

    # 종합 점수 · 종합 등급
    total_table = Table(
        [[
            [_p("종합 점수", "total_label"), _p(f"{total}점" if total is not None else "-", "total_value")],
            [_p("종합 등급", "total_label"),
             _colored(t_grade or "-", GRADE_COLORS.get(t_grade or "", "#14213D"), "total_value")],
            _p("항목별 1~5단계 평가를 100점으로 환산하고, 항목 가중치(아이템·시장·수익성 20, 마케팅·운영 15, 위험 10)를 반영한 점수입니다.", "small"),
        ]],
        colWidths=[width * 0.2, width * 0.2, width * 0.6],
    )
    total_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (0, -1), 0),
        ("LINEAFTER", (0, 0), (1, -1), 0.5, LINE),
        ("LEFTPADDING", (1, 0), (-1, -1), 12),
    ]))

    # 항목별: 이름 / 등급 / 점수 (6칸)
    items = llm.items
    count = max(len(items), 1)
    names = [_p(ITEM_LABELS.get(i.item_key, i.item_key), "glance_label") for i in items]
    values = [_colored(grades.get(i.item_key, "-"), GRADE_COLORS.get(grades.get(i.item_key, ""), "#14213D"), "glance_value")
              for i in items]
    scores = [_p(f"{item_score(i.score)}점", "glance_score") for i in items]

    grade_table = Table([names, values, scores], colWidths=[width / count] * count)
    grade_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), MINT_LIGHT),
        ("LINEAFTER", (0, 0), (-2, -1), 0.5, colors.white),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, 0), 8),
        ("TOPPADDING", (0, 2), (-1, 2), 0),
        ("BOTTOMPADDING", (0, 2), (-1, 2), 8),
    ]))

    high = sum(1 for s in llm.suggestions if s.priority == "높음")
    mismatch = sum(1 for c in result.finance_checks if c.result == "불일치")
    missing = sum(1 for c in result.finance_checks if c.result == "근거 누락")
    summary = _p(
        f"우선 보완이 필요한 개선 제안 {high}건  ·  재무 수치 불일치 {mismatch}건  ·  재무 근거 누락 {missing}건",
        "small",
    )
    return [total_table, Spacer(1, 4 * mm), grade_table, Spacer(1, 2 * mm), summary]


# 모든 쪽 아래에 "StartFit 기획서 AI 검토 보고서 · 1 / 4" 표시
class _NumberedCanvas(rl_canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_pages = []

    def showPage(self):
        self._saved_pages.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved_pages)
        for state in self._saved_pages:
            self.__dict__.update(state)
            self._draw_footer(total)
            super().showPage()
        super().save()

    def _draw_footer(self, total: int):
        page_w = A4[0]
        y = 10 * mm
        self.setStrokeColor(LINE)
        self.setLineWidth(0.5)
        self.line(18 * mm, y + 4 * mm, page_w - 18 * mm, y + 4 * mm)
        self.setFont(FONT, 8)
        self.setFillColor(GRAY)
        self.drawString(18 * mm, y, "StartFit 기획서 AI 검토 보고서")
        self.drawRightString(page_w - 18 * mm, y, f"{self._pageNumber} / {total}")


# Gemini 검토 결과 → 검토 보고서 PDF (bytes)
def build_report_pdf(result: ReportAiResult, source_file_name: str) -> bytes:
    llm = result.llm
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm, topMargin=18 * mm, bottomMargin=22 * mm,
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

    # 한눈에 보기
    if llm.items:
        story += [_p("한눈에 보기", "h2")] + _glance(result, width)

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

    # 2. 항목별 평가 (요약표)
    if llm.items:
        rows = [
            [
                ITEM_LABELS.get(item.item_key, item.item_key),
                _colored(grades.get(item.item_key, "-"), GRADE_COLORS.get(grades.get(item.item_key, ""), "#14213D")),
                f"{item_score(item.score)}점",
                item.evidence.judgment,
            ]
            for item in llm.items
        ]
        story += [_p("2. 항목별 평가", "h2"),
                  _table(["평가 항목", "등급", "점수", "평가 의견"], rows,
                         [width * 0.24, width * 0.11, width * 0.1, width * 0.55])]

        # 항목별 상세는 새 쪽에서 시작
        story += [PageBreak(), _p("항목별 상세 평가", "h2")]
        for item in llm.items:
            block = [_p(f"{ITEM_LABELS.get(item.item_key, item.item_key)} · {grades.get(item.item_key, '-')} ({item_score(item.score)}점)", "h3")]
            if item.evidence.quote:
                page = f" (p.{item.evidence.page})" if item.evidence.page else ""
                block += [_p(f"원문 근거{page}: “{item.evidence.quote}”", "small")]
            if item.strengths:
                block += [_p("잘된 점", "label")] + _bullets(item.strengths)
            if item.gaps:
                block += [_p("보완할 점", "label")] + _bullets(item.gaps)
            story += [KeepTogether(block)]

    # 3. 재무 검산
    if result.finance_checks:
        rows = [
            [c.label, c.original or "-", c.formula or "-", _colored(c.result, RESULT_COLORS.get(c.result, "#14213D"))]
            for c in result.finance_checks
        ]
        story += [_p("3. 재무 수치 검산", "h2"),
                  _p("기획서에 적힌 수치를 다시 계산해 맞는지 확인한 결과입니다.", "small"),
                  Spacer(1, 2 * mm),
                  _table(["구분", "원문 수치", "검산", "결과"], rows,
                         [width * 0.2, width * 0.22, width * 0.43, width * 0.15])]

    # 4. 개선 제안
    if llm.suggestions:
        rows = [[_p(s.priority, "cell_bold"), s.problem, s.action] for s in llm.suggestions]
        story += [_p("4. 개선 제안", "h2"),
                  _table(["우선순위", "문제", "개선 방법"], rows, [width * 0.13, width * 0.35, width * 0.52])]

    # 5. 최종 의견
    if llm.final_opinion:
        story += [_p("5. 최종 의견", "h2"), _p(llm.final_opinion)]

    story += [Spacer(1, 8 * mm),
              _p("이 보고서는 AI가 사업계획서의 완성도를 검토한 참고 자료이며, 창업 성공이나 지원사업 선정 결과를 보장하지 않습니다.", "small")]

    doc.build(story, canvasmaker=_NumberedCanvas)
    return buffer.getvalue()
