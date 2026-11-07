import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

CAMINHO_BANCO = Path(
    os.getenv(
        "CURADORIA_DB_PATH",
        str(
            Path(__file__).resolve().parent.parent
            / "curadoria.db"
        ),
    )
)


@contextmanager
def conectar():
    CAMINHO_BANCO.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    conexao = sqlite3.connect(
        CAMINHO_BANCO,
        timeout=30,
    )

    conexao.row_factory = sqlite3.Row

    try:
        yield conexao
        conexao.commit()
    except Exception:
        conexao.rollback()
        raise
    finally:
        conexao.close()


def inicializar_banco():
    with conectar() as conexao:
        conexao.execute("""
            CREATE TABLE IF NOT EXISTS artigos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                titulo TEXT NOT NULL,
                link TEXT NOT NULL UNIQUE,
                fonte TEXT NOT NULL,
                idioma TEXT DEFAULT 'en',
                resumo TEXT DEFAULT '',
                data_publicacao TEXT,
                coletado_em TEXT NOT NULL
            )
        """)

        conexao.execute("""
            CREATE INDEX IF NOT EXISTS
            idx_artigos_publicacao
            ON artigos(data_publicacao)
        """)


def salvar_artigo(artigo):
    titulo = artigo.get("titulo", "").strip()
    link = artigo.get("link", "").strip()

    if not titulo or not link.startswith("https://"):
        return False

    data_coleta = datetime.now(
        timezone.utc
    ).isoformat()

    with conectar() as conexao:
        cursor = conexao.execute(
            """
            INSERT OR IGNORE INTO artigos (
                titulo,
                link,
                fonte,
                idioma,
                resumo,
                data_publicacao,
                coletado_em
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                titulo,
                link,
                artigo.get("fonte", "Desconhecida"),
                artigo.get("idioma", "en"),
                artigo.get("resumo", ""),
                artigo.get("data_publicacao"),
                data_coleta,
            ),
        )

        return cursor.rowcount > 0


def salvar_artigos(artigos):
    novos = 0

    for artigo in artigos:
        if salvar_artigo(artigo):
            novos += 1

    return {
        "recebidos": len(artigos),
        "novos": novos,
        "duplicados_ou_invalidos": len(artigos) - novos,
    }


def listar_artigos(limite=50):
    limite = max(1, min(int(limite), 500))

    with conectar() as conexao:
        cursor = conexao.execute(
            """
            SELECT
                id,
                titulo,
                link,
                fonte,
                idioma,
                resumo,
                data_publicacao,
                coletado_em
            FROM artigos
            ORDER BY
                COALESCE(data_publicacao, coletado_em) DESC
            LIMIT ?
            """,
            (limite,),
        )

        return [
            dict(linha)
            for linha in cursor.fetchall()
        ]


def contar_artigos():
    with conectar() as conexao:
        cursor = conexao.execute(
            "SELECT COUNT(*) FROM artigos"
        )

        return cursor.fetchone()[0]


def buscar_artigos_por_termo(termo, limite=50):
    limite = max(1, min(int(limite), 500))
    termo = f"%{termo.strip()}%"

    with conectar() as conexao:
        cursor = conexao.execute(
            """
            SELECT *
            FROM artigos
            WHERE titulo LIKE ?
               OR resumo LIKE ?
            ORDER BY
                COALESCE(data_publicacao, coletado_em) DESC
            LIMIT ?
            """,
            (termo, termo, limite),
        )

        return [
            dict(linha)
            for linha in cursor.fetchall()
        ]
