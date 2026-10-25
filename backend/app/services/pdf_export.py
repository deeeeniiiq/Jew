"""Paginated, text-selectable PDF export for submitted educational reports.

PDFs are rendered from the immutable, validated history record. No browser
state, quiz draft or unpublished answer key participates in this export.
"""

from __future__ import annotations

from datetime import timezone
from html import escape
from io import BytesIO
from pathlib import Path
import os

import reportlab
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import HRFlowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer
from reportlab.platypus.doctemplate import LayoutError

from app.models.domain import QuizReportRecord


WATERMARK = "DAniel Schirmer Project JEW"
MAX_REPORT_CHARS = 250_000


class PDFExportError(Exception):
    """The report cannot be represented as a safe, readable PDF."""


def _font_family() -> str:
    # Prefer system fonts with broader glyph coverage. ReportLab bundles Vera,
    # which offers a portable last resort when the OS has no suitable font.
    # Helvetica cannot reliably represent Portuguese or mathematical symbols.
    candidates = [
        ("Arial", Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "arial.ttf"),
        ("DejaVuSans", Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")),
        ("LiberationSans", Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf")),
        ("ArialMac", Path("/Library/Fonts/Arial.ttf")),
        ("JEWBundledVera", Path(reportlab.__file__).resolve().parent / "fonts" / "Vera.ttf"),
    ]
    for name, path in candidates:
        if not path.is_file():
            continue
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, str(path)))
        return name
    raise PDFExportError("No supported Unicode PDF font is installed")


def _clean(value: object) -> str:
    # ReportLab Paragraph takes a small subset of HTML. Escape all user/model
    # supplied material, remove control characters and preserve line breaks.
    source = str(value or "")
    return "".join(ch for ch in source if ch in "\n\t" or ord(ch) >= 32)


def _para(value: object, style: ParagraphStyle) -> Paragraph:
    return Paragraph(escape(_clean(value)).replace("\n", "<br/>").replace("\t", "    "), style)


def render_quiz_report_pdf(record: QuizReportRecord, *, in_current_graph: bool) -> bytes:
    """Render the historic quiz result; caller must enforce graph/topic scope."""
    report = record.report
    if len(record.model_dump_json()) > MAX_REPORT_CHARS:
        raise PDFExportError("Pedagogical report exceeds the PDF export limit")
    try:
        font = _font_family()
        ink = colors.HexColor("#1C2738")
        slate = colors.HexColor("#52657A")
        accent = colors.HexColor("#176E96")
        title = ParagraphStyle("JEWTitle", fontName=font, fontSize=19, leading=25,
                               textColor=ink, spaceAfter=11, splitLongWords=1)
        heading = ParagraphStyle("JEWHeading", fontName=font, fontSize=12, leading=17,
                                 textColor=accent, spaceBefore=16, spaceAfter=7)
        body = ParagraphStyle("JEWBody", fontName=font, fontSize=9.5, leading=15,
                              textColor=ink, spaceAfter=6, alignment=TA_LEFT, splitLongWords=1)
        small = ParagraphStyle("JEWSmall", parent=body, fontSize=8.5, leading=13,
                               textColor=slate)
        caption = ParagraphStyle("JEWCaption", parent=body, fontSize=10,
                                 textColor=accent, spaceBefore=9)
        banner = ParagraphStyle("JEWBanner", parent=body, fontSize=10.5, leading=17,
                                textColor=ink, spaceAfter=12)

        stream = BytesIO()
        document = SimpleDocTemplate(stream, pagesize=A4, leftMargin=53, rightMargin=53,
                                     topMargin=64, bottomMargin=59,
                                     title="Relatório pedagógico - JEW", author="JEW",
                                     subject="Avaliação submetida")
        story = [_para("RELATÓRIO PEDAGÓGICO", caption), _para(report.title, title),
                 _para(f"Nota: {round(report.score * 100)}% | Questões: {report.question_count} | "
                       f"Corretas: {report.correct_count} | Incorretas: {report.incorrect_count} | "
                       f"Sem resposta: {report.unanswered_count}", banner),
                 HRFlowable(width="100%", color=colors.HexColor("#CAD5DF"), thickness=0.7),
                 Spacer(1, 10)]

        attempted_at = report.attempted_at
        when = attempted_at.astimezone(timezone.utc).strftime("%d/%m/%Y %H:%M UTC") if attempted_at.tzinfo else attempted_at.strftime("%d/%m/%Y %H:%M")
        story.append(_para(f"Tentativa: {record.attempt.id} | Data: {when}", small))
        story.append(_para(f"Gerador: {report.generator} | Método: {report.grading_method} | "
                           f"Tempo: {report.duration_seconds if report.duration_seconds is not None else 'não medido'}" , small))
        story.append(_para(f"Gabaritos verificados: {report.verified_keys_count} | "
                           f"Sem verificação conclusiva: {report.unverified_keys_count} | "
                           f"Não avaliadas: {report.ungraded_count}", small))
        if not in_current_graph:
            story.append(_para("Esta tentativa não integra o grafo atual após restauração. "
                               "O relatório permanece como registro histórico.", small))

        def section(name: str, lines: list[str]) -> None:
            story.append(_para(name, heading))
            for line in lines:
                story.append(_para(line, body))

        section("Visão geral", [*report.strengths, *report.improvement_areas,
                               *report.evidence_limits] or ["Sem observações registradas."])
        story.append(_para("Análise por questão", heading))
        findings = {item.question_id: item for item in report.question_findings}
        for index, review in enumerate(record.reviews, start=1):
            finding = findings.get(review.question_id)
            outcome = "Correta" if review.was_correct else "Revisar"
            if finding and finding.outcome == "unanswered":
                outcome = "Não respondida"
            question_story = [_para(f"Questão {index} - {outcome}", caption),
                              _para(review.prompt, body),
                              _para(f"Sua resposta: {review.selected_choice or 'Não respondida'}", body),
                              _para(f"Gabarito registrado: {review.correct_choice}", body)]
            if review.explanation:
                question_story.append(_para(f"Explicação: {review.explanation}", body))
            if finding:
                question_story.append(_para(f"Observação: {finding.observation}", body))
                if finding.error_category == "undetermined":
                    question_story.append(_para("Natureza do erro indeterminada com os dados disponíveis.", small))
                if finding.hypothesis:
                    question_story.append(_para(f"Hipótese: {finding.hypothesis}", body))
                if finding.diagnosis_confidence == "insufficient":
                    question_story.append(_para("Confiança insuficiente para identificar a causa.", small))
                if finding.evidence_needed:
                    question_story.append(_para(f"Evidência adicional: {finding.evidence_needed}", body))
                question_story.append(_para(f"Próxima ação: {finding.next_action}", body))
                if finding.verification_status != "verified":
                    question_story.append(_para("Gabarito sem verificação matemática conclusiva.", small))
            # Keep each short analysis readable as a unit. Oversized analyses
            # can still be split by Platypus when they exceed a page.
            story.append(KeepTogether(question_story))

        section("Plano de recuperação", [f"{i}. {item}" for i, item in enumerate(report.recovery_plan, 1)]
                or ["Nenhuma ação registrada."])
        section("Evolução histórica", [report.historical_comparison or
                "Não há comparação confiável entre conjuntos de questões."])
        section("Próximos passos", report.next_steps or ["Nenhum próximo passo registrado."])

        def decorate(canvas, doc):
            canvas.saveState()
            width, height = A4
            canvas.setFont(font, 8)
            canvas.setFillColor(slate)
            canvas.drawString(53, height - 36, "JEW  /  RELATÓRIO PEDAGÓGICO")
            canvas.drawRightString(width - 53, 34, f"Página {doc.page}")
            canvas.setFont(font, 8)
            canvas.setFillColor(colors.HexColor("#97A9B9"))
            canvas.drawCentredString(width / 2, 33, WATERMARK)
            canvas.restoreState()

        document.build(story, onFirstPage=decorate, onLaterPages=decorate)
        return stream.getvalue()
    except PDFExportError:
        raise
    except (ValueError, TypeError, OSError, LayoutError) as exc:
        raise PDFExportError("Unable to render the pedagogical report") from exc
