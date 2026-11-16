import os
import re
import secrets
from datetime import datetime, timedelta
import bcrypt
from database.conexao import get_cursor, release_cursor
from utils.email_service import enviar_email_codigo_recuperacao, smtp_configurado


# ============================================================
# Política e Validação de Força de Senha
# ============================================================

TAMANHO_MINIMO_SENHA = 8


def avaliar_forca_senha(senha: str) -> dict:
    """
    Avalia os critérios de segurança e força de uma senha.
    Retorna um dicionário detalhado com o status de cada requisito,
    pontuação (0 a 5), classificação e mensagens de erro.
    """
    senha_str = senha or ""

    req_tamanho = len(senha_str) >= TAMANHO_MINIMO_SENHA
    req_maiuscula = bool(re.search(r"[A-ZÀ-Ý]", senha_str))
    req_minuscula = bool(re.search(r"[a-zà-ý]", senha_str))
    req_numero = bool(re.search(r"[0-9]", senha_str))
    req_especial = bool(re.search(r"[^A-Za-zÀ-ÿ0-9\s]", senha_str))

    requisitos = {
        "tamanho_minimo": req_tamanho,
        "letra_maiuscula": req_maiuscula,
        "letra_minuscula": req_minuscula,
        "numero": req_numero,
        "caractere_especial": req_especial,
    }

    pontuacao = sum(1 for ok in requisitos.values() if ok)

    faltantes = []
    if not req_tamanho:
        faltantes.append(f"no mínimo {TAMANHO_MINIMO_SENHA} caracteres")
    if not req_maiuscula:
        faltantes.append("uma letra maiúscula (A-Z)")
    if not req_minuscula:
        faltantes.append("uma letra minúscula (a-z)")
    if not req_numero:
        faltantes.append("um número (0-9)")
    if not req_especial:
        faltantes.append("um caractere especial (ex: !, @, #, $, %)")

    # Verifica repetição de um único caractere (ex: "aaaaaaaa")
    repetida = len(senha_str) >= TAMANHO_MINIMO_SENHA and len(set(senha_str)) == 1
    if repetida:
        faltantes.append("caracteres variados (não repita o mesmo caractere)")

    valida = (pontuacao == 5) and not repetida

    if len(senha_str) == 0:
        nivel = "—"
    elif not req_tamanho or pontuacao <= 2 or repetida:
        nivel = "Muito fraca"
    elif pontuacao == 3:
        nivel = "Fraca"
    elif pontuacao == 4:
        nivel = "Média"
    elif len(senha_str) >= 12:
        nivel = "Muito forte"
    else:
        nivel = "Forte"

    if valida:
        mensagem = "Senha forte e válida."
    elif len(senha_str) < TAMANHO_MINIMO_SENHA:
        if len(faltantes) > 1:
            demais = ", ".join(faltantes[1:])
            mensagem = (
                f"A senha deve ter no mínimo {TAMANHO_MINIMO_SENHA} caracteres. "
                f"Senha fraca: também precisa conter pelo menos {demais}."
            )
        else:
            mensagem = f"A senha deve ter no mínimo {TAMANHO_MINIMO_SENHA} caracteres."
    else:
        itens_str = ", ".join(faltantes)
        mensagem = f"Senha fraca! Para sua segurança, a senha deve conter pelo menos: {itens_str}."

    return {
        "valida": valida,
        "pontuacao": pontuacao,
        "nivel": nivel,
        "tamanho": len(senha_str),
        "tamanho_minimo": TAMANHO_MINIMO_SENHA,
        "requisitos": requisitos,
        "faltantes": faltantes,
        "mensagem": mensagem,
    }


def validar_forca_senha(senha: str) -> tuple[bool, str]:
    """
    Valida se a senha atende aos requisitos mínimos de segurança:
    - Mínimo de 8 caracteres
    - Pelo menos 1 letra maiúscula
    - Pelo menos 1 letra minúscula
    - Pelo menos 1 número
    - Pelo menos 1 caractere especial

    Retorna: (valida: bool, mensagem: str)
    """
    if not senha:
        return False, f"Informe uma senha válida com no mínimo {TAMANHO_MINIMO_SENHA} caracteres."

    avaliacao = avaliar_forca_senha(senha)
    return avaliacao["valida"], avaliacao["mensagem"]


# ============================================================
# Hash de senha
# ============================================================

def gerar_hash_senha(senha: str) -> str:
    """Gera um hash bcrypt seguro para a senha ou token."""
    if not senha:
        return ""
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(senha.encode("utf-8"), salt).decode("utf-8")


def verificar_senha(senha_candidata: str, senha_armazenada: str) -> bool:
    """
    Verifica a senha informada contra a armazenada.
    Suporta tanto hashes bcrypt ($2a$, $2b$, $2y$) quanto migração suave
    de senhas legadas que ainda estavam em texto puro.
    """
    if not senha_candidata or not senha_armazenada:
        return False

    if senha_armazenada.startswith(("$2a$", "$2b$", "$2y$")):
        try:
            return bcrypt.checkpw(
                senha_candidata.encode("utf-8"),
                senha_armazenada.encode("utf-8")
            )
        except Exception:
            return False

    # Fallback para senhas legadas em texto puro (comparação em tempo constante)
    return secrets.compare_digest(senha_candidata, senha_armazenada)


def atualizar_senha_para_hash_se_necessario(usuario_id: int, senha_plana: str, senha_armazenada: str):
    """
    Migra transparentemente uma senha em texto puro para hash bcrypt
    após um login bem-sucedido.
    """
    if not senha_armazenada.startswith(("$2a$", "$2b$", "$2y$")):
        novo_hash = gerar_hash_senha(senha_plana)
        conn, cursor = get_cursor()
        try:
            cursor.execute(
                "UPDATE usuarios SET senha = %s WHERE id = %s",
                (novo_hash, usuario_id)
            )
            conn.commit()
        except Exception as e:
            print(f"[SEGURANCA] Aviso ao migrar senha de usuario #{usuario_id}: {e}")
        finally:
            release_cursor(conn, cursor)


# ============================================================
# Redefinição de senha — funções administrativas (mantidas)
# ============================================================

def redefinir_senha_usuario(usuario_id: int, nova_senha: str) -> bool:
    """Atualiza a senha de um usuário no banco com hash seguro bcrypt após validar força."""
    valida, _ = validar_forca_senha(nova_senha)
    if not valida:
        return False
    novo_hash = gerar_hash_senha(nova_senha)
    conn, cursor = get_cursor()
    try:
        cursor.execute("UPDATE usuarios SET senha = %s WHERE id = %s", (novo_hash, usuario_id))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        print(f"[SEGURANCA] Erro ao redefinir senha do usuário #{usuario_id}: {e}")
        return False
    finally:
        release_cursor(conn, cursor)


def redefinir_senha_por_email(email: str, nova_senha: str) -> bool:
    """Atualiza a senha de um usuário através do e-mail cadastrado (uso interno/admin)."""
    if not email:
        return False
    valida, _ = validar_forca_senha(nova_senha)
    if not valida:
        return False
    novo_hash = gerar_hash_senha(nova_senha)
    conn, cursor = get_cursor()
    try:
        cursor.execute("UPDATE usuarios SET senha = %s WHERE LOWER(email) = LOWER(%s)", (novo_hash, email.strip()))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        print(f"[SEGURANCA] Erro ao redefinir senha por email ({email}): {e}")
        return False
    finally:
        release_cursor(conn, cursor)


# ============================================================
# Fluxo OTP de recuperação de senha (público)
# ============================================================

def solicitar_codigo_otp(email: str) -> tuple[bool, str, dict]:
    """
    Gera e envia um código de verificação OTP de 6 dígitos para o e-mail informado.
    O código OTP é armazenado com hash bcrypt no banco de dados.
    Implementa rate limiting e proteção contra enumeração de usuários.

    Retorna: (sucesso, mensagem, info_dict)
    """
    email_limpo = (email or "").strip().lower()
    if not email_limpo:
        return False, "Informe o endereço de e-mail institucional.", {}

    conn, cursor = get_cursor()
    try:
        # Busca usuário pelo e-mail
        cursor.execute("SELECT id, nome FROM usuarios WHERE LOWER(email) = LOWER(%s)", (email_limpo,))
        usuario = cursor.fetchone()

        # Proteção contra enumeração: retorna mensagem neutra mesmo se não encontrado
        if not usuario:
            return True, "Se este e-mail estiver cadastrado, o código de recuperação foi enviado para sua caixa de entrada.", {
                "email": email_limpo,
                "simulado": True,
            }

        usuario_id, nome = usuario

        # Rate limit: não permite novo código antes de 60 segundos
        cursor.execute(
            """
            SELECT criado_em FROM codigos_recuperacao
            WHERE usuario_id = %s AND criado_em > (CURRENT_TIMESTAMP - INTERVAL '60 seconds')
            ORDER BY criado_em DESC LIMIT 1
            """,
            (usuario_id,)
        )
        if cursor.fetchone():
            return False, "Por favor, aguarde 1 minuto antes de solicitar um novo código.", {
                "email": email_limpo,
                "aguardar": True,
            }

        # Invalida códigos anteriores não usados
        cursor.execute(
            "UPDATE codigos_recuperacao SET usado = TRUE WHERE usuario_id = %s AND usado = FALSE",
            (usuario_id,)
        )

        # Gera código numérico de 6 dígitos criptograficamente seguro e armazena seu hash
        codigo_otp = f"{secrets.randbelow(900000) + 100000:06d}"
        codigo_hash = gerar_hash_senha(codigo_otp)
        expira_em = datetime.now() + timedelta(minutes=15)

        cursor.execute(
            "INSERT INTO codigos_recuperacao (usuario_id, codigo, expira_em) VALUES (%s, %s, %s)",
            (usuario_id, codigo_hash, expira_em)
        )
        conn.commit()

        # Envia o e-mail (ou simula em modo dev)
        _sucesso_envio, status_envio = enviar_email_codigo_recuperacao(email_limpo, nome, codigo_otp)

        info = {
            "email": email_limpo,
            "dev_mode": (status_envio == "dev_mode"),
            "codigo_dev": codigo_otp if status_envio == "dev_mode" else None,
        }

        return True, "Código de verificação enviado! Verifique sua caixa de entrada.", info

    except Exception as e:
        print(f"[SEGURANCA] Erro ao solicitar código OTP ({email_limpo}): {e}")
        return False, "Ocorreu um erro ao processar sua solicitação. Tente novamente mais tarde.", {}
    finally:
        release_cursor(conn, cursor)


def redefinir_senha_com_otp(email: str, codigo: str, nova_senha: str, confirmar_senha: str) -> tuple[bool, str]:
    """
    Valida o código OTP e define a nova senha do usuário com hash bcrypt.
    Exige senha forte com no mínimo 8 caracteres.
    Controla validade de 15 min e máximo de 5 tentativas incorretas.

    Retorna: (sucesso, mensagem)
    """
    email_limpo = (email or "").strip().lower()
    codigo_limpo = (codigo or "").strip().replace(" ", "").replace("-", "")

    if not email_limpo or not codigo_limpo or not nova_senha or not confirmar_senha:
        return False, "Preencha todos os campos obrigatórios."

    senha_valida, msg_senha = validar_forca_senha(nova_senha)
    if not senha_valida:
        return False, msg_senha

    if nova_senha != confirmar_senha:
        return False, "A confirmação de senha não confere com a nova senha digitada."

    conn, cursor = get_cursor()
    try:
        cursor.execute("SELECT id FROM usuarios WHERE LOWER(email) = LOWER(%s)", (email_limpo,))
        usuario = cursor.fetchone()
        if not usuario:
            return False, "E-mail ou código de verificação inválido."

        usuario_id = usuario[0]

        # Busca o código ativo mais recente
        cursor.execute(
            """
            SELECT id, codigo, tentativas, expira_em
            FROM codigos_recuperacao
            WHERE usuario_id = %s AND usado = FALSE
            ORDER BY criado_em DESC LIMIT 1
            """,
            (usuario_id,)
        )
        registro = cursor.fetchone()

        if not registro:
            return False, "Nenhum código ativo encontrado para este e-mail. Solicite um novo código."

        codigo_id, codigo_armazenado, tentativas, expira_em = registro

        # Verifica expiração
        if datetime.now() > expira_em:
            cursor.execute("UPDATE codigos_recuperacao SET usado = TRUE WHERE id = %s", (codigo_id,))
            conn.commit()
            return False, "O código de verificação expirou (validade de 15 minutos). Solicite um novo código."

        # Verifica limite de tentativas
        if tentativas >= 5:
            cursor.execute("UPDATE codigos_recuperacao SET usado = TRUE WHERE id = %s", (codigo_id,))
            conn.commit()
            return False, "Número máximo de tentativas excedido. Solicite um novo código."

        # Verifica o código (suporta hash bcrypt e texto puro legado)
        if not verificar_senha(codigo_limpo, str(codigo_armazenado).strip()):
            novas_tentativas = tentativas + 1
            cursor.execute(
                "UPDATE codigos_recuperacao SET tentativas = %s WHERE id = %s",
                (novas_tentativas, codigo_id)
            )
            conn.commit()

            restantes = max(0, 5 - novas_tentativas)
            if restantes == 0:
                cursor.execute("UPDATE codigos_recuperacao SET usado = TRUE WHERE id = %s", (codigo_id,))
                conn.commit()
                return False, "Código incorreto. Limite de tentativas excedido. Solicite um novo código."

            return False, f"Código de verificação incorreto. Você ainda possui {restantes} tentativa(s)."

        # ✅ Código correto: atualiza senha e invalida o código
        novo_hash = gerar_hash_senha(nova_senha)
        cursor.execute("UPDATE usuarios SET senha = %s WHERE id = %s", (novo_hash, usuario_id))
        cursor.execute("UPDATE codigos_recuperacao SET usado = TRUE WHERE id = %s", (codigo_id,))
        conn.commit()

        return True, "Sua senha foi redefinida com sucesso! Acesse o sistema com sua nova credencial."

    except Exception as e:
        print(f"[SEGURANCA] Erro ao redefinir senha com OTP ({email_limpo}): {e}")
        return False, "Erro ao atualizar a senha no banco de dados. Tente novamente."
    finally:
        release_cursor(conn, cursor)
