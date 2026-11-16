import os
import re
from docx import Document
from docx.shared import Pt, Cm, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.oxml.ns import qn
from docx.oxml import OxmlElement


def _set_cell_bg(cell, hex_color):
    """Define cor de fundo de célula de tabela."""
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'), hex_color)
    tcPr.append(shd)


def _set_cell_borders(cell, color="94A3B8"):
    """Define bordas de uma célula."""
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    tcBorders = OxmlElement('w:tcBorders')
    for side in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'):
        border = OxmlElement(f'w:{side}')
        border.set(qn('w:val'), 'single')
        border.set(qn('w:sz'), '4')
        border.set(qn('w:space'), '0')
        border.set(qn('w:color'), color)
        tcBorders.append(border)
    tcPr.append(tcBorders)


def _add_run_with_style(para, text, bold=False, color=None, size_pt=10):
    run = para.add_run(text)
    run.bold = bold
    run.font.size = Pt(size_pt)
    if color:
        run.font.color.rgb = RGBColor(*bytes.fromhex(color))
    return run


def gerar_docx_atividade(
    titulo,
    conteudo,
    caminho_saida,
    subtitulo="",
    dados_cabecalho=None
):
    """
    Gera um arquivo DOCX de atividade com layout profissional padrão SENAI/SAEP,
    espelhando o design do PDF gerado via ReportLab.
    """
    if not dados_cabecalho:
        dados_cabecalho = {}

    curso_val = dados_cabecalho.get("curso") or subtitulo or "—"
    uc_val = dados_cabecalho.get("unidade_curricular") or "—"
    aula_val = dados_cabecalho.get("aula_encontro") or "Encontro Regular"
    bloom_val = dados_cabecalho.get("nivel_bloom") or "Lembrar"
    titulo_doc = titulo or "ATIVIDADE"

    doc = Document()

    # ── Configuração de Página ──────────────────────────────
    section = doc.sections[0]
    section.page_width = Cm(21)
    section.page_height = Cm(29.7)
    section.left_margin = Cm(2)
    section.right_margin = Cm(2)
    section.top_margin = Cm(1.5)
    section.bottom_margin = Cm(2)

    # ── 1. Cabeçalho: Título centralizado ──────────────────
    p_titulo = doc.add_paragraph()
    p_titulo.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run_titulo = p_titulo.add_run(titulo_doc.upper())
    run_titulo.bold = True
    run_titulo.font.size = Pt(15)
    run_titulo.font.color.rgb = RGBColor(0, 70, 150)  # #004696

    doc.add_paragraph()  # espaço

    # ── 2. Tabela de Identificação ──────────────────────────
    tbl = doc.add_table(rows=3, cols=4)
    tbl.style = 'Table Grid'

    dados_id = [
        [("Curso:", True), (curso_val, False), ("Data:", True), ("____/____/________", False)],
        [("Unidade Curricular:", True), (uc_val, False), ("Bloom:", True), (bloom_val, False)],
        [("Aula / Encontro:", True), (aula_val, False), ("Estudante:", True), ("____________________________", False)],
    ]

    col_widths = [Cm(3.8), Cm(8.0), Cm(2.0), Cm(5.2)]
    for i, row_data in enumerate(dados_id):
        row = tbl.rows[i]
        for j, (text, bold) in enumerate(row_data):
            cell = row.cells[j]
            cell.width = col_widths[j]
            _set_cell_bg(cell, "F8FAFC")
            _set_cell_borders(cell)
            p = cell.paragraphs[0]
            p.paragraph_format.space_before = Pt(2)
            p.paragraph_format.space_after = Pt(2)
            run = p.add_run(text)
            run.bold = bold
            run.font.size = Pt(9)
            if bold:
                run.font.color.rgb = RGBColor(0, 51, 102)  # #003366

    doc.add_paragraph()  # espaço

    # ── 3. Título da Seção de Questões ─────────────────────
    p_secao = doc.add_paragraph()
    run_secao = p_secao.add_run("QUESTÕES DA ATIVIDADE")
    run_secao.bold = True
    run_secao.font.size = Pt(11)
    run_secao.font.color.rgb = RGBColor(0, 70, 150)  # #004696

    # Linha separadora (parágrafo com borda inferior)
    p_linha = doc.add_paragraph()
    pPr = p_linha._p.get_or_add_pPr()
    pBdr = OxmlElement('w:pBdr')
    bottom = OxmlElement('w:bottom')
    bottom.set(qn('w:val'), 'single')
    bottom.set(qn('w:sz'), '12')
    bottom.set(qn('w:space'), '1')
    bottom.set(qn('w:color'), '004696')
    pBdr.append(bottom)
    pPr.append(pBdr)
    p_linha.paragraph_format.space_after = Pt(6)

    # ── 4. Questões formatadas ─────────────────────────────
    linhas = (conteudo or "").split("\n")
    for linha in linhas:
        l_strip = linha.strip()

        if not l_strip:
            doc.add_paragraph().paragraph_format.space_after = Pt(2)
            continue

        # Cabeçalho de questão: "Questão X:" ou "X."
        if re.match(r"^(Quest[aã]o\s*\d+|Exerc[íi]cio\s*\d+|\d+[\.\)])", l_strip, re.IGNORECASE):
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(7)
            p.paragraph_format.space_after = Pt(3)
            run = p.add_run(l_strip)
            run.bold = True
            run.font.size = Pt(10)
            run.font.color.rgb = RGBColor(15, 23, 42)  # #0F172A

        # Alternativas: A) B) C) D) E)
        elif re.match(r"^[A-E]\)", l_strip):
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Cm(0.7)
            p.paragraph_format.space_before = Pt(1)
            p.paragraph_format.space_after = Pt(2)
            run = p.add_run(l_strip)
            run.font.size = Pt(9.5)
            run.font.color.rgb = RGBColor(30, 41, 59)  # #1E293B

        # Resposta correta
        elif l_strip.lower().startswith("resposta"):
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(4)
            p.paragraph_format.space_after = Pt(3)
            run = p.add_run(l_strip)
            run.bold = True
            run.font.size = Pt(9.5)
            run.font.color.rgb = RGBColor(2, 132, 199)  # #0284C7

        # Justificativa
        elif l_strip.lower().startswith("justificativa"):
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(2)
            p.paragraph_format.space_after = Pt(6)
            run = p.add_run(l_strip)
            run.bold = True
            run.font.size = Pt(9.5)
            run.font.color.rgb = RGBColor(5, 150, 105)  # verde #059669

        # Texto normal / corpo da questão
        else:
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(2)
            p.paragraph_format.space_after = Pt(2)
            run = p.add_run(l_strip)
            run.font.size = Pt(9.5)
            run.font.color.rgb = RGBColor(30, 41, 59)  # #1E293B

    # ── 5. Rodapé ──────────────────────────────────────────
    footer = section.footer
    p_footer = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
    p_footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run_footer = p_footer.add_run("SENAI — Serviço Nacional de Aprendizagem Industrial")
    run_footer.font.size = Pt(8)
    run_footer.font.color.rgb = RGBColor(100, 116, 139)  # #64748B

    # ── Salvar ─────────────────────────────────────────────
    pasta = os.path.dirname(caminho_saida)
    if pasta:
        os.makedirs(pasta, exist_ok=True)

    doc.save(caminho_saida)
