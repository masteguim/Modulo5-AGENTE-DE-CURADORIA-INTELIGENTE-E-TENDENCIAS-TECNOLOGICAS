import httpx
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

ROTA = "/integracoes/ia/perguntar"

TOKEN_TESTE = "jwt-simulado-para-testes"


def test_ia_sem_token():
    resposta = client.post(
        ROTA,
        json={"message": "Explique o Módulo 5"},
    )

    assert resposta.status_code == 401


def test_ia_token_invalido():
    resposta = client.post(
        ROTA,
        headers={
            "Authorization": "Token invalido",
        },
        json={"message": "Explique o Módulo 5"},
    )

    assert resposta.status_code == 401


def test_ia_pergunta_vazia():
    resposta = client.post(
        ROTA,
        headers={
            "Authorization": f"Bearer {TOKEN_TESTE}",
        },
        json={"message": ""},
    )

    assert resposta.status_code == 422


def test_ia_temperatura_invalida():
    resposta = client.post(
        ROTA,
        headers={
            "Authorization": f"Bearer {TOKEN_TESTE}",
        },
        json={
            "message": "Explique o projeto",
            "temperature": 2.0,
        },
    )

    assert resposta.status_code == 422


def test_ia_sucesso(monkeypatch):
    async def consultar_fake(payload, token):
        assert token == TOKEN_TESTE
        assert payload["message"] == "Explique o Módulo 5"
        assert payload["profile"] == "Desenvolvedor"

        return {
            "conversation_id": (
                "ad27df41-3746-4d26-9f5d-2be83e3a1d71"
            ),
            "message": {
                "content": "O Módulo 5 realiza curadoria.",
                "sources": [],
                "grounded": False,
            },
        }

    monkeypatch.setattr(
        "app.cliente_ia.consultar_modulo7",
        consultar_fake,
    )

    resposta = client.post(
        ROTA,
        headers={
            "Authorization": f"Bearer {TOKEN_TESTE}",
        },
        json={"message": "Explique o Módulo 5"},
    )

    assert resposta.status_code == 200
    assert resposta.json()["message"]["content"] == (
        "O Módulo 5 realiza curadoria."
    )


def test_ia_erro_autenticacao(monkeypatch):
    async def consultar_fake(payload, token):
        from fastapi import HTTPException

        raise HTTPException(
            status_code=401,
            detail="Sessão inválida.",
        )

    monkeypatch.setattr(
        "app.cliente_ia.consultar_modulo7",
        consultar_fake,
    )

    resposta = client.post(
        ROTA,
        headers={
            "Authorization": f"Bearer {TOKEN_TESTE}",
        },
        json={"message": "Teste"},
    )

    assert resposta.status_code == 401


def test_ia_timeout(monkeypatch):
    async def post_fake(self, url, **kwargs):
        raise httpx.ReadTimeout(
            "Tempo de resposta excedido.",
        )

    monkeypatch.setattr(
        httpx.AsyncClient,
        "post",
        post_fake,
    )

    resposta = client.post(
        ROTA,
        headers={
            "Authorization": f"Bearer {TOKEN_TESTE}",
        },
        json={"message": "Explique o projeto"},
    )

    assert resposta.status_code == 504
