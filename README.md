# 🎓 SGPP — Sistema de Gestão e Planejamento Pedagógico

O **SGPP** (Sistema de Gestão e Planejamento Pedagógico) é uma plataforma web completa e moderna desenvolvida para docentes e coordenadores pedagógicos (com foco nas metodologias SENAI / redes de ensino técnico e profissionalizante). O sistema automatiza a criação de **atividades avaliativas**, **planos de aula**, **planejamentos docentes com Taxonomia de Bloom** e gerencia um **repositório compartilhado de questões**, utilizando Inteligência Artificial (Ollama / LLaMA 3.1, Gemini, OpenAI) com suporte multiusuário em rede local ou nuvem.

---

## ✨ Funcionalidades Principais

| Módulo | Descrição |
|--------|-----------|
| 🌐 **Landing Page & Painel** | Apresentação institucional, estatísticas em tempo real e acesso rápido aos módulos |
| 🗄️ **Repositório de Questões** | Banco de questões autorais (professor) e de IA, com busca, filtros (origem, tipo, Bloom) e visualização de folha com cabeçalho oficial |
| 🧠 **Gerador de Atividades Híbrido** | Montagem de avaliações a partir do repositório interno e/ou complementação inteligente sob demanda via IA |
| 📋 **Planos de Aula Estruturados** | Geração e desdobramento de encontros a partir de PDFs (Plano de Curso) ou Matrizes SAEP / Excel |
| 📊 **Planejamento Docente (Bloom)** | Geração automática da planilha Excel oficial SENAI e Word com capacidades e níveis progressivos da Taxonomia de Bloom |
| 👁️ **Visualização & Impressão** | Pré-visualização de atividades no padrão oficial com cabeçalho de identificação e modo de impressão limpo (`@media print`) |
| 📥 **Exportação Oficial** | Download de documentos formatados em Word (.docx), PDF e planilhas Excel (.xlsx) |
| 🔐 **Segurança & Perfis** | Criptografia Bcrypt (salt=12), redefinição de senha segura via token/e-mail e níveis de acesso (`professor` e `admin`) |

---

## 🏗️ Estrutura do Projeto

```
gerador_atividades/
│
├── app.py                             # Rotas Flask, controle de sessão e endpoints
├── iniciar_servidor.py                # Inicialização de produção com Waitress (WSGI)
├── iniciar.bat / iniciar.sh           # Scripts de inicialização rápida
├── .env                               # Variáveis de ambiente (ignorado no git)
├── .env.example                       # Modelo de configuração para implantação
├── requirements.txt                   # Dependências do ecossistema Python
│
├── database/
│   ├── conexao.py                     # Pool de conexões PostgreSQL thread-safe
│   ├── script_banco.sql               # Esquema das tabelas principais
│   └── criar_banco_completo.sql       # Script completo para instalação inicial
│
├── ia/
│   ├── gerador.py                     # Motor de geração de avaliações via IA
│   ├── plano_aula.py                  # Geração de planos de aula diários
│   └── planejamento_bloom.py          # Lógica da Taxonomia de Bloom progressiva
│
├── utils/
│   ├── repositorio_service.py         # CRUD, busca e parsing de itens do repositório
│   ├── docx_atividade_generator.py    # Geração de avaliações em Word no layout institucional
│   ├── docx_planejamento_generator.py # Geração de planejamento em Word
│   ├── pdf_atividade_generator.py     # Geração de PDF via ReportLab e docx2pdf
│   ├── excel_planejamento_generator.py# Geração da planilha Excel de Planejamento Docente
│   ├── security.py                    # Hash e verificação de senhas com Bcrypt
│   └── email_service.py               # Envio de e-mails de recuperação de senha
│
├── templates/                         # Templates HTML com Bootstrap 5 e ícones
│   ├── base.html                      # Layout base e navbar do SGPP
│   ├── landing.html                   # Landing page institucional
│   ├── dashboard.html                 # Painel com métricas e atalhos
│   ├── repositorio.html               # Banco de questões com filtros e ações
│   ├── visualizar_atividade_repositorio.html # Visualização de folha com cabeçalho oficial
│   ├── atividades.html                # Lista e histórico de atividades geradas
│   ├── index.html                     # Formulário de criação de atividades (híbrido/IA)
│   ├── planejamento_docente.html      # Formulário e geração do planejamento docente
│   ├── planos_curso.html              # Planos de aula por curso e unidade curricular
│   └── login.html / cadastro.html     # Autenticação e gestão de usuários
│
├── static/                            # Arquivos estáticos (CSS customizado, imagens e logos)
├── uploads/                           # Upload temporário de matrizes SAEP e PDFs
└── outputs/                           # Documentos finais gerados (Word, PDF, Excel)
```

---

## ⚙️ Requisitos do Sistema

- **Python**: versão 3.10 ou superior (recomendado 3.11+)
- **PostgreSQL**: versão 14+
- **Ollama** com o modelo `llama3.1:8b` (para processamento de IA local)
- **Sistema Operacional**: Windows 10/11 ou Linux Server

---

## 🚀 Instalação e Configuração

### 1. Clonar o Repositório

```bash
git clone https://github.com/ronan-ferreira/gerador_atividades.git
cd gerador_atividades
```

### 2. Criar e Ativar o Ambiente Virtual

No Windows (PowerShell):
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

No Linux/macOS:
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Instalar as Dependências

```bash
pip install -r requirements.txt
```

### 4. Configurar o Banco de Dados (PostgreSQL)

Crie o banco de dados via pgAdmin ou terminal `psql`:

```sql
CREATE DATABASE gerador_atividades;
```

Execute o script de estruturação das tabelas:
```powershell
psql -U postgres -d gerador_atividades -f database/script_banco.sql
```

### 5. Configurar as Variáveis de Ambiente

Copie o arquivo de exemplo `.env.example` para `.env`:

```powershell
copy .env.example .env
```

Edite o arquivo `.env` com os dados do seu ambiente:

```env
# Banco de Dados
DB_HOST=127.0.0.1
DB_PORT=5432
DB_NAME=gerador_atividades
DB_USER=postgres
DB_PASSWORD=sua_senha_aqui

# Chave secreta da sessão Flask
FLASK_SECRET_KEY=sua_chave_secreta_aqui

# Provedor de IA (Ollama Local)
OLLAMA_URL=http://localhost:11434

# Servidor Web
SERVER_HOST=0.0.0.0
SERVER_PORT=5000
SERVER_THREADS=4
```

### 6. Modelo de IA Local (Ollama)

Certifique-se de que o Ollama está em execução e baixe o modelo LLaMA 3.1:

```powershell
ollama pull llama3.1:8b
```

### 7. Executar a Aplicação

Para iniciar o servidor corporativo com **Waitress**:
```powershell
python iniciar_servidor.py
```
*(ou execute o script `iniciar.bat` no Windows)*

Acesse no navegador: **http://localhost:5000**

---

## 🌐 Acesso em Rede Local (Multi-Docente)

O SGPP foi arquitetado para suportar múltiplos professores conectados simultaneamente na rede da unidade escolar:

1. Inicie o servidor no computador principal:
   ```powershell
   python iniciar_servidor.py
   ```
2. Obtenha o endereço IP local do computador servidor através do comando `ipconfig` (ex: `192.168.1.100`).
3. Os demais professores podem acessar pelo navegador em seus computadores ou notebooks usando:
   ```
   http://192.168.1.100:5000
   ```

- **Waitress WSGI**: processamento concorrente em múltiplas threads.
- **Pool Thread-Safe**: até 20 conexões simultâneas com o PostgreSQL.
- **Isolamento de Dados**: cada professor visualiza e edita apenas seus próprios itens cadastrados.

---

## 📄 Licença e Uso

Sistema desenvolvido para apoio pedagógico e produtividade docente no âmbito da Educação Profissional e Tecnológica (SENAI).
Todos os direitos reservados.
