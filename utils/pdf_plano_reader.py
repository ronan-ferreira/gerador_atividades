import os
import re
import json
import hashlib
import unicodedata
from collections import OrderedDict
from utils.texto_utils import limpar_numeracao_item, limpar_numeracao_texto, eh_linha_lixo

# Tenta importar pdfplumber com fallback para PyPDF2
try:
    import pdfplumber
    TEM_PDFPLUMBER = True
except ImportError:
    TEM_PDFPLUMBER = False

try:
    from PyPDF2 import PdfReader
    TEM_PYPDF2 = True
except ImportError:
    TEM_PYPDF2 = False

# Singleton lazy para OCR quando o PDF não possui camada de texto (ex: Microsoft Print to PDF / escaneado)
_ocr_engine = None


def _obter_ocr_engine():
    """Inicializa sob demanda o motor RapidOCR com modelo Latino/Português (PP-OCRv5)."""
    global _ocr_engine
    if _ocr_engine is not None:
        return _ocr_engine
    try:
        from rapidocr_onnxruntime import RapidOCR
        base_dir = os.path.dirname(os.path.abspath(__file__))
        rec_path = os.path.join(base_dir, "ocr_models", "latin_PP-OCRv5_rec_infer.onnx")
        dict_path = os.path.join(base_dir, "ocr_models", "latin_v5_dict.txt")
        if os.path.exists(rec_path) and os.path.exists(dict_path):
            _ocr_engine = RapidOCR(rec_model_path=rec_path, rec_keys_path=dict_path, use_cls=False)
        else:
            _ocr_engine = RapidOCR(use_cls=False)
        return _ocr_engine
    except Exception as e:
        print(f"[AVISO] Motor OCR não disponível: {e}")
        return None


def normalizar_texto(texto):
    """Remove acentos, caracteres especiais e converte para minúsculas."""
    if not texto:
        return ""
    texto_norm = unicodedata.normalize("NFKD", str(texto)).encode("ASCII", "ignore").decode("ASCII")
    texto_norm = re.sub(r"[^a-zA-Z0-9\s]", " ", texto_norm)
    return re.sub(r"\s+", " ", texto_norm).strip().lower()


def _singularizar_palavra(w):
    """Reduz plurais comuns em português para comparação flexível entre singular e plural."""
    if len(w) <= 3:
        return w
    if w.endswith("oes") or w.endswith("aes"):
        return w[:-3] + "ao"
    if w.endswith("ais") and len(w) > 4:
        return w[:-2] + "l"
    if w.endswith("eis") and len(w) > 4:
        return w[:-2] + "l"
    if w.endswith("res") and len(w) > 4:
        return w[:-2]
    if w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


def normalizar_radical(texto):
    """
    Normaliza o texto removendo preposições/artigos e convertendo plurais para singular,
    permitindo casar perfeitamente 'GESTÃO DE EQUIPES EM CANTEIRO DE OBRAS' com
    'Gestão de Equipes em Canteiros de Obras'.
    """
    norm = normalizar_texto(texto)
    if not norm:
        return ""
    stopwords = {"de", "da", "do", "das", "dos", "em", "na", "no", "nas", "nos", "para", "com", "por", "e", "ou", "a", "o", "as", "os"}
    palavras = [_singularizar_palavra(w) for w in norm.split() if w not in stopwords]
    return " ".join(palavras)


def _localizar_paginas_uc_ocr(doc, ocr, uc_alvo):
    """
    Em PDFs longos sem camada de texto, localiza rapidamente o intervalo de páginas
    da Unidade Curricular solicitada inspecionando as linhas sublinhadas de cabeçalho.
    """
    import numpy as np

    alvo_rad = normalizar_radical(uc_alvo)
    palavras_alvo = [w for w in alvo_rad.split() if len(w) > 2]
    if not palavras_alvo:
        return list(range(len(doc)))

    crops = []
    crop_meta = []

    for i in range(len(doc)):
        img_rgb = np.array(doc[i].render(scale=1.0).to_pil())
        img_g = img_rgb[:, :, 0]
        roi = img_g[80:780, 80:200] < 150
        ys = np.where(roi.sum(axis=1) > 65)[0] + 80
        if len(ys) == 0:
            continue
        groups = []
        for y in ys:
            if not groups or y - groups[-1][-1] > 5:
                groups.append([y])
            else:
                groups[-1].append(y)
        thin_ys = [g[0] for g in groups if len(g) <= 3]
        if not thin_ys:
            continue

        all_ys = list(thin_ys)
        for y1 in thin_ys:
            if not any(abs(y1 - 33 - oy) < 10 for oy in all_ys) and y1 > 120:
                all_ys.append(y1 - 33)
            if not any(abs(y1 - 22 - oy) < 8 for oy in all_ys) and y1 > 110:
                all_ys.append(y1 - 22)
        all_ys = sorted(all_ys)

        img_hi = np.array(doc[i].render(scale=1.5).to_pil())
        for y1 in all_ys:
            yh = int(y1 * 1.5)
            band = img_hi[max(0, yh - 24):min(img_hi.shape[0], yh + 4), 115:820]
            dark_cols = np.where((band[:, :, 0] < 180).sum(axis=0) > 0)[0]
            if len(dark_cols) > 5:
                x_end = min(band.shape[1], dark_cols[-1] + 15)
                x_start = max(0, dark_cols[0] - 8)
                crops.append(band[:, x_start:x_end])
                crop_meta.append(i)

    if not crops:
        return list(range(len(doc)))

    rec_res, _ = ocr.text_rec(crops)
    ucs_paginas = []
    for page_idx, (txt, _score) in zip(crop_meta, rec_res):
        if re.search(r"Unidade\s+[CG]urricular\s*:", txt, re.I):
            nome_uc = re.split(r"Unidade\s+[CG]urricular\s*:", txt, flags=re.I)[-1].strip()
            if nome_uc and (not ucs_paginas or ucs_paginas[-1][0] != page_idx):
                ucs_paginas.append((page_idx, nome_uc))

    if not ucs_paginas:
        return list(range(len(doc)))

    melhor_idx = 0
    melhor_score = -1
    for idx_u, (p_idx, nome_u) in enumerate(ucs_paginas):
        u_rad = normalizar_radical(nome_u)
        if u_rad == alvo_rad or alvo_rad in u_rad or u_rad in alvo_rad:
            melhor_idx = idx_u
            melhor_score = 100
            break
        pts = sum(2 if w in u_rad.split() else (1 if w in u_rad else 0) for w in palavras_alvo)
        if pts > melhor_score:
            melhor_score = pts
            melhor_idx = idx_u

    pag_ini = ucs_paginas[melhor_idx][0]
    if melhor_idx + 1 < len(ucs_paginas):
        pag_fim = ucs_paginas[melhor_idx + 1][0]
    else:
        pag_fim = len(doc) - 1

    return list(range(pag_ini, min(len(doc), pag_fim + 1)))


def extrair_texto_pdf_ocr(caminho_pdf, uc_alvo=None):
    """
    Extrai texto de PDFs vetoriais (como Microsoft Print to PDF com fontes em curvas)
    ou escaneados, utilizando cache persistente por hash MD5.
    """
    try:
        import pypdfium2 as pdfium
        import numpy as np
    except ImportError as e:
        print(f"[AVISO] pypdfium2/numpy não disponível para OCR: {e}")
        return ""

    try:
        with open(caminho_pdf, "rb") as f:
            md5_hash = hashlib.md5(f.read()).hexdigest()
    except Exception as e:
        print(f"[AVISO] Erro ao calcular hash do PDF: {e}")
        return ""

    base_proj = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cache_dir = os.path.join(base_proj, "uploads", ".pdf_ocr_cache")
    os.makedirs(cache_dir, exist_ok=True)
    cache_file = os.path.join(cache_dir, f"{md5_hash}.json")

    cache_data = {"md5": md5_hash, "total_pages": 0, "pages": {}}
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                cache_data = json.load(f)
        except Exception:
            pass

    doc = pdfium.PdfDocument(caminho_pdf)
    total_pages = len(doc)
    paginas_cache = cache_data.get("pages", {})

    # Se todas as páginas já estão em cache, retorna instantaneamente
    if len(paginas_cache) >= total_pages and total_pages > 0:
        return "\n".join(paginas_cache.get(str(i), "") for i in range(total_pages))

    ocr = _obter_ocr_engine()
    if ocr is None:
        return ""

    if uc_alvo and total_pages > 10:
        paginas_alvo = _localizar_paginas_uc_ocr(doc, ocr, uc_alvo)
    else:
        paginas_alvo = list(range(total_pages))

    alterou_cache = False
    for p_idx in paginas_alvo:
        if str(p_idx) not in paginas_cache:
            img = np.array(doc[p_idx].render(scale=1.5).to_pil())
            res, _ = ocr(img)
            linhas = [r[1] for r in (res or [])]
            paginas_cache[str(p_idx)] = "\n".join(linhas)
            alterou_cache = True

    if alterou_cache:
        cache_data["total_pages"] = total_pages
        cache_data["pages"] = paginas_cache
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    indices_ordenados = sorted(int(k) for k in paginas_cache.keys() if str(k).isdigit())
    return "\n".join(paginas_cache[str(i)] for i in indices_ordenados)


def extrair_texto_pdf(caminho_pdf, uc_alvo=None):
    """
    Extrai todo o texto do PDF preservando palavras completas e formatação.
    Prioriza pdfplumber por sua precisão com layout, usa PyPDF2 como fallback,
    e aciona OCR inteligente caso o PDF tenha sido gerado como curvas/imagens.
    """
    # Se já existir cache OCR completo para este arquivo, retorna imediatamente em milissegundos
    try:
        with open(caminho_pdf, "rb") as f:
            md5_hash = hashlib.md5(f.read()).hexdigest()
        base_proj = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cache_file = os.path.join(base_proj, "uploads", ".pdf_ocr_cache", f"{md5_hash}.json")
        if os.path.exists(cache_file):
            with open(cache_file, "r", encoding="utf-8") as fc:
                cdata = json.load(fc)
            paginas_c = cdata.get("pages", {})
            tot_p = cdata.get("total_pages", 0)
            if tot_p > 0 and len(paginas_c) >= tot_p:
                return "\n".join(paginas_c.get(str(i), "") for i in range(tot_p))
    except Exception:
        pass

    texto_completo = []

    if TEM_PDFPLUMBER:
        try:
            with pdfplumber.open(caminho_pdf) as pdf:
                amostra_pags = pdf.pages[:min(3, len(pdf.pages))]
                tem_chars = any(len(p.chars) > 0 for p in amostra_pags)
                if tem_chars:
                    for pagina in pdf.pages:
                        txt = pagina.extract_text()
                        if txt:
                            texto_completo.append(txt)
            texto_join = "\n".join(texto_completo).strip()
            if len(texto_join) >= 50:
                return texto_join
        except Exception as e:
            print(f" Erro ao extrair texto com pdfplumber: {e}. Tentando PyPDF2...")

    if TEM_PYPDF2:
        try:
            reader = PdfReader(caminho_pdf)
            amostra_pags = reader.pages[:min(3, len(reader.pages))]
            tem_txt_amostra = any(len((p.extract_text() or "").strip()) > 0 for p in amostra_pags)
            if tem_txt_amostra:
                for pagina in reader.pages:
                    txt = pagina.extract_text()
                    if txt:
                        texto_completo.append(txt)
            texto_join = "\n".join(texto_completo).strip()
            if len(texto_join) >= 50:
                return texto_join
        except Exception as e:
            print(f" Erro ao extrair texto com PyPDF2: {e}")

    print(" [OCR] PDF sem camada de texto selecionável detectado. Extraindo via OCR...")
    return extrair_texto_pdf_ocr(caminho_pdf, uc_alvo=uc_alvo)


def limpar_texto_pdf(texto):
    """
    Remove cabeçalhos repetidos de página, rodapés institucionais e
    une palavras que foram divididas por hifenização na virada de linha.
    """
    if not texto:
        return ""

    # Normaliza marcadores de bullet comuns para facilitar o reconhecimento
    texto_norm = re.sub(r"[\uf0b7\uf0a7\u2022\u25aa\u25ab\u25cf\u25cb\u25a0\u25a1\u2023\u2043]", "• ", texto)

    # 1. Padrões comuns de rodapés e cabeçalhos em PDFs de planos de curso do SENAI
    padroes_lixo = [
        r"(?m)^\s*Plano\s+de\s+Curso\b[^\n]*$",
        r"(?m)^\s*Plano\s+de\s+Ensino\b[^\n]*$",
        r"Plano\s+de\s+Curso\s+Simplificado[^\n]*",
        r"P[aá]gina\s+\d+\s+de\s+\d+",
        r"FP\.EP\.[^\n]*",
        r"FIETO[^\n]*",
        r"SERVI[ÇC]O\s+NACIONAL\s+DE\s+APRENDIZAGEM[^\n]*",
        r"(?m)^\s*PELO\s+FUTURO\s+DO\s+TRABALHO[^\n]*$",
        r"(?m)^\s*SENAI?\s*$",
        r"Departamento\s+Regional[^\n]*",
        r"Revis[aã]o\s+\d+[^\n]*"
    ]
    texto_limpo = texto_norm
    for p in padroes_lixo:
        texto_limpo = re.sub(p, "", texto_limpo, flags=re.IGNORECASE)

    # 2. Une palavras hifenizadas no final da linha (ex: "desenvolvi-\n mento" -> "desenvolvimento")
    texto_limpo = re.sub(r"(\b[a-zA-ZÀ-ÿ]+)-\s*\n\s*([a-zA-ZÀ-ÿ]+\b)", r"\1\2", texto_limpo)

    return texto_limpo


def _extrair_nome_uc_completo(texto, match_obj):
    """
    Reconstrói o nome completo da UC quando o layout de tabela em duas colunas
    quebra o nome após 'Carga Horária: XX horas' (ex: 'Conceitos de Hardware de\nCarga Horária: 28 horas\nMicrocomputadores').
    """
    nome_bruto = match_obj.group(1).strip()
    nome_limpo = re.split(r"\s+Carga\s+Hor", nome_bruto, flags=re.IGNORECASE)[0].strip()

    # Verifica as próximas 2 linhas após o match para ver se o nome da UC continuou na linha seguinte
    pos_fim_linha = match_obj.end()
    trecho_pos = texto[pos_fim_linha:pos_fim_linha + 200]
    linhas_pos = [l.strip() for l in trecho_pos.split("\n") if l.strip()]

    palavras_finais_incompletas = {"de", "da", "do", "das", "dos", "em", "na", "no", "para", "com", "e", "-", "–", "—"}
    ult_palavra = nome_limpo.split()[-1].lower() if nome_limpo.split() else ""

    if ult_palavra in palavras_finais_incompletas and linhas_pos:
        for lp in linhas_pos[:2]:
            if re.match(r"^(?:Carga\s+Hor[aá]ria|Objetivo\s+Geral|Capacidades|CONHECIMENTO|Unidade\s+Curricular)", lp, re.I):
                continue
            if len(lp) < 60 and not lp.endswith("."):
                nome_limpo = f"{nome_limpo} {lp}".strip()
                break

    return " ".join(nome_limpo.split())


def isolar_bloco_uc(texto, uc_alvo=None):
    """
    Localiza todas as seções de detalhamento de UC no PDF e recorta
    estritamente o trecho correspondente à UC determinada pelo professor.
    """
    padrao_inicio_uc = re.compile(
        r"(?:(?:\bUNIDADE\s+CURRICULAR\b|\bDetalhamento\s+da\s+Unidade\s+Curricular\b|\bM[oó]dulo\b[^\n]*)\s*[:\-]?\s*\n?\s*)?"
        r"(?:\bUnidade\s+[CG]urricular\b|\bDetalhamento\s+da\s+Unidade\s+Curricular\b|\bUC\b)\s*[:\-]\s*([^\n\r]+)",
        re.IGNORECASE
    )

    matches = list(padrao_inicio_uc.finditer(texto))

    if not matches:
        padrao_alt = re.compile(r"\n\s*(?:\bUC\s*\d+\s*[-–:]\s*|\bUNIDADE\s+CURRICULAR\s*[-–:]\s*)([^\n\r]+)", re.IGNORECASE)
        matches = list(padrao_alt.finditer(texto))

    if not matches:
        print(" Nenhuma demarcação explícita de múltiplas UCs encontrada. Processando o documento completo.")
        return texto

    ucs_encontradas = []
    for m in matches:
        nome_limpo = _extrair_nome_uc_completo(texto, m)
        if not nome_limpo or re.match(r"^(?:Capacidades|Conhecimentos?|Objetivo)\b", nome_limpo, re.IGNORECASE):
            continue
        pos_inicio = m.start()
        ucs_encontradas.append({
            "indice": len(ucs_encontradas),
            "nome": nome_limpo,
            "pos_inicio": pos_inicio
        })

    if not ucs_encontradas:
        print(" Nenhuma UC individual delimitada. Utilizando o texto completo.")
        return texto

    print(f" Encontradas {len(ucs_encontradas)} seções de Unidade Curricular no PDF:")
    for u in ucs_encontradas:
        print(f"    UC #{u['indice'] + 1}: {u['nome']}")

    if not uc_alvo or not str(uc_alvo).strip():
        print(f" Nenhuma UC alvo fornecida. Utilizando a primeira UC: '{ucs_encontradas[0]['nome']}'")
        uc_escolhida = ucs_encontradas[0]
    else:
        alvo_norm = normalizar_texto(uc_alvo)
        alvo_rad = normalizar_radical(uc_alvo)
        print(f" Buscando UC determinada pelo professor: '{uc_alvo}' (normalizado: '{alvo_norm}')")

        uc_escolhida = None

        # 1. Correspondência exata normalizada ou por radical (singular/plural)
        for u in ucs_encontradas:
            u_norm = normalizar_texto(u["nome"])
            u_rad = normalizar_radical(u["nome"])
            if (
                alvo_norm == u_norm
                or alvo_rad == u_rad
                or alvo_norm in u_norm
                or u_norm in alvo_norm
                or (alvo_rad and (alvo_rad in u_rad or u_rad in alvo_rad))
            ):
                uc_escolhida = u
                break

        # 2. Correspondência por palavras-chave significativas (comparando radicais)
        if not uc_escolhida:
            palavras_alvo = [w for w in alvo_rad.split() if len(w) > 2 and w not in {"para", "com", "tecnico", "curso"}]
            if palavras_alvo:
                melhor_match = None
                maior_pontuacao = 0
                for u in ucs_encontradas:
                    u_rad_words = set(normalizar_radical(u["nome"]).split())
                    pontos = sum(2 if w in u_rad_words else 0 for w in palavras_alvo)
                    if pontos > maior_pontuacao:
                        maior_pontuacao = pontos
                        melhor_match = u
                if melhor_match and maior_pontuacao > 0:
                    uc_escolhida = melhor_match

        # 3. Fallback: primeira UC encontrada
        if not uc_escolhida:
            print(f" UC '{uc_alvo}' não encontrada explicitamente no PDF. Utilizando UC padrão: '{ucs_encontradas[0]['nome']}'")
            uc_escolhida = ucs_encontradas[0]

    print(f" UC delimitada para extração: '{uc_escolhida['nome']}'")

    pos_ini = uc_escolhida["pos_inicio"]
    idx_atual = uc_escolhida["indice"]

    if idx_atual + 1 < len(ucs_encontradas):
        pos_fim_cand = ucs_encontradas[idx_atual + 1]["pos_inicio"]
        trecho_pre = texto[:pos_fim_cand]
        match_pre = list(re.finditer(r"\n\s*(?:M[oó]dulo[^\n]*|Carga\s+Hor[aá]ria[^\n]*)\s*", trecho_pre[-350:], re.IGNORECASE))
        if match_pre:
            pos_fim = (pos_fim_cand - 350) + match_pre[0].start()
        else:
            pos_fim = pos_fim_cand
    else:
        padrao_final = re.compile(
            r"\n\s*(?:(?:\d+[\.\)]\s*)?(?:METODOLOGIA\s+DE\s+ENSINO|CRIT[EÉ]RIOS\s+DE\s+AVALIA[ÇC][AÃ]O|PERFIL\s+DO\s+DOCENTE|INSTALA[ÇC][ÕO]ES|RECURSOS\s+DID[AÁ]TICOS|BIBLIOGRAFIA|REFER[EÊ]NCIAS|AVALIA[ÇC][AÃ]O\s+DA\s+APRENDIZAGEM|CERTIFICA[ÇC][AÃ]O|ELABORA[ÇC][AÃ]O))",
            re.IGNORECASE
        )
        match_final = padrao_final.search(texto, pos_ini)
        if match_final:
            pos_fim = match_final.start()
        else:
            pos_fim = len(texto)

    bloco_uc = texto[pos_ini:pos_fim].strip()
    return bloco_uc


def _formatar_titulo_topico(t):
    """Formata títulos de tópicos principais em Title Case legível preservando siglas."""
    t = t.strip()
    if t.isupper() and len(t) > 4:
        preps = {"de", "da", "do", "das", "dos", "em", "na", "no", "nas", "nos", "para", "por", "com", "e", "ou", "a", "o", "as", "os", "à", "às", "ao", "aos", "x"}
        siglas = {"TI", "CPU", "EPI", "EPC", "EPIS", "EPCS", "NR", "ABNT", "SENAI", "SAEP", "USB", "VGA", "HDMI", "WWW", "WEB", "5S", "5W2H", "IGBT", "IPM", "SCR", "DIAC", "TRIAC", "TBJ", "MOSFET", "JFET"}
        palavras = t.split()
        res = []
        for i, p in enumerate(palavras):
            p_clean = re.sub(r"[^A-ZÁÉÍÓÚÂÊÔÃÕÇ0-9]", "", p)
            if p_clean in siglas:
                res.append(p)
            elif i > 0 and p.lower() in preps:
                res.append(p.lower())
            else:
                res.append(p.capitalize())
        return " ".join(res)
    return t


def _estruturar_conhecimentos_numerados(itens_numerados):
    """
    Constrói a estrutura hierárquica dos conhecimentos numerados (1, 1.1, 1.1.1):
    - Consolida sub-subtópicos de 3º nível (X.Y.Z) dentro do seu subtópico de 2º nível (X.Y).
    - Contextualiza subtópicos curtos/dependentes com o título do Tópico Principal (X),
      evitando palavras soltas sem sentido ('Conceito', 'Tipos', 'Características', 'Consequências').
    - Retorna (lista_plana, grupos_por_topico).
    """
    arvore = OrderedDict()

    for num_str, txt in itens_numerados:
        partes_num = [p for p in num_str.rstrip(".").split(".") if p.isdigit()]
        if not partes_num:
            continue
        txt_limpo = re.sub(r"\s*[;,\.]?\s*\.\.\.\s*$", "", txt).strip()
        txt_limpo = txt_limpo.rstrip(".")
        if not txt_limpo or eh_linha_lixo(txt_limpo):
            continue

        n1 = partes_num[0]
        if len(partes_num) == 1:
            arvore[n1] = {"titulo": _formatar_titulo_topico(txt_limpo), "subitens": OrderedDict()}
        elif len(partes_num) == 2:
            n2 = f"{partes_num[0]}.{partes_num[1]}"
            if n1 not in arvore:
                arvore[n1] = {"titulo": "", "subitens": OrderedDict()}
            arvore[n1]["subitens"][n2] = {"titulo": txt_limpo, "filhos": []}
        else:
            n2 = f"{partes_num[0]}.{partes_num[1]}"
            if n1 not in arvore:
                arvore[n1] = {"titulo": "", "subitens": OrderedDict()}
            if n2 not in arvore[n1]["subitens"]:
                arvore[n1]["subitens"][n2] = {"titulo": "", "filhos": []}
            arvore[n1]["subitens"][n2]["filhos"].append(txt_limpo)

    grupos = []
    lista_plana = []

    for n1, dados_t in arvore.items():
        titulo_t = dados_t["titulo"]
        subitens = dados_t["subitens"]
        if not subitens:
            if titulo_t:
                grupos.append([titulo_t])
                lista_plana.append(titulo_t)
            continue

        lista_subs = list(subitens.values())
        # Coloca 'Conceito' / 'Definição' em primeiro lugar dentro do próprio tópico
        subs_conceito = [
            s for s in lista_subs
            if not s["filhos"] and re.match(r"^(?:conceitos?|defini[çc][aã]o|defini[çc][oõ]es)\b", s["titulo"], re.I)
        ]
        subs_outros = [s for s in lista_subs if s not in subs_conceito]
        lista_subs_ord = subs_conceito + subs_outros

        sub_curtos = []
        linhas_detalhadas = []

        for s in lista_subs_ord:
            st = s["titulo"]
            filhos = s["filhos"]
            if filhos:
                # Se tiver muitos filhos (ex: > 6 componentes), divide em grupos de 6
                for i in range(0, len(filhos), 6):
                    fatia = ", ".join(filhos[i:i + 6])
                    if st:
                        linhas_detalhadas.append(f"{st}: {fatia}")
                    elif titulo_t:
                        linhas_detalhadas.append(f"{titulo_t}: {fatia}")
                    else:
                        linhas_detalhadas.append(fatia)
            else:
                if ":" in st or len(st) > 65:
                    linhas_detalhadas.append(st)
                else:
                    sub_curtos.append(st)

        linhas_grupo = []
        if sub_curtos:
            # Agrupa os subtópicos curtos sob o título do Tópico Principal em fatias legíveis
            fatia_atual = []
            for sc in sub_curtos:
                fatia_atual.append(sc)
                if len("; ".join(fatia_atual)) > 115:
                    prefixo = f"{titulo_t}: " if titulo_t else ""
                    linhas_grupo.append(prefixo + "; ".join(fatia_atual))
                    fatia_atual = []
            if fatia_atual:
                prefixo = f"{titulo_t}: " if titulo_t else ""
                linhas_grupo.append(prefixo + "; ".join(fatia_atual))

        for ld in linhas_detalhadas:
            if titulo_t and not linhas_grupo and titulo_t.lower() not in ld.lower():
                linhas_grupo.append(f"{titulo_t} — {ld}")
            else:
                linhas_grupo.append(ld)

        if linhas_grupo:
            grupos.append(linhas_grupo)
            lista_plana.extend(linhas_grupo)

    return lista_plana, grupos


def _extrair_lista_capacidades(bloco, verbos_comuns):
    """Extrai e une linhas multilinhas de capacidades (técnicas, básicas ou socioemocionais)."""
    linhas = [l.strip() for l in bloco.split("\n") if l.strip()]
    itens = []
    item_atual = ""

    for linha in linhas:
        if eh_linha_lixo(linha):
            continue
        has_bullet = bool(re.match(r"^[•\-\u2022\uf0b7\*\►\▸\▪\▫]\s*", linha))
        linha_sem_bullet = re.sub(r"^[•\-\u2022\uf0b7\*\►\▸\▪\▫\s]+", "", linha).strip()
        is_verb = bool(re.match(r"^[A-ZÁÉÍÓÚÂÊÔÃÕÇ][a-zà-ÿ]+(?:ar|er|ir|or|-se)\b", linha_sem_bullet))

        if has_bullet or (is_verb and not item_atual):
            if item_atual:
                cap_limpa = limpar_numeracao_item(item_atual)
                if cap_limpa and not eh_linha_lixo(cap_limpa) and cap_limpa not in itens:
                    itens.append(cap_limpa)
            item_atual = linha_sem_bullet
        elif is_verb and len(item_atual) > 25 and (
            item_atual.endswith((".", ";"))
            or linha_sem_bullet.split()[0] in verbos_comuns
        ):
            if item_atual:
                cap_limpa = limpar_numeracao_item(item_atual)
                if cap_limpa and not eh_linha_lixo(cap_limpa) and cap_limpa not in itens:
                    itens.append(cap_limpa)
            item_atual = linha_sem_bullet
        else:
            if item_atual:
                if item_atual.endswith("-"):
                    item_atual = item_atual[:-1] + linha_sem_bullet
                else:
                    item_atual = f"{item_atual} {linha_sem_bullet}".strip()
            else:
                item_atual = linha_sem_bullet

    if item_atual:
        cap_limpa = limpar_numeracao_item(item_atual)
        if cap_limpa and not eh_linha_lixo(cap_limpa) and cap_limpa not in itens:
            itens.append(cap_limpa)

    return [i for i in itens if len(i) > 10 and not eh_linha_lixo(i)]


def estruturar_dados_plano_pdf(caminho_pdf, unidade_curricular_alvo=None):
    """
    Analisa o PDF do Plano de Curso e extrai estritamente as informações
    da Unidade Curricular solicitada pelo professor:
    - Unidade Curricular
    - Carga Horária
    - Objetivo Geral
    - Capacidades Técnicas
    - Capacidades Socioemocionais
    - Conhecimentos (e grupos_conhecimentos agrupados por tópico principal)
    Garante palavras inteiras e completas, sem cortes por quebra de linha.
    """
    texto_bruto = extrair_texto_pdf(caminho_pdf, uc_alvo=unidade_curricular_alvo)
    texto_limpo = limpar_texto_pdf(texto_bruto)

    # Isola somente a porção de texto da UC determinada
    texto_uc = isolar_bloco_uc(texto_limpo, unidade_curricular_alvo)

    dados = {
        "unidade_curricular": unidade_curricular_alvo or "",
        "carga_horaria": None,
        "objetivo_geral": "",
        "capacidades_tecnicas": [],
        "capacidades_socioemocionais": [],
        "conhecimentos": [],
        "grupos_conhecimentos": [],
        "texto_bruto": texto_uc
    }

    # 1. Nome da Unidade Curricular
    match_uc = re.search(
        r"(?:\bUnidade\s+[CG]urricular\b|\bDetalhamento\s+da\s+Unidade\s+Curricular\b|\bUC\b)\s*[:\-]\s*([^\n\r]+)",
        texto_uc,
        re.IGNORECASE
    )
    if match_uc:
        nome_uc_extraido = _extrair_nome_uc_completo(texto_uc, match_uc)
        if nome_uc_extraido and not re.match(r"^(?:Capacidades|Conhecimentos?)\b", nome_uc_extraido, re.I):
            dados["unidade_curricular"] = nome_uc_extraido

    # 2. Carga Horária da UC específica
    match_ch = re.search(r"Carga\s+Hor[aá]ria\s*:?\s*([0-9GO]+)\s*h", texto_uc, re.IGNORECASE)
    if not match_ch:
        match_ch = re.search(r"Carga\s+Hor[aá]ria\s*:\s*(\d+)", texto_uc, re.IGNORECASE)
    if match_ch:
        ch_str = match_ch.group(1).upper().replace("O", "0").replace("G", "6")
        if ch_str.isdigit():
            dados["carga_horaria"] = int(ch_str)

    # 3. Objetivo Geral da UC
    match_obj = re.search(
        r"Objetivo\s+Geral\s*:?\s*([\s\S]+?)(?=\n\s*(?:Capacidades\s+T[eé]cnicas|Capacidades\s+B[aá]sicas|Capacidades\s+Socioemocionais|CONHECIMENTOS?\b|$))",
        texto_uc,
        re.IGNORECASE
    )
    if match_obj:
        obj_texto = match_obj.group(1)
        dados["objetivo_geral"] = " ".join(obj_texto.split()).strip()

    # 4. Capacidades Técnicas ou Básicas (quando não são lista numerada de conhecimentos)
    match_cap_tec = re.search(
        r"\n\s*Capacidades\s+(?:T[eé]cnicas|B[aá]sicas)\s*:?\s*\n([\s\S]+?)(?=\n\s*(?:Capacidades\s+Socioemocionais|Capacidades\s+B[aá]sicas|CONHECIMENTOS?\b|$))",
        texto_uc,
        re.IGNORECASE
    )
    if match_cap_tec:
        verbos_tec = {
            "Utilizar", "Aplicar", "Estruturar", "Codificar", "Interpretar", "Identificar",
            "Reconhecer", "Avaliar", "Definir", "Elaborar", "Implementar", "Realizar",
            "Selecionar", "Analisar", "Liderar", "Coordenar", "Dar", "Comunicar-se",
            "Dimensionar", "Relacionar", "Calcular", "Diferenciar", "Classificar", "Substituir"
        }
        dados["capacidades_tecnicas"] = _extrair_lista_capacidades(match_cap_tec.group(1), verbos_tec)

    # 5. Capacidades Socioemocionais
    match_cap_socio = re.search(
        r"\n\s*Capacidades\s+Socioemocionais\s*:?\s*\n([\s\S]+?)(?=\n\s*(?:CONHECIMENTOS?\b|Capacidades\s+B[aá]sicas\s*:?\s*\n\s*1\b|\d+[\.\)]\s*METODOLOGIA|$))",
        texto_uc,
        re.IGNORECASE
    )
    if match_cap_socio:
        verbos_socio = {
            "Valorizar", "Demonstrar", "Atuar", "Colaborar", "Trabalhar",
            "Respeitar", "Estabelecer", "Ser", "Evidenciar", "Constatar", "Contribuir", "Acolher"
        }
        dados["capacidades_socioemocionais"] = _extrair_lista_capacidades(match_cap_socio.group(1), verbos_socio)

    # 6. Conhecimentos (aceita CONHECIMENTOS, CONHECIMENTO ou bloco numerado após Capacidades Básicas:)
    match_conhec = re.search(
        r"\n\s*CONHECIMENTOS?\s*:?\s*\n([\s\S]+)$",
        texto_uc,
        re.IGNORECASE
    )
    if not match_conhec:
        match_conhec = re.search(
            r"\n\s*Capacidades\s+B[aá]sicas\s*:?\s*\n(\s*1[\.\s][\s\S]+)$",
            texto_uc,
            re.IGNORECASE
        )

    if match_conhec:
        bloco = match_conhec.group(1)
        # Corta caso haja seções posteriores (ex: Capacidades Socioemocionais após Conhecimento, ou Metodologia)
        match_corte = re.search(
            r"\n\s*(?:UNIDADE\s+CURRICULAR|Unidade\s+[CG]urricular\s*:|M[OÓ]DULO|CARGA\s+HOR[AÁ]RIA|Capacidades\s+Socioemocionais|Capacidades\s+T[eé]cnicas|(?:\d+[\.\)]\s*)?(?:METODOLOGIA|CRIT[EÉ]RIOS|PERFIL|INSTALA[ÇC]|CERTIFICA[ÇC]|ELABORA[ÇC]|REFER[EÊ]NCIAS|BIBLIOGRAFIA)|OBJETIVO\s+GERAL)",
            bloco,
            re.IGNORECASE
        )
        if match_corte:
            bloco = bloco[:match_corte.start()]

        linhas = [l.strip() for l in bloco.split("\n") if l.strip()]
        padrao_num_topico = re.compile(r"^(\d+(?:\.\d+)*)[\.\)]?\s+(.+)$")

        # Verifica se os conhecimentos seguem numeração hierárquica (1, 1.1, 1.2, ...)
        qtd_numeradas = sum(1 for l in linhas if padrao_num_topico.match(l))

        if qtd_numeradas >= 3:
            itens_numerados = []
            for linha in linhas:
                if eh_linha_lixo(linha):
                    continue
                m_num = padrao_num_topico.match(linha)
                if m_num:
                    itens_numerados.append([m_num.group(1), m_num.group(2).strip()])
                elif itens_numerados:
                    # Linha sem numeração em bloco numerado é continuação da linha anterior
                    if itens_numerados[-1][1].endswith("-"):
                        itens_numerados[-1][1] = itens_numerados[-1][1][:-1] + linha
                    else:
                        itens_numerados[-1][1] = f"{itens_numerados[-1][1]} {linha}".strip()

            conhecimentos_planos, grupos_conhec = _estruturar_conhecimentos_numerados(itens_numerados)
            dados["conhecimentos"] = conhecimentos_planos
            dados["grupos_conhecimentos"] = grupos_conhec
        else:
            conhecimentos = []
            item_atual = ""

            for linha in linhas:
                if eh_linha_lixo(linha):
                    continue

                continua = False
                if item_atual:
                    palavras = item_atual.split()
                    ult_palavra = palavras[-1].lower().rstrip(",;:") if palavras else ""
                    if (
                        item_atual.endswith(("-", ",", ";", ":"))
                        or ult_palavra in {"de", "da", "do", "dos", "das", "para", "com", "em", "e", "ou", "a", "o", "as", "os", "por", "sobre", "na", "no", "nas", "nos", "ao", "aos", "à", "às"}
                        or re.match(r"^[a-zà-ÿ]", linha)
                    ):
                        continua = True

                if continua:
                    if item_atual.endswith("-"):
                        item_atual = item_atual[:-1] + linha
                    else:
                        item_atual = f"{item_atual} {linha}".strip()
                else:
                    if item_atual:
                        item_limpo = limpar_numeracao_item(item_atual)
                        if len(item_limpo) > 2 and not eh_linha_lixo(item_limpo) and not item_limpo.startswith("http") and item_limpo not in conhecimentos:
                            conhecimentos.append(item_limpo)
                    item_atual = linha

            if item_atual:
                item_limpo = limpar_numeracao_item(item_atual)
                if len(item_limpo) > 2 and not eh_linha_lixo(item_limpo) and not item_limpo.startswith("http") and item_limpo not in conhecimentos:
                    conhecimentos.append(item_limpo)

            dados["conhecimentos"] = conhecimentos
            dados["grupos_conhecimentos"] = [[c] for c in conhecimentos]

    return dados
