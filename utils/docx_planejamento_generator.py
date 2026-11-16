"""
Módulo de Preenchimento e Geração de Planejamento Docente em Word (.docx).
Capaz de ler qualquer modelo personalizado em Word (.docx) enviado por professores ou instituições:
- Formato Cartões Verticais (uma tabela de 2 colunas para cada aula - padrão comum em modelos institucionais)
- Formato Tabela Horizontal Única (uma única tabela com colunas: Aula, Conteúdo, Metodologia, etc.)
- Formato com Placeholders Textuais (tags {{curso}}, {{disciplina}}, etc.)

Garante que nenhuma linha seja duplicada e preenche rigorosamente todos os campos pedagógicos.
"""

import os
import re
import unicodedata
from datetime import datetime
import docx
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from utils.texto_utils import limpar_numeracao_texto


def normalizar_texto_chave(txt):
    """Remove acentos, pontuações e converte para minúsculo para buscas flexíveis."""
    if not txt:
        return ""
    s = unicodedata.normalize("NFKD", str(txt)).encode("ASCII", "ignore").decode("utf-8")
    return re.sub(r"[^a-zA-Z0-9\s]", " ", s).strip().lower()


def _set_cell_bg(cell, hex_color):
    """Define a cor de fundo de uma célula da tabela no Word."""
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    tcPr.append(shd)


def _set_cell_borders(cell, color="CBD5E1"):
    """Define bordas finas para uma célula de tabela no Word."""
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    tcBorders = OxmlElement("w:tcBorders")
    for side in ("top", "left", "bottom", "right"):
        border = OxmlElement(f"w:{side}")
        border.set(qn("w:val"), "single")
        border.set(qn("w:sz"), "4")
        border.set(qn("w:space"), "0")
        border.set(qn("w:color"), color)
        tcBorders.append(border)
    tcPr.append(tcBorders)


def _definir_texto_celula(cell, texto, bold=False, alinhamento=WD_ALIGN_PARAGRAPH.LEFT, tamanho_pt=9.5, cor_rgb=None):
    """Define o texto de uma célula com espaçamento e formatação limpa."""
    cell.text = ""
    p = cell.paragraphs[0] if cell.paragraphs else cell.add_paragraph()
    p.alignment = alinhamento
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(2)
    p.paragraph_format.line_spacing = 1.05

    linhas = str(texto or "").split("\n")
    for i, linha in enumerate(linhas):
        run = p.add_run(linha)
        run.bold = bold
        run.font.name = "Calibri"
        run.font.size = Pt(tamanho_pt)
        if cor_rgb:
            run.font.color.rgb = cor_rgb
        if i < len(linhas) - 1:
            p.add_run("\n")


def _substituir_texto_no_paragrafo(paragrafo, mapa_substituicoes):
    """
    Substitui padrões no parágrafo respeitando as divisões de runs do Word.
    """
    texto_original = paragrafo.text
    if not texto_original:
        return

    texto_alterado = texto_original
    for busca, substituto in mapa_substituicoes.items():
        if busca in texto_alterado:
            texto_alterado = texto_alterado.replace(busca, str(substituto))

    if texto_alterado != texto_original:
        if paragrafo.runs:
            primeiro_run = paragrafo.runs[0]
            primeiro_run.text = texto_alterado
            for r in paragrafo.runs[1:]:
                r.text = ""
        else:
            paragrafo.text = texto_alterado


def _substituir_em_tabelas(doc, mapa_substituicoes):
    """Varre todas as células de tabelas procurando e substituindo placeholders."""
    for tabela in doc.tables:
        for row in tabela.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    _substituir_texto_no_paragrafo(p, mapa_substituicoes)


def _preencher_tabela_cabecalho_grade(tabela, dados_cabecalho):
    """
    Preenche tabelas de cabeçalho institucional em formato grade (rótulo | valor | rótulo | valor).
    """
    nome_curso = str(dados_cabecalho.get("nome_curso", "")).strip().upper()
    uc = str(dados_cabecalho.get("unidade_curricular", "")).strip()
    turma = str(dados_cabecalho.get("codigo_turma", "")).strip().upper()
    ch = str(dados_cabecalho.get("carga_horaria", "")).strip()
    instrutor = str(dados_cabecalho.get("instrutor", "")).strip().upper()
    unidade = str(dados_cabecalho.get("unidade_escolar", "")).strip()
    modalidade = str(dados_cabecalho.get("modalidade", "")).strip().upper()
    d_ini = str(dados_cabecalho.get("data_inicio", "")).strip()
    d_fim = str(dados_cabecalho.get("data_fim", "")).strip()
    periodo = f"{d_ini} à {d_fim}" if (d_ini and d_fim) else (d_ini or d_fim or "")

    for row in tabela.rows:
        num_cells = len(row.cells)
        for c_idx in range(num_cells):
            cell_txt = normalizar_texto_chave(row.cells[c_idx].text)
            if not cell_txt or c_idx + 1 >= num_cells:
                continue

            alvo_cell = row.cells[c_idx + 1]

            if any(k in cell_txt for k in ["curso", "nome do curso"]):
                _definir_texto_celula(alvo_cell, nome_curso, bold=True)
            elif any(k in cell_txt for k in ["unidade curricular", "componente", "disciplina"]):
                _definir_texto_celula(alvo_cell, uc, bold=True)
            elif any(k in cell_txt for k in ["codigo da turma", "turma"]):
                _definir_texto_celula(alvo_cell, turma, bold=False)
            elif any(k in cell_txt for k in ["carga horaria da u c", "carga horaria"]):
                ch_txt = f"{ch} horas" if ch and not ch.endswith("h") and not "hora" in ch.lower() else ch
                _definir_texto_celula(alvo_cell, ch_txt, bold=False)
            elif any(k in cell_txt for k in ["instrutor", "docente", "professor"]):
                _definir_texto_celula(alvo_cell, instrutor, bold=True)
            elif any(k in cell_txt for k in ["modalidade"]):
                _definir_texto_celula(alvo_cell, modalidade, bold=False)
            elif any(k in cell_txt for k in ["periodo", "datas"]):
                _definir_texto_celula(alvo_cell, periodo, bold=False)
            elif any(k in cell_txt for k in ["unidade escolar", "escola", "instituicao"]) and unidade:
                _definir_texto_celula(alvo_cell, unidade, bold=False)


def _detectar_tipo_modelo_docx(doc):
    """
    Detecta o formato das tabelas do documento Word:
    - ('cartoes_verticais', tabelas_aulas): Múltiplas tabelas de 2 colunas, uma por aula
    - ('tabela_horizontal', tabela, linha_hdr_idx, mapa_cols): Uma tabela única com várias colunas
    - ('sem_tabela', None, None, None): Nenhuma tabela de aulas identificada
    """
    # 1. Verifica se existem tabelas de cartões verticais (2 colunas com rótulos pedagógicos)
    tabelas_verticais = []
    palavras_chave_rotulo = [
        "capacidade", "conhecimento", "estrategia", "ambiente", "recurso",
        "carga horaria", "criterio", "instrumento", "situacao", "periodo", "saep"
    ]

    for i, t in enumerate(doc.tables):
        if len(t.columns) == 2 and len(t.rows) >= 5:
            rotulos = [normalizar_texto_chave(r.cells[0].text) for r in t.rows]
            matches = sum(1 for rot in rotulos if any(k in rot for k in palavras_chave_rotulo))
            if matches >= 3:
                tabelas_verticais.append((i, t))

    if len(tabelas_verticais) >= 1:
        return ("cartoes_verticais", [t for _, t in tabelas_verticais], None, None)

    # 2. Verifica se existe uma tabela horizontal única com várias colunas
    palavras_chave_colunas = {
        "conteudo": ["conteudo", "conteudos", "capacidade", "capacidades", "competencia", "competencias", "o que", "tema", "objeto de conhecimento", "conhecimento", "conhecimentos", "descricao"],
        "estrategia": ["estrategia", "estrategias", "metodologia", "metodologias", "como", "procedimento", "procedimentos", "acao docente", "desenvolvimento", "atividades"],
        "recursos": ["recurso", "recursos", "recursos didaticos", "material", "materiais", "equipamento"],
        "ambiente": ["ambiente", "ambientes", "local", "onde", "espaco", "sala", "laboratorio"],
        "carga_horaria": ["carga horaria", "ch", "horas", "duracao", "tempo"],
        "criterios": ["criterio", "criterios", "criterios de avaliacao", "avaliacao", "desempenho"],
        "instrumentos": ["instrumento", "instrumentos", "instrumentos de avaliacao"],
        "situacao": ["situacao", "situacao de aprendizagem", "projeto", "desafio", "sa"],
        "data_inicio": ["data inicio", "inicio", "quando", "data", "periodo", "cronograma"],
        "data_fim": ["data fim", "termino", "fim"],
        "dia": ["aula", "dia", "encontro", "no", "item", "seq"]
    }

    melhor_tabela = None
    melhor_linha_idx = 0
    melhor_mapa = {}
    maior_score = 0

    for tabela in doc.tables:
        if len(tabela.columns) < 3:
            continue
        for r_idx, row in enumerate(tabela.rows[:4]):
            col_map_temp = {}
            score = 0
            for c_idx, cell in enumerate(row.cells):
                txt_norm = normalizar_texto_chave(cell.text)
                if not txt_norm:
                    continue
                for tipo_col, termos in palavras_chave_colunas.items():
                    if any(t in txt_norm for t in termos):
                        if tipo_col not in col_map_temp:
                            col_map_temp[tipo_col] = c_idx
                            score += 1
                        break
            if score > maior_score and score >= 2:
                maior_score = score
                melhor_tabela = tabela
                melhor_linha_idx = r_idx
                melhor_mapa = col_map_temp

    if melhor_tabela:
        return ("tabela_horizontal", melhor_tabela, melhor_linha_idx, melhor_mapa)

    return ("sem_tabela", None, None, None)


def _preencher_cartoes_verticais_docx(doc, tabelas_aulas, dados_cabecalho, aulas):
    """
    Preenche documentos no formato de Cartões Verticais (uma tabela de 2 colunas para cada aula).
    Preenche exatamente cada tabela existente SEM adicionar linhas dentro delas, evitando duplicação.
    """
    total_aulas = len(aulas)
    num_tabelas_modelo = len(tabelas_aulas)
    print(f"[DOCX] Preenchendo {total_aulas} aulas em modelo de cartões verticais ({num_tabelas_modelo} tabelas no modelo)...")

    # Localiza parágrafos de títulos de aula (ex: 'AULA — 10/11/2026')
    paragrafos_aula = []
    for p in doc.paragraphs:
        txt = p.text.strip().upper()
        if re.search(r"\bAULA\b", txt) and ("—" in txt or "-" in txt or ":" in txt or "/" in txt or re.search(r"\d", txt)):
            paragrafos_aula.append(p)

    for idx, aula in enumerate(aulas):
        cap = limpar_numeracao_texto(aula.get("capacidade", "")).strip()
        con = limpar_numeracao_texto(aula.get("conhecimento", ""), separador="\n").strip()
        if cap and con:
            texto_conteudo = f"CAPACIDADE:\n{cap}\n\n             CONHECIMENTOS:\n{con}"
        else:
            texto_conteudo = cap or con or "Desenvolvimento de competências técnicas"

        saep_txt = str(aula.get("saep") or "").strip()
        if not saep_txt:
            saep_txt = "—"

        estrategia_txt = str(aula.get("estrategia", "")).strip().upper()
        ambiente_txt = str(aula.get("ambiente", "LABORATORIO T.I")).strip().upper()
        recursos_txt = str(aula.get("recursos", "NOTEBOOK\nTELA DIGITAL\nCOMPUTADORES\nFERRAMENTAS DIDÁTICAS")).strip().upper()
        ch_txt = str(aula.get("carga_horaria_str", "4 HS")).strip().upper()
        criterios_txt = str(aula.get("criterios", "")).strip().upper()
        instrumentos_txt = str(aula.get("instrumentos", "")).strip().upper()
        sa_txt = str(aula.get("situacao_aprendizagem") or ("Situação de Aprendizagem da UC" if idx == 0 else "—")).strip()

        dt_ini = aula.get("data_inicio")
        dt_fim = aula.get("data_fim", dt_ini)
        dt_ini_str = dt_ini.strftime("%d/%m/%Y") if isinstance(dt_ini, datetime) else str(dt_ini or "")
        dt_fim_str = dt_fim.strftime("%d/%m/%Y") if isinstance(dt_fim, datetime) else str(dt_fim or "")
        periodo_aula_txt = f"{dt_ini_str} / {dt_fim_str}" if (dt_ini_str and dt_fim_str) else (dt_ini_str or dt_fim_str)

        # Atualiza o parágrafo de título da aula se existir
        if idx < len(paragrafos_aula):
            p_aula = paragrafos_aula[idx]
            p_aula.text = f"AULA — {dt_ini_str}" if dt_ini_str else f"AULA {idx+1}"

        # Se já existe a tabela correspondente no modelo, preenche suas células na coluna 1
        if idx < num_tabelas_modelo:
            tabela = tabelas_aulas[idx]
            for row in tabela.rows:
                if len(row.cells) < 2:
                    continue
                rotulo = normalizar_texto_chave(row.cells[0].text)
                cell_valor = row.cells[1]

                if any(k in rotulo for k in ["capacidade e conhecimento", "capacidade", "conhecimento"]):
                    _definir_texto_celula(cell_valor, texto_conteudo)
                elif any(k in rotulo for k in ["matriz de referencia", "saep"]):
                    _definir_texto_celula(cell_valor, saep_txt)
                elif any(k in rotulo for k in ["estrategia de ensino", "estrategia", "metodologia"]):
                    _definir_texto_celula(cell_valor, estrategia_txt)
                elif any(k in rotulo for k in ["ambiente pedagogico", "ambiente", "local"]):
                    _definir_texto_celula(cell_valor, ambiente_txt)
                elif any(k in rotulo for k in ["recursos didaticos", "recursos", "material"]):
                    _definir_texto_celula(cell_valor, recursos_txt)
                elif any(k in rotulo for k in ["carga horaria", "ch"]):
                    _definir_texto_celula(cell_valor, ch_txt)
                elif any(k in rotulo for k in ["criterios de avaliacao", "criterios"]):
                    _definir_texto_celula(cell_valor, criterios_txt)
                elif any(k in rotulo for k in ["instrumento de avaliacao", "instrumento"]):
                    _definir_texto_celula(cell_valor, instrumentos_txt)
                elif any(k in rotulo for k in ["situacao de aprendizagem", "situacao"]):
                    _definir_texto_celula(cell_valor, sa_txt)
                elif any(k in rotulo for k in ["periodo", "data"]):
                    _definir_texto_celula(cell_valor, periodo_aula_txt)

    # Se o modelo tinha MAIS tabelas de aula do que o necessário, remove as tabelas e títulos excedentes
    if num_tabelas_modelo > total_aulas:
        print(f"[DOCX] Removendo {num_tabelas_modelo - total_aulas} tabelas excedentes do modelo...")
        for t_excedente in tabelas_aulas[total_aulas:]:
            t_elem = t_excedente._tbl
            if t_elem.getparent() is not None:
                t_elem.getparent().remove(t_elem)

        if len(paragrafos_aula) > total_aulas:
            for p_excedente in paragrafos_aula[total_aulas:]:
                p_elem = p_excedente._p
                if p_elem.getparent() is not None:
                    p_elem.getparent().remove(p_elem)


def _preencher_tabela_horizontal_docx(tabela, linha_cabecalho_idx, mapeamento, dados_cabecalho, aulas):
    """
    Preenche documentos com tabela única horizontal (colunas: Aula, Conteúdo, etc.).
    Limpa linhas antigas de dados abaixo do cabeçalho e insere exatamente 1 linha por aula.
    """
    if "conteudo" not in mapeamento:
        for col_i in range(len(tabela.columns)):
            if col_i != mapeamento.get("dia"):
                mapeamento["conteudo"] = col_i
                break

    # Remove qualquer linha de dados pré-existente abaixo do cabeçalho para não duplicar
    num_linhas_total = len(tabela.rows)
    linhas_a_remover = num_linhas_total - (linha_cabecalho_idx + 1)
    if linhas_a_remover > 0:
        for _ in range(linhas_a_remover):
            ultima_linha = tabela.rows[-1]
            tabela._tbl.remove(ultima_linha._tr)

    # Adiciona exatamente 1 linha para cada aula
    for idx, aula in enumerate(aulas):
        row = tabela.add_row()

        cap = limpar_numeracao_texto(aula.get("capacidade", "")).strip()
        con = limpar_numeracao_texto(aula.get("conhecimento", ""), separador="\n").strip()
        if cap and con:
            texto_conteudo = f"CAPACIDADE:\n{cap}\n\nCONHECIMENTOS:\n{con}"
        else:
            texto_conteudo = cap or con or "Desenvolvimento de competências técnicas"

        if "dia" in mapeamento:
            _definir_texto_celula(row.cells[mapeamento["dia"]], f"Aula {idx+1}", bold=True, alinhamento=WD_ALIGN_PARAGRAPH.CENTER)

        if "conteudo" in mapeamento:
            _definir_texto_celula(row.cells[mapeamento["conteudo"]], texto_conteudo)

        if "estrategia" in mapeamento:
            _definir_texto_celula(row.cells[mapeamento["estrategia"]], str(aula.get("estrategia", "")).strip())

        if "ambiente" in mapeamento:
            _definir_texto_celula(row.cells[mapeamento["ambiente"]], str(aula.get("ambiente", "Sala / Laboratório")).strip())

        if "recursos" in mapeamento:
            _definir_texto_celula(row.cells[mapeamento["recursos"]], str(aula.get("recursos", "Recursos Didáticos")).strip())

        if "carga_horaria" in mapeamento:
            ch_txt = str(aula.get("carga_horaria_str") or f"{aula.get('horas_aula', 4)}h")
            _definir_texto_celula(row.cells[mapeamento["carga_horaria"]], ch_txt, alinhamento=WD_ALIGN_PARAGRAPH.CENTER)

        if "criterios" in mapeamento:
            _definir_texto_celula(row.cells[mapeamento["criterios"]], str(aula.get("criterios", "")).strip())

        if "instrumentos" in mapeamento:
            _definir_texto_celula(row.cells[mapeamento["instrumentos"]], str(aula.get("instrumentos", "")).strip())

        if "situacao" in mapeamento:
            sa = aula.get("situacao_aprendizagem") or "Situação de aprendizagem contextualizada com prática profissional"
            _definir_texto_celula(row.cells[mapeamento["situacao"]], str(sa).strip())

        # Datas
        dt_ini = aula.get("data_inicio")
        dt_fim = aula.get("data_fim", dt_ini)
        dt_ini_str = dt_ini.strftime("%d/%m/%Y") if isinstance(dt_ini, datetime) else str(dt_ini or "")
        dt_fim_str = dt_fim.strftime("%d/%m/%Y") if isinstance(dt_fim, datetime) else str(dt_fim or "")

        if "data_inicio" in mapeamento:
            data_texto = dt_ini_str
            if "data_fim" not in mapeamento or mapeamento["data_fim"] == mapeamento["data_inicio"]:
                if dt_fim_str and dt_fim_str != dt_ini_str:
                    data_texto = f"{dt_ini_str} a {dt_fim_str}"
            _definir_texto_celula(row.cells[mapeamento["data_inicio"]], data_texto, alinhamento=WD_ALIGN_PARAGRAPH.CENTER)

        if "data_fim" in mapeamento and mapeamento["data_fim"] != mapeamento.get("data_inicio"):
            _definir_texto_celula(row.cells[mapeamento["data_fim"]], dt_fim_str, alinhamento=WD_ALIGN_PARAGRAPH.CENTER)

        for cell in row.cells:
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
            _set_cell_borders(cell)


def _criar_tabela_padrao_no_docx(doc, dados_cabecalho, aulas):
    """
    Cria uma tabela completa de planejamento no Word caso o modelo não possua tabela prévia.
    """
    p_titulo = doc.add_paragraph()
    p_titulo.paragraph_format.space_before = Pt(12)
    p_titulo.paragraph_format.space_after = Pt(4)
    run_t = p_titulo.add_run("CRONOGRAMA E PLANEJAMENTO DE AULAS")
    run_t.bold = True
    run_t.font.name = "Calibri"
    run_t.font.size = Pt(11)
    run_t.font.color.rgb = RGBColor(0, 70, 150)

    colunas_header = [
        "Aula", "Conteúdo / Capacidades", "Metodologia / Estratégia",
        "Ambiente", "Recursos", "Avaliação / Critérios", "Data / CH"
    ]
    tabela = doc.add_table(rows=1, cols=len(colunas_header))
    tabela.style = "Table Grid"

    hdr_cells = tabela.rows[0].cells
    for i, col_name in enumerate(colunas_header):
        _definir_texto_celula(
            hdr_cells[i], col_name, bold=True,
            alinhamento=WD_ALIGN_PARAGRAPH.CENTER, tamanho_pt=9.5,
            cor_rgb=RGBColor(255, 255, 255)
        )
        _set_cell_bg(hdr_cells[i], "004696")
        _set_cell_borders(hdr_cells[i], "003366")

    for idx, aula in enumerate(aulas):
        row = tabela.add_row()

        cap = limpar_numeracao_texto(aula.get("capacidade", "")).strip()
        con = limpar_numeracao_texto(aula.get("conhecimento", ""), separador="\n").strip()
        texto_conteudo = f"CAPACIDADE:\n{cap}\n\nCONHECIMENTOS:\n{con}" if (cap and con) else (cap or con or "Competências técnicas")

        dt_ini = aula.get("data_inicio")
        dt_str = dt_ini.strftime("%d/%m/%Y") if isinstance(dt_ini, datetime) else str(dt_ini or "")
        ch_str = str(aula.get("carga_horaria_str") or f"{aula.get('horas_aula', 4)}h")
        data_ch = f"{dt_str}\n({ch_str})" if dt_str else ch_str

        _definir_texto_celula(row.cells[0], f"Aula {idx+1}", bold=True, alinhamento=WD_ALIGN_PARAGRAPH.CENTER)
        _definir_texto_celula(row.cells[1], texto_conteudo)
        _definir_texto_celula(row.cells[2], str(aula.get("estrategia", "")).strip())
        _definir_texto_celula(row.cells[3], str(aula.get("ambiente", "Sala / Laboratório")).strip())
        _definir_texto_celula(row.cells[4], str(aula.get("recursos", "Recursos Didáticos")).strip())
        _definir_texto_celula(row.cells[5], str(aula.get("criterios", "")).strip())
        _definir_texto_celula(row.cells[6], data_ch, alinhamento=WD_ALIGN_PARAGRAPH.CENTER)

        for cell in row.cells:
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
            _set_cell_borders(cell)


def gerar_docx_planejamento(dados_cabecalho, aulas, caminho_modelo, caminho_saida=None):
    """
    Função principal para preenchimento de Planejamento Docente a partir de modelo Word (.docx).
    Detecta automaticamente se é formato de cartões verticais ou tabela horizontal única,
    preenche os dados com precisão cirúrgica sem duplicar conteúdo.
    """
    if not os.path.exists(caminho_modelo):
        raise FileNotFoundError(f"Arquivo modelo Word '{caminho_modelo}' não encontrado.")

    doc = Document(caminho_modelo)

    nome_curso = str(dados_cabecalho.get("nome_curso", "")).strip()
    uc = str(dados_cabecalho.get("unidade_curricular", "")).strip()
    turma = str(dados_cabecalho.get("codigo_turma", "")).strip()
    ch = str(dados_cabecalho.get("carga_horaria", "")).strip()
    horas_dia = str(dados_cabecalho.get("horas_por_dia", "4")).strip()
    instrutor = str(dados_cabecalho.get("instrutor", "")).strip()
    unidade = str(dados_cabecalho.get("unidade_escolar", "")).strip()
    modalidade = str(dados_cabecalho.get("modalidade", "")).strip()
    data_ini = str(dados_cabecalho.get("data_inicio", "")).strip()
    data_fim = str(dados_cabecalho.get("data_fim", "")).strip()
    periodo = f"{data_ini} à {data_fim}" if (data_ini and data_fim) else (data_ini or data_fim or "")

    mapa_substituicoes = {
        "{{curso}}": nome_curso,
        "{{nome_curso}}": nome_curso,
        "{{CURSO}}": nome_curso,
        "[CURSO]": nome_curso,
        "[NOME_DO_CURSO]": nome_curso,
        "{{unidade_curricular}}": uc,
        "{{disciplina}}": uc,
        "{{uc}}": uc,
        "{{UC}}": uc,
        "[UNIDADE_CURRICULAR]": uc,
        "[DISCIPLINA]": uc,
        "{{turma}}": turma,
        "{{codigo_turma}}": turma,
        "[TURMA]": turma,
        "{{carga_horaria}}": f"{ch} horas" if ch and not "hora" in ch.lower() else ch,
        "{{ch}}": f"{ch} horas" if ch and not "hora" in ch.lower() else ch,
        "[CARGA_HORARIA]": ch,
        "{{horas_por_dia}}": f"{horas_dia}h/dia",
        "{{instrutor}}": instrutor,
        "{{professor}}": instrutor,
        "{{docente}}": instrutor,
        "[INSTRUTOR]": instrutor,
        "[PROFESSOR]": instrutor,
        "{{unidade_escolar}}": unidade,
        "{{escola}}": unidade,
        "{{instituicao}}": unidade,
        "[UNIDADE_ESCOLAR]": unidade,
        "{{modalidade}}": modalidade,
        "[MODALIDADE]": modalidade,
        "{{data_inicio}}": data_ini,
        "{{data_fim}}": data_fim,
        "{{periodo}}": periodo,
        "[PERIODO]": periodo,
        "{{total_aulas}}": str(len(aulas)),
    }

    # 1. Substitui placeholders em parágrafos do corpo do documento
    for p in doc.paragraphs:
        _substituir_texto_no_paragrafo(p, mapa_substituicoes)

    # 2. Substitui placeholders em tabelas
    _substituir_em_tabelas(doc, mapa_substituicoes)

    # 3. Preenche tabelas de cabeçalho institucional em formato grade
    if doc.tables:
        t0 = doc.tables[0]
        # Se a tabela 0 for uma tabela de cabeçalho geral (linhas com Curso, UC, etc.)
        if len(t0.columns) >= 2 and len(t0.rows) <= 8:
            _preencher_tabela_cabecalho_grade(t0, dados_cabecalho)

    # 4. Detecta o formato das aulas no documento Word
    tipo_modelo, param1, param2, param3 = _detectar_tipo_modelo_docx(doc)
    print(f"[DOCX] Formato detectado no documento Word: {tipo_modelo}")

    if tipo_modelo == "cartoes_verticais":
        tabelas_aulas = param1
        _preencher_cartoes_verticais_docx(doc, tabelas_aulas, dados_cabecalho, aulas)
    elif tipo_modelo == "tabela_horizontal":
        tabela = param1
        linha_hdr_idx = param2
        mapa_cols = param3
        _preencher_tabela_horizontal_docx(tabela, linha_hdr_idx, mapa_cols, dados_cabecalho, aulas)
    else:
        print("[DOCX] Nenhuma tabela de aulas identificada. Gerando tabela estruturada...")
        _criar_tabela_padrao_no_docx(doc, dados_cabecalho, aulas)

    # 5. Salva o documento Word preenchido
    if not caminho_saida:
        os.makedirs("outputs", exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        nome_uc_safe = "".join(c for c in uc if c.isalnum() or c in (" ", "_", "-")).strip() or "Planejamento"
        caminho_saida = f"outputs/Planejamento_Docente_{nome_uc_safe}_{timestamp}.docx"

    pasta = os.path.dirname(caminho_saida)
    if pasta:
        os.makedirs(pasta, exist_ok=True)

    doc.save(caminho_saida)
    print(f"[OK] Planejamento Docente gerado em Word (.docx) sem duplicidade: {caminho_saida}")
    return caminho_saida
