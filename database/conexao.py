import os
import psycopg2
from psycopg2 import pool
from dotenv import load_dotenv

# Carrega variáveis do arquivo .env (na raiz do projeto)
load_dotenv()

# Pool de conexões para suportar múltiplos usuários simultâneos
# Configuração via .env — sem credenciais fixas no código
conexao_pool = psycopg2.pool.ThreadedConnectionPool(
    minconn=2,
    maxconn=20,  # Aumentado para suportar mais professores simultâneos
    host=os.getenv("DB_HOST", "127.0.0.1"),
    port=os.getenv("DB_PORT", "5432"),
    dbname=os.getenv("DB_NAME", "gerador_atividades"),
    user=os.getenv("DB_USER", "postgres"),
    password=os.getenv("DB_PASSWORD", "123")
)


def get_cursor():
    """Retorna uma conexão e cursor do pool thread-safe"""
    conn = conexao_pool.getconn()
    conn.autocommit = True
    cursor = conn.cursor()
    return conn, cursor


def release_cursor(conn, cursor):
    """Devolve a conexão ao pool"""
    if cursor:
        cursor.close()
    if conn:
        conexao_pool.putconn(conn)


def _executar_migracoes_iniciais():
    """Garante que novas tabelas e colunas existam no banco sem necessidade de intervenção manual."""
    try:
        conn = conexao_pool.getconn()
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute("""
            ALTER TABLE planejamentos_docente ADD COLUMN IF NOT EXISTS modalidade VARCHAR(100);
            ALTER TABLE planejamentos_docente ADD COLUMN IF NOT EXISTS curso_id INTEGER REFERENCES cursos_plano(id) ON DELETE SET NULL;
            ALTER TABLE planos_aula ADD COLUMN IF NOT EXISTS planejamento_id INTEGER REFERENCES planejamentos_docente(id) ON DELETE SET NULL;
            ALTER TABLE atividades ADD COLUMN IF NOT EXISTS origem VARCHAR(100) DEFAULT 'ia';
            ALTER TABLE atividades ALTER COLUMN conteudo TYPE TEXT;
            ALTER TABLE atividades ALTER COLUMN origem TYPE VARCHAR(100);

            CREATE TABLE IF NOT EXISTS repositorio_atividades (
                id SERIAL PRIMARY KEY,
                curso VARCHAR(150) NOT NULL,
                disciplina VARCHAR(150) NOT NULL,
                conteudo TEXT NOT NULL,
                dificuldade VARCHAR(50) NOT NULL DEFAULT 'médio',
                tipo VARCHAR(50) NOT NULL DEFAULT 'objetiva',
                enunciado TEXT NOT NULL,
                alternativas TEXT,
                resposta_correta TEXT,
                origem VARCHAR(50) NOT NULL DEFAULT 'professor',
                usuario_id INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
                data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            ALTER TABLE repositorio_atividades ALTER COLUMN conteudo TYPE TEXT;
            ALTER TABLE repositorio_atividades ALTER COLUMN origem TYPE VARCHAR(50);
            ALTER TABLE repositorio_atividades ALTER COLUMN tipo TYPE VARCHAR(50);

            CREATE INDEX IF NOT EXISTS idx_repositorio_curso ON repositorio_atividades(curso);
            CREATE INDEX IF NOT EXISTS idx_repositorio_disciplina ON repositorio_atividades(disciplina);
            CREATE INDEX IF NOT EXISTS idx_repositorio_usuario ON repositorio_atividades(usuario_id);
            CREATE INDEX IF NOT EXISTS idx_repositorio_origem ON repositorio_atividades(origem);
            CREATE INDEX IF NOT EXISTS idx_repositorio_dificuldade ON repositorio_atividades(dificuldade);
            CREATE INDEX IF NOT EXISTS idx_repositorio_tipo ON repositorio_atividades(tipo);

            CREATE TABLE IF NOT EXISTS codigos_recuperacao (
                id SERIAL PRIMARY KEY,
                usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
                codigo VARCHAR(255) NOT NULL,
                tentativas INTEGER NOT NULL DEFAULT 0,
                usado BOOLEAN NOT NULL DEFAULT FALSE,
                criado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                expira_em TIMESTAMP NOT NULL
            );

            ALTER TABLE codigos_recuperacao ALTER COLUMN codigo TYPE VARCHAR(255);

            CREATE INDEX IF NOT EXISTS idx_codigos_recuperacao_user ON codigos_recuperacao(usuario_id, usado, expira_em);

            ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS tutorial_visto BOOLEAN DEFAULT FALSE;

            UPDATE usuarios SET perfil = 'professor' WHERE perfil != 'professor';
        """)
        cur.close()
        conexao_pool.putconn(conn)
    except Exception as e:
        print(f"[BD] Aviso na verificação de migrações: {e}")


# Executa checagem de colunas na inicialização
_executar_migracoes_iniciais()

