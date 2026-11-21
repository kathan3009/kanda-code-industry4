"""Render report.md as the three-page submission PDF."""
from html import escape
from io import BytesIO
import os
from pathlib import Path
import re

from pypdf import PdfWriter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Table, TableStyle

root = Path(__file__).resolve().parent
fonts = Path(os.environ.get("TNR_FONT_DIR", "/System/Library/Fonts/Supplemental"))
pdfmetrics.registerFont(TTFont("TNR", str(fonts / "Times New Roman.ttf")))
pdfmetrics.registerFont(TTFont("TNR-Bold", str(fonts / "Times New Roman Bold.ttf")))
pdfmetrics.registerFontFamily("TNR", normal="TNR", bold="TNR-Bold")

body = ParagraphStyle("body", fontName="TNR", fontSize=11, leading=11, spaceAfter=8)
heading = ParagraphStyle("heading", parent=body, fontName="TNR-Bold", spaceBefore=6,
                         keepWithNext=True)
cell = ParagraphStyle("cell", parent=body, spaceAfter=0)

story, table = [], []
for line in (root / "report.md").read_text().replace("–", "-").splitlines() + [""]:
    if line.startswith("|"):
        if set(line) <= set("| -:"):
            continue
        table.append([Paragraph(escape(s.strip()), cell) for s in line.strip("|").split("|")])
        continue
    if table:
        widths = [86, 120, 91, 81, 109] if len(table[0]) == 5 else [280, 207]
        story.append(Table(table, colWidths=widths, hAlign="LEFT", style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EBEFF1")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LINEBELOW", (0, 0), (-1, 0), .5, colors.HexColor("#9BA6A8")),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
        ]), spaceAfter=8))
        table = []
    if line == "<!-- pagebreak -->":
        story.append(PageBreak())
    elif line.startswith("#"):
        story.append(Paragraph(escape(line.lstrip("# ")), heading))
    elif line:
        story.append(Paragraph(re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", escape(line)), body))


def footer(canvas, doc):
    canvas.setFont("TNR", 11)
    canvas.drawString(54, 38, "Kanda Code | MS4001")
    canvas.drawRightString(A4[0] - 54, 38, f"{doc.page} / 3")


buffer = BytesIO()
SimpleDocTemplate(buffer, pagesize=A4, topMargin=54, bottomMargin=56,
                  leftMargin=54, rightMargin=54).build(story, onFirstPage=footer,
                                                        onLaterPages=footer)
buffer.seek(0)
pdf = PdfWriter(clone_from=buffer)
if len(pdf.pages) != 3:
    raise ValueError(f"Expected three pages, found {len(pdf.pages)}")
pdf.metadata = None
pdf.xmp_metadata = None
pdf.write(root / "Kanda Code.pdf")
