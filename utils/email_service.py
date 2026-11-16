import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def smtp_configurado() -> bool:
    """Verifica se os parâmetros mínimos de SMTP foram fornecidos no .env."""
    servidor = os.getenv("SMTP_SERVER", "").strip()
    usuario = os.getenv("SMTP_USER", "").strip()
    senha = os.getenv("SMTP_PASSWORD", "").strip()
    return bool(servidor and usuario and senha)


def enviar_email_codigo_recuperacao(destinatario_email: str, destinatario_nome: str, codigo: str) -> tuple[bool, str]:
    """
    Envia o código OTP de 6 dígitos para o e-mail do usuário.
    Se o SMTP não estiver configurado no .env, registra no console/log
    em modo de desenvolvimento sem quebrar o fluxo.
    """
    destinatario_email = destinatario_email.strip()
    primeiro_nome = (destinatario_nome.strip().split()[0] if destinatario_nome else "Professor(a)").title()

    # Se o SMTP não estiver configurado, executa simulação para desenvolvimento/testes
    if not smtp_configurado():
        print("\n" + "=" * 65)
        print("  [SGPP SEGURANÇA] SIMULAÇÃO DE E-MAIL (SMTP NÃO CONFIGURADO)")
        print(f"  Para: {destinatario_email} ({primeiro_nome})")
        print(f"  CÓDIGO DE RECUPERAÇÃO OTP (6 DÍGITOS): >>>  {codigo}  <<<")
        print("  Validade: 15 minutos")
        print("  Para envio real, configure SMTP_SERVER, SMTP_USER e SMTP_PASSWORD no .env")
        print("=" * 65 + "\n")
        return True, "dev_mode"

    servidor_host = os.getenv("SMTP_SERVER", "").strip()
    servidor_porta = int(os.getenv("SMTP_PORT", "587"))
    usuario = os.getenv("SMTP_USER", "").strip()
    senha = os.getenv("SMTP_PASSWORD", "").strip()
    usar_tls = os.getenv("SMTP_USE_TLS", "true").lower() in ("1", "true", "yes")
    usar_ssl = os.getenv("SMTP_USE_SSL", "false").lower() in ("1", "true", "yes")
    remetente_nome = os.getenv("SMTP_FROM_NAME", "SGPP - Gestão Pedagógica").strip()
    remetente_email = os.getenv("SMTP_FROM_EMAIL", usuario).strip()

    assunto = f"{codigo} é o seu código de recuperação de senha &bull; SGPP"

    texto_plano = (
        f"Olá, {primeiro_nome}!\n\n"
        f"Recebemos uma solicitação para redefinir a senha da sua conta no SGPP.\n\n"
        f"Seu código de verificação é: {codigo}\n\n"
        f"Este código é válido por 15 minutos. Caso não tenha feito esta solicitação, "
        f"ignore este e-mail por segurança.\n\n"
        f"— Equipe SGPP"
    )

    corpo_html = f"""<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Código de Recuperação</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f4f6f9; font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, Helvetica, Arial, sans-serif; color: #212529;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color: #f4f6f9; padding: 30px 15px;">
        <tr>
            <td align="center">
                <table role="presentation" width="100%" style="max-width: 520px; background-color: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 16px rgba(0,0,0,0.06); border: 1px solid #e2e8f0;">
                    <!-- Topo / Header -->
                    <tr>
                        <td style="background: linear-gradient(135deg, #0a3871 0%, #0d6efd 100%); padding: 28px 24px; text-align: center;">
                            <h1 style="margin: 0; color: #ffffff; font-size: 24px; font-weight: 700; letter-spacing: 0.5px;">SGPP</h1>
                            <p style="margin: 4px 0 0 0; color: rgba(255,255,255,0.85); font-size: 13px;">Sistema de Gestão e Planejamento Pedagógico</p>
                        </td>
                    </tr>

                    <!-- Corpo Principal -->
                    <tr>
                        <td style="padding: 32px 28px;">
                            <h2 style="margin: 0 0 12px 0; color: #1e293b; font-size: 20px; font-weight: 600;">Olá, {primeiro_nome}!</h2>
                            <p style="margin: 0 0 18px 0; color: #475569; font-size: 15px; line-height: 1.5;">
                                Recebemos uma solicitação para redefinir a senha da sua conta de acesso ao SGPP.
                            </p>
                            <p style="margin: 0 0 10px 0; color: #475569; font-size: 14px; font-weight: 500;">
                                Utilize o código de verificação de 6 dígitos abaixo para continuar:
                            </p>

                            <!-- Bloco do Código OTP -->
                            <div style="background-color: #f8fafc; border: 2px dashed #0d6efd; border-radius: 10px; padding: 20px; text-align: center; margin: 22px 0;">
                                <span style="font-family: 'Courier New', Courier, monospace; font-size: 36px; font-weight: 800; letter-spacing: 10px; color: #0a3871; display: inline-block;">{codigo}</span>
                                <div style="margin-top: 8px; color: #dc3545; font-size: 12px; font-weight: 600;">
                                    ⏱ Código válido por 15 minutos
                                </div>
                            </div>

                            <p style="margin: 0 0 14px 0; color: #64748b; font-size: 13px; line-height: 1.5;">
                                Digite este código no formulário de redefinição de senha na tela do sistema junto com sua nova senha.
                            </p>

                            <!-- Aviso de Segurança -->
                            <div style="background-color: #fff8e1; border-left: 4px solid #f59e0b; padding: 12px 14px; border-radius: 4px; margin-top: 24px;">
                                <p style="margin: 0; color: #92400e; font-size: 12.5px; line-height: 1.4;">
                                    <strong>Atenção de segurança:</strong> Se você não solicitou a redefinição de senha, desconsidere este e-mail. Sua senha permanecerá inalterada e ninguém terá acesso sem este código.
                                </p>
                            </div>
                        </td>
                    </tr>

                    <!-- Rodapé -->
                    <tr>
                        <td style="background-color: #f8fafc; padding: 18px 24px; text-align: center; border-top: 1px solid #e2e8f0;">
                            <p style="margin: 0; color: #94a3b8; font-size: 12px;">
                                SGPP &bull; Ambiente Docente Seguro
                            </p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>"""

    mensagem = MIMEMultipart("alternative")
    mensagem["Subject"] = assunto
    mensagem["From"] = f"{remetente_nome} <{remetente_email}>"
    mensagem["To"] = destinatario_email

    mensagem.attach(MIMEText(texto_plano, "plain", "utf-8"))
    mensagem.attach(MIMEText(corpo_html, "html", "utf-8"))

    try:
        if usar_ssl:
            with smtplib.SMTP_SSL(servidor_host, servidor_porta, timeout=12) as servidor:
                servidor.login(usuario, senha)
                servidor.sendmail(remetente_email, [destinatario_email], mensagem.as_string())
        else:
            with smtplib.SMTP(servidor_host, servidor_porta, timeout=12) as servidor:
                if usar_tls:
                    servidor.starttls()
                servidor.login(usuario, senha)
                servidor.sendmail(remetente_email, [destinatario_email], mensagem.as_string())

        print(f"[EMAIL] Código OTP enviado com sucesso para: {destinatario_email}")
        return True, "enviado"
    except Exception as e:
        print(f"[EMAIL] Erro ao enviar e-mail OTP para {destinatario_email}: {e}")
        return False, str(e)
