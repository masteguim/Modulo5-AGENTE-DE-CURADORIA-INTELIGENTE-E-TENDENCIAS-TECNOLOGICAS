from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_consultar_retorna_artigos(monkeypatch):
    artigos_esperados = [
        {
            "titulo": "Artigo de teste",
            "link": "https://arxiv.org/abs/1234.5678",
        }
    ]

    def buscar_artigos_fake(pergunta: str):
        assert pergunta == "computação quântica"
        return artigos_esperados

    monkeypatch.setattr("app.main.buscar_artigos", buscar_artigos_fake)

    resposta = client.post(
        "/consultas",
        json={"pergunta": "computação quântica"},
    )

    assert resposta.status_code == 200
    assert resposta.json() == {
        "pergunta": "computação quântica",
        "artigos": artigos_esperados,
    }


def test_consultar_rejeita_pergunta_vazia():
    resposta = client.post(
        "/consultas",
        json={"pergunta": ""},
    )

    assert resposta.status_code == 422