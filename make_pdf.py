"""Render report.md as the three-page submission PDF."""
import argparse
from html import escape
from io import BytesIO
import os
from pathlib import Path
import re

from pypdf import PdfWriter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Table,
                                TableStyle)

root = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument("--report", type=Path, default=root / "report.md")
parser.add_argument("--output", type=Path, default=root / "Kanda Code.pdf")
args = parser.parse_args()
fonts = Path(os.environ.get("TNR_FONT_DIR", "/System/Library/Fonts/Supplemental"))
for name, file in (("TNR", "Times New Roman"), ("TNR-Bold", "Times New Roman Bold"),
                   ("TNR-Italic", "Times New Roman Italic"),
                   ("TNR-BoldItalic", "Times New Roman Bold Italic")):
    pdfmetrics.registerFont(TTFont(name, str(fonts / f"{file}.ttf")))
pdfmetrics.registerFontFamily("TNR", normal="TNR", bold="TNR-Bold", italic="TNR-Italic",
                              boldItalic="TNR-BoldItalic")

MARGIN = 54
WIDTH = A4[0] - 2 * MARGIN
body = ParagraphStyle("body", fontName="TNR", fontSize=11, leading=11, spaceAfter=7)
heading = ParagraphStyle("heading", parent=body, fontName="TNR-Bold", spaceBefore=5,
                         keepWithNext=True)
cell = ParagraphStyle("cell", parent=body, spaceAfter=0)
display = ParagraphStyle("display", parent=body, alignment=1, leading=15, spaceBefore=2)
item = ParagraphStyle("item", parent=body, spaceAfter=3)


def inline(text):
    text = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", escape(text))
    text = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<i>\1</i>", text)
    text = re.sub(r"\^\{(.+?)\}", r"<super>\1</super>", text)
    return re.sub(r"_\{(.+?)\}", r"<sub>\1</sub>", text)


def table_widths(columns):
    first = WIDTH * {2: .6, 3: .22}.get(columns, .32)
    return [first] + [(WIDTH - first) / (columns - 1)] * (columns - 1)


story, table = [], []
for line in args.report.read_text().replace("–", "-").splitlines() + [""]:
    if line.startswith("|"):
        if set(line) <= set("| -:"):
            continue
        table.append([Paragraph(inline(s.strip()), cell) for s in line.strip("|").split("|")])
        continue
    if table:
        story.append(KeepTogether(Table(
            table, colWidths=table_widths(len(table[0])), hAlign="LEFT", spaceAfter=7,
            style=TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EBEFF1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, 0), .5, colors.HexColor("#9BA6A8")),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
            ]))))
        table = []
    figure = re.fullmatch(r"!\[\]\((.+)\)", line)
    if figure:
        path = root / figure.group(1)
        width, height = ImageReader(str(path)).getSize()
        story.append(Image(str(path), width=WIDTH, height=WIDTH * height / width))
    elif line.startswith("- "):
        story.append(Paragraph(inline(line[2:]), item))
    elif line.startswith("$$ "):
        story.append(Paragraph(inline(line[3:]), display))
    elif line == "<!-- pagebreak -->":
        story.append(PageBreak())
    elif line.startswith("#"):
        story.append(Paragraph(escape(line.lstrip("# ")), heading))
    elif line:
        story.append(Paragraph(inline(line), body))


def footer(canvas, doc):
    canvas.setFont("TNR", 11)
    canvas.drawString(MARGIN, 38, "Kanda Code | MS4001")
    canvas.drawRightString(A4[0] - MARGIN, 38, f"{doc.page} / 3")


buffer = BytesIO()
SimpleDocTemplate(buffer, pagesize=A4, topMargin=MARGIN, bottomMargin=56,
                  leftMargin=MARGIN, rightMargin=MARGIN).build(story, onFirstPage=footer,
                                                               onLaterPages=footer)
buffer.seek(0)
pdf = PdfWriter(clone_from=buffer)
if len(pdf.pages) != 3:
    raise ValueError(f"Expected three pages, found {len(pdf.pages)}")
pdf.metadata = None
pdf.xmp_metadata = None
pdf._ID = None  # pypdf has no public option to omit the trailer /ID
args.output.parent.mkdir(parents=True, exist_ok=True)
pdf.write(args.output)
