"""
Suíte de testes automatizados para Segurança, Hash Bcrypt, Token OTP
e Política de Criação/Validação de Senha Forte (mínimo de 8 caracteres).
"""

import unittest
import uuid
from app import app
from database.conexao import get_cursor, release_cursor
from utils.security import (
    TAMANHO_MINIMO_SENHA,
    avaliar_forca_senha,
    validar_forca_senha,
    gerar_hash_senha,
    verificar_senha,
    redefinir_senha_usuario,
    solicitar_codigo_otp,
    redefinir_senha_com_otp,
)


class TestSegurancaESenhaForte(unittest.TestCase):

    def setUp(self):
        self.client = app.test_client()
        self.app_context = app.app_context()
        self.app_context.push()
        self.emails_teste = []

    def tearDown(self):
        if self.emails_teste:
            conn, cur = get_cursor()
            try:
                for email in self.emails_teste:
                    cur.execute("DELETE FROM usuarios WHERE LOWER(email) = LOWER(%s)", (email,))
                conn.commit()
            finally:
                release_cursor(conn, cur)
        self.app_context.pop()

    def _gerar_email_unico(self) -> str:
        email = f"teste_sec_{uuid.uuid4().hex[:8]}@senai.br"
        self.emails_teste.append(email)
        return email

    # ============================================================
    # 1. Testes Unitários de Validação de Força de Senha
    # ============================================================

    def test_01_rejeitar_senhas_menores_que_8_caracteres(self):
        """Não deve aceitar nenhuma senha com menos de 8 caracteres."""
        self.assertEqual(TAMANHO_MINIMO_SENHA, 8)
        senhas_curtas = [
            "",
            "123",
            "abc",
            "123456",
            "1234567",
            "Ab1@56",    # 6 chars mesmo tendo todos os tipos
            "Ab1@567",   # 7 chars mesmo tendo todos os tipos
        ]
        for s in senhas_curtas:
            valida, msg = validar_forca_senha(s)
            self.assertFalse(valida, f"A senha curta '{s}' (len={len(s)}) deveria ser rejeitada.")
            self.assertIn("8 caracteres", msg)

    def test_02_rejeitar_senhas_fracas_com_8_ou_mais_caracteres(self):
        """Não deve aceitar senhas fracas mesmo que tenham 8 ou mais caracteres."""
        senhas_fracas = [
            "12345678",       # Apenas números
            "1234567890",     # Apenas números (10 chars)
            "abcdefgh",       # Apenas minúsculas
            "ABCDEFGH",       # Apenas maiúsculas
            "aaaaaaaa",       # Caracteres repetidos
            "@@@@@@@@",       # Especiais repetidos
            "senha1234",      # Sem maiúscula e sem especial
            "Senha1234",      # Sem caractere especial
            "senha@123",      # Sem letra maiúscula
            "SENHA@123",      # Sem letra minúscula
            "SenhaForte@",    # Sem número
        ]
        for s in senhas_fracas:
            valida, msg = validar_forca_senha(s)
            self.assertFalse(valida, f"A senha fraca '{s}' deveria ser rejeitada.")
            self.assertIn("Senha fraca", msg)

    def test_03_aceitar_senhas_fortes_validas(self):
        """Deve aceitar senhas com >= 8 caracteres e todos os requisitos de complexidade."""
        senhas_fortes = [
            "Senha@123",
            "Docente#2026",
            "Sgpp$Forte99",
            "Abcdef1!",
            "Planejamento_2026*",
        ]
        for s in senhas_fortes:
            valida, msg = validar_forca_senha(s)
            self.assertTrue(valida, f"A senha forte '{s}' deveria ser aceita, mas falhou: {msg}")
            avaliacao = avaliar_forca_senha(s)
            self.assertTrue(avaliacao["valida"])
            self.assertEqual(avaliacao["pontuacao"], 5)
            self.assertIn(avaliacao["nivel"], ("Forte", "Muito forte"))

    # ============================================================
    # 2. Testes de Hash Bcrypt de Senha
    # ============================================================

    def test_04_hash_bcrypt_e_verificacao(self):
        """Verifica se o hash gerado utiliza Bcrypt ($2b$12$) e valida corretamente."""
        senha = "SenhaForte@2026"
        hash_gerado = gerar_hash_senha(senha)
        self.assertTrue(hash_gerado.startswith("$2b$12$"))
        self.assertNotEqual(hash_gerado, senha)
        self.assertTrue(verificar_senha(senha, hash_gerado))
        self.assertFalse(verificar_senha("SenhaErrada@2026", hash_gerado))

    # ============================================================
    # 3. Testes de Rotas Flask: /cadastro, /login, /api/validar_senha
    # ============================================================

    def test_05_api_validar_senha(self):
        """Testa o endpoint JSON /api/validar_senha."""
        resp_fraca = self.client.post("/api/validar_senha", json={"senha": "12345"})
        self.assertEqual(resp_fraca.status_code, 200)
        dados_fraca = resp_fraca.get_json()
        self.assertFalse(dados_fraca["valida"])
        self.assertFalse(dados_fraca["requisitos"]["tamanho_minimo"])

        resp_forte = self.client.post("/api/validar_senha", json={"senha": "Professor@2026"})
        self.assertEqual(resp_forte.status_code, 200)
        dados_forte = resp_forte.get_json()
        self.assertTrue(dados_forte["valida"])
        self.assertEqual(dados_forte["pontuacao"], 5)

    def test_06_cadastro_bloqueia_senha_curta_e_fraca_e_aceita_forte(self):
        """Testa a rota /cadastro bloqueando senhas < 8 chars e senhas fracas, e aceitando senha forte."""
        email = self._gerar_email_unico()

        # 1) Senha com menos de 8 caracteres
        r1 = self.client.post("/cadastro", data={
            "nome": "Prof Teste",
            "email": email,
            "senha": "12345",
            "confirmar_senha": "12345",
        })
        self.assertEqual(r1.status_code, 200)
        self.assertIn("8 caracteres", r1.get_data(as_text=True))

        # 2) Senha de 8 caracteres porém fraca (sem maiúscula/especial)
        r2 = self.client.post("/cadastro", data={
            "nome": "Prof Teste",
            "email": email,
            "senha": "senha1234",
            "confirmar_senha": "senha1234",
        })
        self.assertEqual(r2.status_code, 200)
        self.assertIn("Senha fraca", r2.get_data(as_text=True))

        # 3) Confirmação de senha divergente
        r3 = self.client.post("/cadastro", data={
            "nome": "Prof Teste",
            "email": email,
            "senha": "SenhaForte@2026",
            "confirmar_senha": "OutraSenha@2026",
        })
        self.assertEqual(r3.status_code, 200)
        self.assertIn("não confere", r3.get_data(as_text=True))

        # 4) Cadastro com senha forte válida
        r4 = self.client.post("/cadastro", data={
            "nome": "Prof Teste",
            "email": email,
            "senha": "SenhaForte@2026",
            "confirmar_senha": "SenhaForte@2026",
        })
        self.assertEqual(r4.status_code, 302)
        self.assertIn("/login", r4.headers["Location"])

        # Verifica no banco que a senha foi salva com hash bcrypt
        conn, cur = get_cursor()
        try:
            cur.execute("SELECT id, senha FROM usuarios WHERE email = %s", (email,))
            row = cur.fetchone()
            self.assertIsNotNone(row)
            self.assertTrue(row[1].startswith("$2b$12$"))
        finally:
            release_cursor(conn, cur)

        # 5) Login com a senha cadastrada
        r_login = self.client.post("/login", data={
            "email": email,
            "senha": "SenhaForte@2026",
        })
        self.assertEqual(r_login.status_code, 302)
        self.assertIn("/dashboard", r_login.headers["Location"])

    # ============================================================
    # 4. Testes de Alterar Senha (/alterar_senha) e Admin
    # ============================================================

    def test_07_alterar_senha_usuario_logado(self):
        """Testa a rota /alterar_senha exigindo mínimo 8 caracteres e senha forte."""
        email = self._gerar_email_unico()
        senha_inicial = "Inicial@2026"

        # Cria usuário
        self.client.post("/cadastro", data={
            "nome": "Docente Alteracao",
            "email": email,
            "senha": senha_inicial,
            "confirmar_senha": senha_inicial,
        })

        conn, cur = get_cursor()
        try:
            cur.execute("SELECT id FROM usuarios WHERE email = %s", (email,))
            user_id = cur.fetchone()[0]
        finally:
            release_cursor(conn, cur)

        with self.client.session_transaction() as sess:
            sess["usuario_id"] = user_id
            sess["nome"] = "Docente Alteracao"
            sess["perfil"] = "professor"

        # Tenta alterar para senha curta (< 8)
        r_curta = self.client.post("/alterar_senha", data={
            "senha_atual": senha_inicial,
            "nova_senha": "Ab1@5",
            "confirmar_senha": "Ab1@5",
        })
        self.assertIn("8 caracteres", r_curta.get_data(as_text=True))

        # Tenta alterar para senha fraca (8 chars apenas números)
        r_fraca = self.client.post("/alterar_senha", data={
            "senha_atual": senha_inicial,
            "nova_senha": "12345678",
            "confirmar_senha": "12345678",
        })
        self.assertIn("Senha fraca", r_fraca.get_data(as_text=True))

        # Altera para senha forte válida
        nova_forte = "NovaForte#2026"
        r_ok = self.client.post("/alterar_senha", data={
            "senha_atual": senha_inicial,
            "nova_senha": nova_forte,
            "confirmar_senha": nova_forte,
        })
        self.assertIn("alterada com sucesso", r_ok.get_data(as_text=True))

        # Verifica no banco
        conn, cur = get_cursor()
        try:
            cur.execute("SELECT senha FROM usuarios WHERE id = %s", (user_id,))
            hash_banco = cur.fetchone()[0]
            self.assertTrue(verificar_senha(nova_forte, hash_banco))
        finally:
            release_cursor(conn, cur)

    # ============================================================
    # 5. Testes do Fluxo OTP (Token com Hash + Redefinição de Senha)
    # ============================================================

    def test_08_fluxo_otp_hash_token_e_validacao_senha_forte(self):
        """Verifica que o token OTP é salvo com hash no banco e exige senha forte na redefinição."""
        email = self._gerar_email_unico()
        self.client.post("/cadastro", data={
            "nome": "Docente OTP",
            "email": email,
            "senha": "Antiga@2026",
            "confirmar_senha": "Antiga@2026",
        })

        # Solicita código OTP
        sucesso_otp, msg_otp, info_otp = solicitar_codigo_otp(email)
        self.assertTrue(sucesso_otp, f"Falha ao gerar OTP: {msg_otp}")
        codigo_gerado = info_otp.get("codigo_dev")
        self.assertIsNotNone(codigo_gerado)
        self.assertEqual(len(codigo_gerado), 6)

        # Verifica no banco que o código OTP foi salvo com hash bcrypt ($2b$12$), não em texto puro!
        conn, cur = get_cursor()
        try:
            cur.execute(
                """
                SELECT cr.codigo
                FROM codigos_recuperacao cr
                JOIN usuarios u ON u.id = cr.usuario_id
                WHERE u.email = %s AND cr.usado = FALSE
                ORDER BY cr.criado_em DESC LIMIT 1
                """,
                (email,)
            )
            row = cur.fetchone()
            self.assertIsNotNone(row)
            codigo_no_banco = row[0]
            self.assertTrue(codigo_no_banco.startswith("$2b$12$"), "O código OTP deve estar com hash Bcrypt no banco.")
            self.assertNotEqual(codigo_no_banco, codigo_gerado)
        finally:
            release_cursor(conn, cur)

        # Tenta redefinir com OTP válido mas senha curta (< 8 chars)
        ok_curta, msg_curta = redefinir_senha_com_otp(email, codigo_gerado, "Curta1@", "Curta1@")
        self.assertFalse(ok_curta)
        self.assertIn("8 caracteres", msg_curta)

        # Tenta redefinir com OTP válido mas senha fraca
        ok_fraca, msg_fraca = redefinir_senha_com_otp(email, codigo_gerado, "12345678", "12345678")
        self.assertFalse(ok_fraca)
        self.assertIn("Senha fraca", msg_fraca)

        # Redefine com OTP válido e senha forte
        ok_forte, msg_forte = redefinir_senha_com_otp(email, codigo_gerado, "Redefinida#2026", "Redefinida#2026")
        self.assertTrue(ok_forte, f"Deveria redefinir com sucesso, mas retornou: {msg_forte}")

    def test_09_paginas_auth_minimalistas_e_responsivas_sem_imagem_antiga(self):
        """Verifica se Login, Cadastro e Redefinir Senha renderizam o novo layout sem computador.png."""
        for rota in ("/login", "/cadastro", "/redefinir_senha"):
            resp = self.client.get(rota)
            self.assertEqual(resp.status_code, 200, f"Falha ao carregar {rota}")
            html = resp.get_data(as_text=True)
            self.assertNotIn("computador.png", html, f"A imagem antiga não deve aparecer em {rota}")
            self.assertIn("sgpp-auth", html)
            self.assertIn("sgpp-form", html)
            self.assertIn("js/senha.js", html)

    def test_10_pagina_planos_sem_emojis_e_sem_suporte_vip_ou_humanizado(self):
        """Verifica se /precos não exibe estrela, troféu, suporte VIP 24h ou atendimento humanizado."""
        resp = self.client.get("/precos")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertNotIn("⭐", html)
        self.assertNotIn("🏆", html)
        self.assertNotIn("VIP 24h", html)
        self.assertNotIn("humanizado", html.lower())

    def test_11_sistema_sem_admin_apenas_professor(self):
        """Verifica que rotas administrativas não existem mais e usuários possuem apenas perfil professor."""
        for rota_admin in ("/usuarios", "/admin/redefinir_senha/1", "/admin/alterar_perfil/1", "/admin/deletar_usuario/1"):
            r_get = self.client.get(rota_admin)
            r_post = self.client.post(rota_admin)
            self.assertEqual(r_get.status_code, 404, f"A rota {rota_admin} deveria retornar 404.")
            self.assertEqual(r_post.status_code, 404, f"A rota POST {rota_admin} deveria retornar 404.")


if __name__ == "__main__":
    unittest.main()
