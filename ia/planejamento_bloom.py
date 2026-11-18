import os
import json
import re
from datetime import datetime, timedelta, date
import requests
from dotenv import load_dotenv
from utils.texto_utils import limpar_numeracao_item, limpar_numeracao_texto, eh_linha_lixo
from utils.matriz_saep_reader import filtrar_matriz_por_uc
from ia.ia_client import chamar_ia

load_dotenv()

# Níveis da Taxonomia de Bloom e verbos correspondentes
NIVEIS_BLOOM = {
    "Lembrar": {
        "verbos": ["Reconhecer", "Identificar", "Listar", "Nomear", "Descrever", "Definir"],
        "estrategias": ["AULA EXPOSITIVA DIALOGADA", "LEITURA ORIENTADA", "APRESENTAÇÃO DE CONCEITOS"],
        "recursos": ["NOTEBOOK\nTELA DIGITAL\nSLIDES ILUSTRATIVOS\nDOCUMENTOS TÉCNICOS"],
        "criterios": "VERIFICAR SE O ALUNO RECONHECE E DEFINE CORRETAMENTE OS CONCEITOS BÁSICOS.",
        "instrumentos": "PERGUNTAS DIRECIONADAS ORALMENTE E CHECKLIST TEÓRICO."
    },
    "Entender": {
        "verbos": ["Compreender", "Interpretar", "Explicar", "Diferenciar", "Classificar", "Associar"],
        "estrategias": ["AULA EXPOSITIVA DIALOGADA\nDEMONSTRAÇÃO CONCEITUAL", "ESTUDO DIRIGIDO", "DISCUSSÃO MEDIADA"],
        "recursos": ["NOTEBOOK\nTELA DIGITAL\nCOMPUTADORES\nEXEMPLOS DIDÁTICOS"],
        "criterios": "VERIFICAR O ENTENDIMENTO E INTERPRETAÇÃO DOS CONCEITOS PELO ALUNO.",
        "instrumentos": "QUESTIONÁRIO FORMATIVO E EXERCÍCIOS DE INTERPRETAÇÃO."
    },
    "Aplicar": {
        "verbos": ["Executar", "Realizar", "Utilizar", "Empregar", "Operar", "Implementar", "Aplicar"],
        "estrategias": ["AULA EXPOSITIVA COM ATIVIDADE PRÁTICA", "PRÁTICA GUIADA", "RESOLUÇÃO DE PROBLEMAS PRÁTICOS"],
        "recursos": ["NOTEBOOK\nTELA DIGITAL\nRECURSOS E INSTRUMENTOS TÉCNICOS"],
        "criterios": "VERIFICAR A CORRETA EXECUÇÃO DOS PROCEDIMENTOS PRÁTICOS E APLICAÇÃO DOS CONCEITOS.",
        "instrumentos": "OBSERVAÇÃO DIRETA COM LISTA DE CHECAGEM (CHECKLIST) E ATIVIDADES PRÁTICAS."
    },
    "Analisar": {
        "verbos": ["Analisar", "Comparar", "Diagnosticar", "Examinar", "Testar", "Verificar", "Depurar"],
        "estrategias": ["ESTUDO DE CASO\nDEPURAÇÃO E DIAGNÓSTICO", "TESTES DE FUNCIONAMENTO", "ANÁLISE DE QUALIDADE E BOAS PRÁTICAS"],
        "recursos": ["NOTEBOOK\nLABORATÓRIO T.I\nCOMPUTADORES\nFERRAMENTAS DE DIAGNÓSTICO E TESTES"],
        "criterios": "AVALIAR A CAPACIDADE DE ANÁLISE CRÍTICA, DIAGNÓSTICO DE FALHAS E CONFORMIDADE COM PADRÕES.",
        "instrumentos": "RELATÓRIO PRÁTICO DE DIAGNÓSTICO E CHECKLIST DE BOAS PRÁTICAS."
    },
    "Criar": {
        "verbos": ["Criar", "Desenvolver", "Projetar", "Construir", "Planejar", "Elaborar", "Integrar"],
        "estrategias": ["PROJETO PRÁTICO INTEGRADOR", "DESENVOLVIMENTO DE PROTÓTIPO / SOLUÇÃO", "SITUAÇÃO DE APRENDIZAGEM DESAFIADORA"],
        "recursos": ["NOTEBOOK\nLABORATÓRIO T.I\nCOMPUTADORES\nFERRAMENTAS PROFISSIONAIS"],
        "criterios": "AVALIAR A CAPACIDADE DE CRIAÇÃO, INTEGRAÇÃO E MELHORIA DE SOLUÇÕES COMPLETAS.",
        "instrumentos": "APRESENTAÇÃO DO PROJETO E RUBRICA DE ENTREGA DE PRODUTO."
    },
    "Avaliar": {
        "verbos": ["Avaliar", "Validar", "Criticar", "Julgar", "Medir", "Revisar"],
        "estrategias": ["ATIVIDADE AVALIATIVA PRÁTICA", "AVALIAÇÃO PRÁTICA INDIVIDUAL OU EM DUPLA", "SIMULAÇÃO REALÍSTICA"],
        "recursos": ["NOTEBOOK\nLABORATÓRIO T.I\nCOMPUTADORES\nSITUAÇÃO DE APRENDIZAGEM AVALIATIVA"],
        "criterios": "VERIFICAR O DOMÍNIO COMPLETO DAS CAPACIDADES TÉCNICAS E CRITÉRIOS DE DESEMPENHO DA UC.",
        "instrumentos": "AVALIAÇÃO PRÁTICA FORMAL E RUBRICA DE DESEMPENHO TÉCNICO."
    }
}


def calcular_datas_aulas(data_inicio_str, total_aulas, dias_semana=None, feriados=None, periodicidade="semanal"):
    """
    Gera as datas para cada aula conforme os dias da semana selecionados (0=Seg, ..., 6=Dom),
    desconsiderando feriados e recessos municipais/regionais,
    e respeitando a periodicidade ('semanal' ou 'quinzenal' / a cada 15 dias).
    """
    if not data_inicio_str:
        hoje = datetime.now()
        data_inicio = hoje + timedelta(days=1)
    else:
        if "/" in str(data_inicio_str):
            partes = str(data_inicio_str).strip().split("/")
            data_inicio = datetime(int(partes[2]), int(partes[1]), int(partes[0]))
        else:
            data_inicio = datetime.strptime(str(data_inicio_str).strip()[:10], "%Y-%m-%d")

    # Padrão: Segunda a Sexta (0, 1, 2, 3, 4) se não especificado
    if dias_semana is None or len(dias_semana) == 0:
        dias_semana = [0, 1, 2, 3, 4]
    else:
        dias_semana = [int(d) for d in dias_semana if str(d).isdigit()]

    # Conjunto de feriados no formato date
    feriados_set = set()
    if feriados:
        for f in feriados:
            if not f:
                continue
            if isinstance(f, (datetime, date)):
                feriados_set.add(f.date() if isinstance(f, datetime) else f)
            elif isinstance(f, str):
                s = f.strip()[:10]
                try:
                    if "/" in s:
                        p = s.split("/")
                        feriados_set.add(date(int(p[2]), int(p[1]), int(p[0])))
                    elif "-" in s:
                        p = s.split("-")
                        feriados_set.add(date(int(p[0]), int(p[1]), int(p[2])))
                except Exception:
                    pass

    datas = []
    atual = data_inicio.date() if isinstance(data_inicio, datetime) else data_inicio

    eh_quinzenal = (str(periodicidade).lower() in ["quinzenal", "15_dias", "15", "quinzena"])
    segunda_base = atual - timedelta(days=atual.weekday())

    # Itera dia a dia até atingir a quantidade total de aulas necessárias
    iteracoes = 0
    max_iter = total_aulas * 40 + 365  # Proteção contra loop infinito
    while len(datas) < total_aulas and iteracoes < max_iter:
        iteracoes += 1
        if atual.weekday() in dias_semana:
            if eh_quinzenal:
                semanas_decorridas = (atual - segunda_base).days // 7
                if semanas_decorridas % 2 != 0:
                    atual += timedelta(days=1)
                    continue

            if atual not in feriados_set:
                datas.append(datetime.combine(atual, datetime.min.time()))

        atual += timedelta(days=1)

    return datas


def dividir_em_blocos(lista, n):
    """Divide uma lista em n blocos aproximadamente iguais."""
    if not lista:
        return [[] for _ in range(n)]
    if n <= 1:
        return [lista]
    k, m = divmod(len(lista), n)
    return [lista[i * k + min(i, m):(i + 1) * k + min(i + 1, m)] for i in range(n)]


def classificar_bloom_topico(texto):
    """
    Classifica um tópico de conhecimento em uma escala de complexidade cognitiva de Bloom (1 a 6).
    1: Lembrar (Conceitos, Fundamentos, Introdução, Definições, O que é)
    2: Entender (Características, Modelos, Tipos de dados, Variáveis, Constantes, Fluxogramas)
    3: Aplicar (Operadores, Expressões, Comandos, Condicionais, Repetições, Codificação, Compiladores)
    4: Analisar (Indentação, Nomenclatura, Comentários, Legibilidade, Diagnóstico, Depuração, Testes)
    5: Criar (Projetos, Soluções integradas, Inovação, Melhoria contínua, Automação)
    6: Avaliar (Avaliação prática, Validação, Critérios de desempenho)
    """
    t = texto.lower()
    if any(k in t for k in ["avaliação", "validar", "revisão final", "simulado"]):
        return 6
    if any(k in t for k in ["inovação", "melhoria contínua", "visão inovadora", "projeto integrador", "desenvolvimento de soluções"]):
        return 5
    if any(k in t for k in ["indentação", "legibilidade", "padrões de nomenclatura", "nomenclatura", "comentários", "depuração", "debug", "diagnóstico", "teste de mesa", "análise de código"]):
        return 4
    if any(k in t for k in ["operador", "operadores", "aritmético", "relacional", "lógico", "expressões", "expressao", "repetição", "repeticao", "condicional", "condicionais", "laço", "codificação", "codificacao", "compilador", "compiladores", "implementação", "implementacao", "instalação", "configuração"]):
        return 3
    if any(k in t for k in ["tipo de dado", "tipos de dados", "constante", "constantes", "variável", "variavel", "variáveis", "variaveis", "fluxograma", "representações gráficas", "representacao grafica", "arquitetura", "componentes", "características", "ferramentas para codificação"]):
        return 2
    if any(k in t for k in ["fundamento", "fundamentos", "conceito", "conceitos", "definição", "definicao", "introdução", "introducao", "abstração", "abstracao", "etapas para construção", "o que é", "histórico"]):
        return 1
    return 3


def ordenar_conhecimentos_por_bloom(conhecimentos_brutos, matriz_itens=None):
    """
    Filtra ruídos institucionais ('Plano de Curso', cabeçalhos) e
    preserva a sequência pedagógica e hierárquica dos tópicos do Plano de Curso.
    """
    conhecimentos_limpos = []
    for c in conhecimentos_brutos:
        c_limpo = limpar_numeracao_item(c)
        if c_limpo and not eh_linha_lixo(c_limpo) and c_limpo not in conhecimentos_limpos:
            conhecimentos_limpos.append(c_limpo)

    return conhecimentos_limpos


def _desdobrar_conhecimentos_para_aulas(lista_conhecimentos, total_aulas):
    """
    Quando a quantidade de linhas de conhecimento é menor que o total de aulas,
    desdobra linhas compostas (separadas por ';' após ':') mantendo o título do tópico,
    para que todas as aulas tenham conteúdos específicos do Plano de Curso.
    """
    if len(lista_conhecimentos) >= total_aulas or not lista_conhecimentos:
        return lista_conhecimentos

    expandidos = []
    for item in lista_conhecimentos:
        if len(expandidos) + (len(lista_conhecimentos) - lista_conhecimentos.index(item)) >= total_aulas and ";" not in item:
            expandidos.append(item)
            continue
        if ":" in item and ";" in item:
            prefixo, resto = item.split(":", 1)
            partes = [p.strip() for p in resto.split(";") if p.strip()]
            if len(partes) > 1:
                for p in partes:
                    expandidos.append(f"{prefixo.strip()}: {p}")
                continue
        elif ";" in item:
            partes = [p.strip() for p in item.split(";") if p.strip()]
            if len(partes) > 1:
                expandidos.extend(partes)
                continue
        expandidos.append(item)

    return expandidos


def _distribuir_conhecimentos_por_aulas(dados_plano, total_aulas, uc_nome, matriz_uc=None):
    """
    Divide os conhecimentos do Plano de Curso em blocos exatamente para cada dia de aula:
    - Se houver grupos de tópicos principais >= total_aulas, agrupa por tópicos inteiros
      sem quebrar nenhum tópico principal no meio entre duas aulas.
    - Caso contrário, distribui os subtópicos contextualizados preservando a ordem do curso.
    """
    grupos_brutos = dados_plano.get("grupos_conhecimentos") or []
    grupos_limpos = []
    for g in grupos_brutos:
        g_l = [limpar_numeracao_item(x) for x in g if limpar_numeracao_item(x) and not eh_linha_lixo(x)]
        if g_l:
            grupos_limpos.append(g_l)

    if len(grupos_limpos) >= total_aulas:
        blocos_grupos = dividir_em_blocos(grupos_limpos, total_aulas)
        return [[item for grp in bg for item in grp] for bg in blocos_grupos]

    conhecimentos_ordenados = ordenar_conhecimentos_por_bloom(
        dados_plano.get("conhecimentos", []),
        matriz_itens=matriz_uc
    )

    if not conhecimentos_ordenados:
        conhecimentos_ordenados = [
            f"Fundamentos e conceitos de {uc_nome}",
            "Definições e princípios essenciais",
            "Estruturas e ferramentas de trabalho",
            "Procedimentos e técnicas de aplicação",
            "Operações e implementação prática",
            "Boas práticas e controle de qualidade",
            "Diagnóstico e resolução de problemas",
            "Melhoria contínua e projetos integradores"
        ]

    if len(conhecimentos_ordenados) < total_aulas:
        conhecimentos_ordenados = _desdobrar_conhecimentos_para_aulas(conhecimentos_ordenados, total_aulas)

    return dividir_em_blocos(conhecimentos_ordenados, total_aulas)


def _obter_ambiente_e_recursos_padrao(uc_nome):
    """Retorna o ambiente pedagógico e os recursos didáticos coerentes com a área da UC."""
    u = (uc_nome or "").lower()
    termos_ti = ["informática", "informatica", "hardware", "software", "computador", "rede", "programação", "programacao", "sistema", "dados", "digital", "digitais", "web", "java", "python", "escritório", "escritorio"]
    if any(t in u for t in termos_ti):
        return (
            "LABORATORIO T.I",
            "NOTEBOOK\nTELA DIGITAL\nCOMPUTADORES\nFERRAMENTAS DIDÁTICAS"
        )
    if any(t in u for t in ["obra", "canteiro", "edifica", "constru", "topografia", "alvenaria"]):
        return (
            "SALA DE AULA / LABORATÓRIO PRÁTICO",
            "NOTEBOOK\nTELA DIGITAL\nPROJETOS E DOCUMENTOS TÉCNICOS\nFERRAMENTAS DIDÁTICAS"
        )
    return (
        "SALA DE AULA / LABORATÓRIO PRÁTICO",
        "NOTEBOOK\nTELA DIGITAL\nRECURSOS E INSTRUMENTOS TÉCNICOS\nFERRAMENTAS DIDÁTICAS"
    )


def determinar_nivel_bloom_dia(dia, total_aulas):
    """Determina o nível cognitivo da Taxonomia de Bloom para a aula do dia."""
    proporcao = dia / total_aulas
    if dia == 1:
        return "Lembrar"
    elif proporcao <= 0.25:
        return "Entender"
    elif proporcao <= 0.70:
        return "Aplicar"
    elif proporcao < 0.90:
        return "Analisar"
    elif dia < total_aulas:
        return "Criar"
    else:
        return "Avaliar"


def adaptar_verbo_para_bloom(capacidade_texto, nivel_bloom):
    """
    Preserva a redação oficial das capacidades do Plano de Curso do SENAI quando já
    iniciam com verbo pedagógico válido, e adapta suavemente caso contrário.
    """
    cap_limpa = limpar_numeracao_texto(capacidade_texto).strip()
    if not cap_limpa:
        return ""

    # Se a capacidade oficial do Plano de Curso já começa com verbo no infinitivo, preserva sua gramática original
    if re.match(r"^[A-ZÁÉÍÓÚÂÊÔÃÕÇ][a-zà-ÿ]*(?:ar|er|ir|or|-se)\b", cap_limpa):
        return cap_limpa

    cfg = NIVEIS_BLOOM.get(nivel_bloom, NIVEIS_BLOOM["Aplicar"])
    verbo = cfg["verbos"][0]
    return f"{verbo} {cap_limpa[0].lower() + cap_limpa[1:]}"


def formular_capacidade_dia(dia, total_aulas, nivel_bloom, topicos_dia, capacidades_plano, matriz_itens, socioemocionais, uc_nome, caps_usadas=None):
    """
    Seleciona a Capacidade do Plano de Curso / Matriz SAEP mais aderente aos
    conhecimentos do dia, sem repetir capacidades já trabalhadas e sem cortar frases.
    """
    cfg_bloom = NIVEIS_BLOOM[nivel_bloom]
    if caps_usadas is None:
        caps_usadas = set()

    # Capacidades consolidadas do Plano de Curso (Técnicas + Socioemocionais) + Matriz SAEP
    todas_caps = []
    for c in list(capacidades_plano or []) + list(socioemocionais or []):
        c_l = limpar_numeracao_texto(c)
        if c_l and len(c_l) > 15 and not eh_linha_lixo(c_l) and c_l not in todas_caps:
            todas_caps.append(c_l)

    for m in (matriz_itens or []):
        cap_itin = m.get("capacidade_itinerario", "")
        cap_l = limpar_numeracao_texto(cap_itin)
        if cap_l and len(cap_l) > 15 and not eh_linha_lixo(cap_l) and cap_l not in todas_caps:
            todas_caps.append(cap_l)

    topicos_str = " ".join(topicos_dia).lower()
    stopwords_cap = {"para", "com", "como", "sobre", "entre", "processos", "trabalho", "equipe", "equipes", "obras", "construção", "civil", "diferentes", "atividades"}
    palavras_topicos = set(
        w for w in re.findall(r"\b[a-záéíóúâêôãõç]{4,}\b", topicos_str)
        if w not in stopwords_cap
    )

    caps_disponiveis = [c for c in todas_caps if c not in caps_usadas] or todas_caps

    melhor_cap = None
    maior_score = 0

    for cap in caps_disponiveis:
        palavras_cap = set(re.findall(r"\b[a-záéíóúâêôãõç]{4,}\b", cap.lower()))
        score = len(palavras_topicos.intersection(palavras_cap))
        if score > maior_score:
            maior_score = score
            melhor_cap = cap

    if melhor_cap and maior_score > 0:
        caps_usadas.add(melhor_cap)
        return adaptar_verbo_para_bloom(melhor_cap, nivel_bloom)

    # Mapeamento proporcional entre as capacidades disponíveis do Plano de Curso
    if caps_disponiveis:
        idx = min(int((dia - 1) / total_aulas * len(caps_disponiveis)), len(caps_disponiveis) - 1)
        cap_cand = caps_disponiveis[idx]
        caps_usadas.add(cap_cand)
        return adaptar_verbo_para_bloom(cap_cand, nivel_bloom)

    # Última aula (fallback quando o plano não possui capacidades extraídas)
    if dia == total_aulas:
        return f"Avaliar a integridade, conformidade e execução prática dos conhecimentos e procedimentos desenvolvidos na Unidade Curricular de {uc_nome}."

    if dia == total_aulas - 1 and total_aulas > 3:
        return f"Desenvolver e integrar soluções técnicas completas de {uc_nome}, propondo melhorias e inovações nos processos de trabalho."

    verbo = cfg_bloom["verbos"][dia % len(cfg_bloom["verbos"])]
    topico_ref = topicos_dia[0].split(":")[0] if topicos_dia else f"procedimentos de {uc_nome}"
    return f"{verbo} os conceitos, técnicas e procedimentos relativos a {topico_ref.lower()} na resolução de problemas práticos."


def gerar_planejamento_algoritmico(dados_plano, dados_matriz, total_aulas, horas_por_dia, datas):
    """
    Gera o planejamento docente completo cruzando o Plano de Curso e a Matriz SAEP
    através da Taxonomia de Bloom, com divisão exata e progressiva dos conhecimentos
    e capacidades ao longo dos dias.
    """
    uc_nome = dados_plano.get("unidade_curricular", "Unidade Curricular")

    # 1. Filtra a Matriz SAEP especificamente para esta UC
    matriz_uc = filtrar_matriz_por_uc(dados_matriz, uc_nome)

    # 2. Extrai e limpa capacidades do Plano
    capacidades_plano = [
        limpar_numeracao_texto(c) for c in dados_plano.get("capacidades_tecnicas", [])
        if limpar_numeracao_texto(c) and not eh_linha_lixo(c)
    ]
    socioemocionais = [
        limpar_numeracao_texto(c) for c in dados_plano.get("capacidades_socioemocionais", [])
        if limpar_numeracao_texto(c) and not eh_linha_lixo(c)
    ]

    # 3. Divide os conhecimentos estruturados pelos dias de aula
    blocos_conhecimentos = _distribuir_conhecimentos_por_aulas(
        dados_plano,
        total_aulas,
        uc_nome=uc_nome,
        matriz_uc=matriz_uc
    )
    ambiente_padrao, recursos_padrao = _obter_ambiente_e_recursos_padrao(uc_nome)

    aulas = []
    caps_usadas = set()
    for dia in range(1, total_aulas + 1):
        nivel = determinar_nivel_bloom_dia(dia, total_aulas)
        cfg_bloom = NIVEIS_BLOOM[nivel]

        topicos_dia = [t for t in blocos_conhecimentos[dia - 1] if t and not eh_linha_lixo(t)]
        if not topicos_dia:
            topicos_dia = [f"Práticas e aprofundamento em {uc_nome}"]

        texto_conhecimento = "\n".join(topicos_dia)

        capacidade_dia = formular_capacidade_dia(
            dia=dia,
            total_aulas=total_aulas,
            nivel_bloom=nivel,
            topicos_dia=topicos_dia,
            capacidades_plano=capacidades_plano,
            matriz_itens=matriz_uc,
            socioemocionais=socioemocionais,
            uc_nome=uc_nome,
            caps_usadas=caps_usadas
        )

        data_aula = datas[dia - 1] if dia - 1 < len(datas) else datetime.now()

        estrategia = cfg_bloom["estrategias"][dia % len(cfg_bloom["estrategias"])]
        criterios = cfg_bloom["criterios"]
        instrumentos = cfg_bloom["instrumentos"]

        # Matriz SAEP para cursos técnicos
        saep_dia = "Não tem cruzamento"
        if matriz_uc:
            idx_m = min(int((dia - 1) / total_aulas * len(matriz_uc)), len(matriz_uc) - 1)
            item_m = matriz_uc[idx_m]
            cap_s = str(item_m.get("capacidade_saep") or "").strip()
            con_r = str(item_m.get("conhecimentos_relacionados") or "").strip()
            if cap_s and con_r:
                saep_dia = f"{cap_s}\n{con_r}"
            elif cap_s:
                saep_dia = cap_s
            elif con_r:
                saep_dia = con_r

        aula = {
            "dia": dia,
            "nivel_bloom": nivel,
            "capacidade": capacidade_dia,
            "conhecimento": texto_conhecimento,
            "saep": saep_dia,
            "estrategia": estrategia,
            "ambiente": ambiente_padrao,
            "recursos": recursos_padrao,
            "carga_horaria_str": f"{horas_por_dia} HS",
            "criterios": criterios,
            "instrumentos": instrumentos,
            "situacao_aprendizagem": f"Situação de Aprendizagem da UC - Encontro {dia}",
            "data_inicio": data_aula,
            "data_fim": data_aula
        }
        aulas.append(aula)

    return aulas


def gerar_planejamento_ia(dados_plano, dados_matriz, total_aulas, horas_por_dia, datas):
    """
    Chama a IA para enriquecer os planos de aula com o cruzamento da Taxonomia de Bloom,
    garantindo fidelidade total à separação hierárquica dos conhecimentos do Plano de Curso.
    Em caso de lentidão, indisponibilidade ou inconsistência, utiliza o motor algorítmico robusto.
    """
    uc = dados_plano.get("unidade_curricular", "")
    objetivo = dados_plano.get("objetivo_geral", "")

    # Filtra matriz especificamente para a UC alvo
    matriz_uc = filtrar_matriz_por_uc(dados_matriz, uc)

    # Distribui os conhecimentos estruturados do Plano de Curso para cada aula
    blocos_conhecimentos = _distribuir_conhecimentos_por_aulas(
        dados_plano,
        total_aulas,
        uc_nome=uc,
        matriz_uc=matriz_uc
    )
    conhecimentos_por_aula_str = "\n".join(
        f"Aula {i+1}: {' | '.join(bloco)}"
        for i, bloco in enumerate(blocos_conhecimentos)
    )
    ambiente_padrao, recursos_padrao = _obter_ambiente_e_recursos_padrao(uc)

    capacidades_plano = [
        limpar_numeracao_texto(c) for c in dados_plano.get("capacidades_tecnicas", [])
        if limpar_numeracao_texto(c) and not eh_linha_lixo(c)
    ]
    capacidades_str = "\n".join(capacidades_plano)

    matriz_resumo = []
    for item in matriz_uc:
        cap_itin = limpar_numeracao_texto(item.get('capacidade_itinerario', ''))
        bloom_ref = item.get('detalhamento_bloom', '')
        con_rel = item.get('conhecimentos_relacionados', '')
        matriz_resumo.append(f"- {cap_itin} (Bloom: {bloom_ref} | Foco: {con_rel})")
    matriz_str = "\n".join(matriz_resumo) if matriz_resumo else "Conforme Matriz de Referência"

    prompt = f"""
Voce e um especialista em Planejamento Docente e Metodologia Pedagogica com foco na Taxonomia de Bloom.
Elabore o planejamento de EXATAMENTE {total_aulas} aulas para a Unidade Curricular: "{uc}".
Carga horaria por aula: {horas_por_dia} horas.

OBJETIVO DA UC:
{objetivo}

CAPACIDADES DA MATRIZ SAEP / ITINERÁRIO:
{matriz_str}

CAPACIDADES DO PLANO DE CURSO:
{capacidades_str}

CONHECIMENTOS DISTRIBUÍDOS POR AULA (USE EXATAMENTE ESTES CONHECIMENTOS EM CADA AULA):
{conhecimentos_por_aula_str}

REQUISITOS PEDAGOGICOS OBRIGATORIOS:
1. Mantenha rigorosamente os conhecimentos de cada aula conforme a distribuicao acima.
2. Aplique a Taxonomia de Bloom na progressao cognitiva:
   - Aulas iniciais: Lembrar e Entender
   - Aulas intermediarias: Aplicar
   - Aulas avancadas: Analisar
   - Aulas finais: Criar e Avaliar
3. REGRA CRITICA: NUNCA coloque termos como "Plano de Curso" nos conhecimentos.
4. REGRA CRITICA: NUNCA coloque numeros de topicos ou secoes (como "1", "1.1", "2.1") e NUNCA coloque simbolos (?, •, -, *) no inicio das palavras. Escreva apenas os nomes limpos, separados por quebra de linha \\n.
5. Cada aula DEVE conter:
   - dia: numero da aula de 1 a {total_aulas}
   - nivel_bloom: Nivel correspondente (Lembrar, Entender, Aplicar, Analisar, Criar, Avaliar)
   - capacidade: Frase completa iniciando com verbo de Bloom adequado
   - conhecimento: Topicos de conhecimento daquela aula separados por \\n
   - estrategia: Estrategia de ensino coerente
   - criterios: Criterio de avaliacao claro
   - instrumentos: Instrumento de avaliacao correspondente
6. Escreva sempre palavras completas e frases inteiras em portugues, sem cortes.

Responda ESTRITAMENTE em formato JSON valido, sem nenhum texto antes ou depois:
{{
  "aulas": [
    {{
      "dia": 1,
      "nivel_bloom": "Lembrar",
      "capacidade": "Reconhecer conceitos fundamentais...",
      "conhecimento": "Topico 1\\nTopico 2",
      "estrategia": "AULA EXPOSITIVA DIALOGADA",
      "criterios": "Verificar se o aluno reconhece os conceitos.",
      "instrumentos": "Perguntas orais e checklist."
    }}
  ]
}}
"""

    try:
        print(f"[IA] Solicitando planejamento docente com Taxonomia de Bloom ({total_aulas} aulas)...")
        texto_resp = chamar_ia(
            prompt=prompt,
            system_prompt="Você é um especialista em planejamento pedagógico docente e responde exclusivamente em JSON válido.",
            max_tokens=4096,
            temperature=0.2
        )

        if texto_resp:
            match_json = re.search(r"\{[\s\S]*\}", texto_resp)
            if match_json:
                dados_json = json.loads(match_json.group(0))
                lista_aulas_ia = dados_json.get("aulas", [])
                if len(lista_aulas_ia) == total_aulas:
                    aulas_finais = []
                    for idx, a in enumerate(lista_aulas_ia):
                        dia = idx + 1
                        data_aula = datas[idx] if idx < len(datas) else datetime.now()
                        cap_ia = limpar_numeracao_texto(a.get("capacidade", ""))
                        topicos_plano_dia = [t for t in blocos_conhecimentos[idx] if t and not eh_linha_lixo(t)]
                        if topicos_plano_dia and dados_plano.get("conhecimentos"):
                            con_ia = "\n".join(topicos_plano_dia)
                        else:
                            con_ia = limpar_numeracao_texto(a.get("conhecimento", ""), separador="\n") or "\n".join(topicos_plano_dia)
                        nivel_ia = a.get("nivel_bloom", determinar_nivel_bloom_dia(dia, total_aulas))

                        # Validação de integridade do texto
                        if not cap_ia or eh_linha_lixo(cap_ia):
                            cap_ia = formular_capacidade_dia(dia, total_aulas, nivel_ia, con_ia.split("\n"), capacidades_plano, matriz_uc, [], uc)

                        saep_dia = "Não tem cruzamento"
                        if matriz_uc:
                            idx_m = min(int(idx / total_aulas * len(matriz_uc)), len(matriz_uc) - 1)
                            item_m = matriz_uc[idx_m]
                            cap_s = str(item_m.get("capacidade_saep") or "").strip()
                            con_r = str(item_m.get("conhecimentos_relacionados") or "").strip()
                            if cap_s and con_r:
                                saep_dia = f"{cap_s}\n{con_r}"
                            elif cap_s:
                                saep_dia = cap_s
                            elif con_r:
                                saep_dia = con_r

                        aulas_finais.append({
                            "dia": dia,
                            "nivel_bloom": nivel_ia,
                            "capacidade": cap_ia,
                            "conhecimento": con_ia,
                            "saep": saep_dia,
                            "estrategia": a.get("estrategia", "AULA EXPOSITIVA COM ATIVIDADE PRÁTICA"),
                            "ambiente": ambiente_padrao,
                            "recursos": recursos_padrao,
                            "carga_horaria_str": f"{horas_por_dia} HS",
                            "criterios": a.get("criterios", "VERIFICAR O ENTENDIMENTO E DESEMPENHO PRÁTICO DO ALUNO."),
                            "instrumentos": a.get("instrumentos", "OBSERVAÇÃO DIRETA E ATIVIDADE PRÁTICA."),
                            "situacao_aprendizagem": f"Situação de Aprendizagem - Encontro {dia}",
                            "data_inicio": data_aula,
                            "data_fim": data_aula
                        })
                    print("[OK] Planejamento gerado com sucesso via IA!")
                    return aulas_finais

    except Exception as e:
        print(f"[AVISO] Aviso na geração via IA: {e}. Utilizando gerador algorítmico robusto...")

    # Fallback transparente para o gerador algorítmico de alta fidelidade
    return gerar_planejamento_algoritmico(dados_plano, dados_matriz, total_aulas, horas_por_dia, datas)
