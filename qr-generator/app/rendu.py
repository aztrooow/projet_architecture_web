"""Rendu des QR codes (SVG pour l'écran, PNG dans le PDF) et du PDF des billets."""

import io

import segno
from fpdf import FPDF

POLICE = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
POLICE_GRAS = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

NOIR = (14, 13, 12)
ROUGE = (178, 18, 34)
OR = (201, 162, 90)
GRIS = (120, 116, 110)


def qr_svg(jeton: str) -> bytes:
    tampon = io.BytesIO()
    segno.make(jeton, error="m").save(tampon, kind="svg", scale=4, border=2, xmldecl=False, dark="#111111")
    return tampon.getvalue()


def qr_png(jeton: str) -> bytes:
    tampon = io.BytesIO()
    segno.make(jeton, error="m").save(tampon, kind="png", scale=10, border=2)
    return tampon.getvalue()


def _billet(pdf: FPDF, x: float, y: float, infos: dict, billet: dict) -> None:
    largeur, hauteur, talon = 186, 84, 64

    # partie gauche, fond noir
    pdf.set_fill_color(*NOIR)
    pdf.rect(x, y, largeur - talon, hauteur, style="F", round_corners=True, corner_radius=3)
    pdf.set_text_color(*OR)
    pdf.set_font("dejavu", "B", 8)
    pdf.set_xy(x + 8, y + 7)
    pdf.cell(60, 4, "CINETINT  ·  CINÉMA D'ÉVRY")

    pdf.set_text_color(255, 255, 255)
    pdf.set_font("dejavu", "B", 16)
    pdf.set_xy(x + 8, y + 15)
    pdf.multi_cell(largeur - talon - 16, 7, infos["film"], max_line_height=7)

    pdf.set_font("dejavu", "", 9.5)
    pdf.set_text_color(220, 214, 204)
    pdf.set_x(x + 8)
    pdf.cell(0, 6, infos["date"].capitalize(), new_x="LMARGIN", new_y="NEXT")
    pdf.set_x(x + 8)
    pdf.cell(0, 5, f"{infos['salle']}  ·  {infos['version']}", new_x="LMARGIN", new_y="NEXT")
    if infos.get("evenement"):
        pdf.set_text_color(*OR)
        pdf.set_x(x + 8)
        pdf.cell(0, 5, infos["evenement"], new_x="LMARGIN", new_y="NEXT")

    pdf.set_text_color(*GRIS)
    pdf.set_font("dejavu", "", 7.5)
    pdf.set_xy(x + 8, y + hauteur - 22)
    pdf.cell(30, 4, "PLACE")
    pdf.cell(60, 4, "TARIF")
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("dejavu", "B", 20)
    pdf.set_xy(x + 8, y + hauteur - 17)
    pdf.cell(30, 9, billet["place"])
    pdf.set_font("dejavu", "", 9.5)
    pdf.cell(60, 9, f"{billet['tarif']}  ·  {billet['prix']}")

    # talon avec le QR code
    pdf.set_fill_color(255, 255, 255)
    pdf.set_draw_color(*NOIR)
    pdf.rect(x + largeur - talon, y, talon, hauteur, style="DF", round_corners=True, corner_radius=3)
    pdf.set_draw_color(*GRIS)
    pdf.set_dash_pattern(dash=1.2, gap=1.2)
    pdf.line(x + largeur - talon, y + 2, x + largeur - talon, y + hauteur - 2)
    pdf.set_dash_pattern()
    pdf.image(io.BytesIO(qr_png(billet["jeton"])), x=x + largeur - talon + 7, y=y + 5, w=50)
    pdf.set_text_color(*NOIR)
    pdf.set_font("dejavu", "B", 8)
    pdf.set_xy(x + largeur - talon, y + hauteur - 22)
    pdf.cell(talon, 4, infos["reference"], align="C")
    pdf.set_font("dejavu", "", 6.5)
    pdf.set_text_color(*GRIS)
    pdf.set_xy(x + largeur - talon, y + hauteur - 17)
    pdf.multi_cell(talon, 3.2, "Billet valable une seule fois.\nPrésentez ce code à l'entrée de la salle.", align="C")


def pdf_billets(infos: dict) -> bytes:
    pdf = FPDF(format="A4", unit="mm")
    pdf.set_auto_page_break(False)
    pdf.set_title(f"Billets {infos['reference']}")
    pdf.set_author("CinetINT")
    pdf.add_font("dejavu", "", POLICE)
    pdf.add_font("dejavu", "B", POLICE_GRAS)
    for i, billet in enumerate(infos["billets"]):
        if i % 3 == 0:
            pdf.add_page()
        _billet(pdf, 12, 14 + (i % 3) * 92, infos, billet)
    return bytes(pdf.output())
