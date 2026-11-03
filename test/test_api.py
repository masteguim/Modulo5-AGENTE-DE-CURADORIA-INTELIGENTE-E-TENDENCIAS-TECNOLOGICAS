
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def criar_artigo(
    titulo="Artigo de teste",
    fonte="arXiv",
    idioma="en",
):
    return {
        "titulo": titulo,
        "link": "https://example.com/artigo",
        "fonte": fonte,
        "idioma": idioma,
        "data_publicacao": "2026-11-02T12:00:00+00:00",
    }


def criar_resultado(
    artigos=None,
    fontes_indisponiveis=None,
):
    return {
        "artigos": artigos if artigos is not None else [],
        "fontes_consultadas": [
            "arXiv",
            "Tecnoblog",
            "Hacker News",
        ],
        "fontes_indisponiveis": (
            fontes_indisponiveis
            if fontes_indisponiveis is not None
            else []
        ),
    }


def test_inicio():
    resposta = client.get("/")

    assert resposta.status_code == 200
    assert resposta.json()["status"] == "online"
    assert resposta.json()["versao"] == "2.3.0"


def test_consultar_retorna_artigos(monkeypatch):
    artigos_esperados = [
        criar_artigo(
            titulo="Inteligência Artificial",
            fonte="Tecnoblog",
            idioma="pt",
        ),
    ]

    def buscar_conteudos_fake(pergunta):
        assert pergunta == "inteligência artificial"

        return criar_resultado(
            artigos=artigos_esperados
        )

    monkeypatch.setattr(
        "app.main.buscar_conteudos",
        buscar_conteudos_fake,
    )

    resposta = client.post(
        "/consultas",
        json={
            "pergunta": "inteligência artificial"
        },
    )

    assert resposta.status_code == 200

    assert resposta.json() == {
        "pergunta": "inteligência artificial",
        "artigos": artigos_esperados,
    }


def test_consultar_rejeita_pergunta_vazia():
    resposta = client.post(
        "/consultas",
        json={"pergunta": ""},
    )

    assert resposta.status_code == 422


def test_consultar_fontes_indisponiveis(monkeypatch):
    def buscar_conteudos_fake(pergunta):
        return criar_resultado(
            fontes_indisponiveis=[
                "arXiv",
                "Tecnoblog",
                "Hacker News",
            ]
        )

    monkeypatch.setattr(
        "app.main.buscar_conteudos",
        buscar_conteudos_fake,
    )

    resposta = client.post(
        "/consultas",
        json={"pergunta": "React"},
    )

    assert resposta.status_code == 502

    assert resposta.json() == {
        "detail": "Todas as fontes estão indisponíveis."
    }


def test_feed_retorna_artigos(monkeypatch):
    artigos_esperados = [
        criar_artigo(
            titulo="Novidades do Python",
            fonte="Tecnoblog",
            idioma="pt",
        ),
        {
            **criar_artigo(
                titulo="React Updates",
                fonte="React Blog",
                idioma="en",
            ),
            "link": "https://example.com/react",
        },
    ]

    def obter_feed_fake():
        return {
            **criar_resultado(
                artigos=artigos_esperados
            ),
            "total": len(artigos_esperados),
        }

    monkeypatch.setattr(
        "app.main.obter_feed",
        obter_feed_fake,
    )

    resposta = client.get("/feed")

    assert resposta.status_code == 200

    dados = resposta.json()

    assert dados["total"] == 2
    assert dados["artigos"] == artigos_esperados
    assert dados["fontes_indisponiveis"] == []


def test_feed_sem_artigos(monkeypatch):
    def obter_feed_fake():
        return {
            **criar_resultado(),
            "total": 0,
        }

    monkeypatch.setattr(
        "app.main.obter_feed",
        obter_feed_fake,
    )

    resposta = client.get("/feed")

    assert resposta.status_code == 200
    assert resposta.json()["artigos"] == []
    assert resposta.json()["total"] == 0


def test_feed_fontes_indisponiveis(monkeypatch):
    def obter_feed_fake():
        return {
            **criar_resultado(
                fontes_indisponiveis=[
                    "arXiv",
                    "Tecnoblog",
                    "Hacker News",
                ]
            ),
            "total": 0,
        }

    monkeypatch.setattr(
        "app.main.obter_feed",
        obter_feed_fake,
    )

    resposta = client.get("/feed")

    assert resposta.status_code == 502

    assert resposta.json() == {
        "detail": "Todas as fontes estão indisponíveis."
    }
