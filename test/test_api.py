
import json

import pytest
from fastapi.testclient import TestClient

from app.auth import AuthenticatedUser, get_current_user
from app.main import app
from app.recomendacoes import selecionar_recomendacoes

client = TestClient(app)


@pytest.fixture(autouse=True)
def usuario_autenticado():
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        subject="usuario-teste",
        access_token="token-teste",
        profile={
            "id": "id-teste",
            "email": "teste@example.com",
            "display_name": "Usuário de teste",
            "is_active": True,
        },
    )
    yield
    app.dependency_overrides.pop(get_current_user, None)


def criar_artigo(numero=1, idioma="en", fonte="arXiv"):
    return {
        "titulo": f"React and software article {numero}",
        "link": f"https://example.com/artigo-{numero}",
        "fonte": fonte,
        "idioma": idioma,
        "data_publicacao": "2026-11-02T12:00:00+00:00",
    }


def criar_resultado(artigos=None):
    return {
        "artigos": artigos if artigos is not None else [],
        "fontes_consultadas": ["arXiv", "Tecnoblog"],
        "fontes_indisponiveis": [],
    }


def test_inicio(monkeypatch):
    monkeypatch.setattr(
        "app.main.contar_artigos",
        lambda: 0,
    )

    resposta = client.get("/")

    assert resposta.status_code == 200
    assert resposta.json()["versao"] == "3.4.0"
    assert resposta.json()["status"] == "online"
    assert resposta.json()["artigos_armazenados"] == 0


def test_login_repassa_formulario_ao_modulo1(monkeypatch):
    chamadas = {}

    def requisitar(metodo, url, **kwargs):
        chamadas.update(metodo=metodo, url=url, **kwargs)
        return type(
            "Resposta",
            (),
            {
                "status_code": 200,
                "json": lambda _self: {
                    "access_token": "token-teste",
                    "expires_in": 300,
                },
            },
        )()

    monkeypatch.setattr("app.auth.httpx.request", requisitar)
    resposta = client.post(
        "/auth/login",
        json={"username": "teste@example.com", "password": "senha-teste"},
    )

    assert resposta.status_code == 200
    assert resposta.json()["access_token"] == "token-teste"
    assert chamadas["url"].endswith("/auth/token")
    assert chamadas["data"] == {
        "username": "teste@example.com",
        "password": "senha-teste",
    }


def test_mfa_encaminha_um_codigo_de_verificacao(monkeypatch):
    chamadas = {}

    def requisitar(metodo, url, **kwargs):
        chamadas.update(metodo=metodo, url=url, **kwargs)
        return type(
            "Resposta",
            (),
            {
                "status_code": 200,
                "json": lambda _self: {"access_token": "token-teste"},
            },
        )()

    monkeypatch.setattr("app.auth.httpx.request", requisitar)
    resposta = client.post(
        "/auth/mfa/verify",
        json={"challenge_token": "desafio", "code": "123456"},
    )

    assert resposta.status_code == 200
    assert chamadas["json"] == {
        "challenge_token": "desafio",
        "code": "123456",
    }


def test_mfa_rejeita_codigo_e_codigo_de_recuperacao_juntos():
    resposta = client.post(
        "/auth/mfa/verify",
        json={
            "challenge_token": "desafio",
            "code": "123456",
            "recovery_code": "recuperacao",
        },
    )

    assert resposta.status_code == 422


def test_sessao_atual_retorna_apenas_perfil_da_conta():
    resposta = client.get("/auth/session")

    assert resposta.status_code == 200
    assert resposta.json() == {
        "id": "id-teste",
        "email": "teste@example.com",
        "display_name": "Usuário de teste",
        "is_active": True,
    }


def test_logout_preserva_resposta_204_do_modulo1(monkeypatch):
    chamadas = {}

    def requisitar(metodo, url, **kwargs):
        chamadas.update(metodo=metodo, url=url, **kwargs)
        return type(
            "Resposta",
            (),
            {
                "status_code": 204,
                "json": lambda _self: (_ for _ in ()).throw(
                    AssertionError("204 não deve ser decodificado como JSON")
                ),
            },
        )()

    monkeypatch.setattr("app.auth.httpx.request", requisitar)
    resposta = client.post("/auth/logout")

    assert resposta.status_code == 204
    assert resposta.content == b""
    assert chamadas["headers"]["Authorization"] == "Bearer token-teste"
    assert chamadas["json"] == {}


def test_consultar(monkeypatch):
    artigo = criar_artigo()
    persistencia = {}

    def buscar_fake(pergunta):
        assert pergunta == "React"
        return criar_resultado([artigo])

    monkeypatch.setattr(
        "app.main.buscar_conteudos",
        buscar_fake,
    )
    monkeypatch.setattr(
        "app.main.registrar_consulta",
        lambda **kwargs: persistencia.update(kwargs) or 12,
    )

    resposta = client.post(
        "/consultas",
        json={"pergunta": "React"},
    )

    assert resposta.status_code == 200
    assert resposta.json()["artigos"] == [artigo]
    assert resposta.json()["chat_id"] == 12
    assert persistencia["subject"] == "usuario-teste"
    assert json.loads(persistencia["resposta"]) == [artigo]


def test_pergunta_vazia():
    resposta = client.post(
        "/consultas",
        json={"pergunta": ""},
    )

    assert resposta.status_code == 422


def test_consulta_exige_autenticacao():
    app.dependency_overrides.pop(get_current_user)

    resposta = client.post(
        "/consultas",
        json={"pergunta": "React"},
    )

    assert resposta.status_code == 401


def test_consulta_fontes_indisponiveis(monkeypatch):
    def buscar_fake(pergunta):
        assert pergunta == "React"
        return {
            **criar_resultado(),
            "fontes_indisponiveis": [
                "arXiv",
                "Tecnoblog",
            ],
        }

    monkeypatch.setattr(
        "app.main.buscar_conteudos",
        buscar_fake,
    )

    resposta = client.post(
        "/consultas",
        json={"pergunta": "React"},
    )

    assert resposta.status_code == 502


def test_assistente_persiste_conversa(monkeypatch):
    chamadas = {}
    persistencia = {}

    def perguntar(**kwargs):
        chamadas.update(kwargs)
        return {
            "conversation_id": "m7-chat-1",
            "message": {
                "content": "Resposta do assistente",
                "sources": [],
                "grounded": False,
                "mode": "general",
            },
        }

    monkeypatch.setattr(
        "app.main.perguntar_ao_modulo7",
        perguntar,
    )
    monkeypatch.setattr(
        "app.main.registrar_resposta_assistente",
        lambda **kwargs: persistencia.update(kwargs) or 23,
    )

    resposta = client.post(
        "/assistente",
        json={"pergunta": "Explique a stack"},
    )

    assert resposta.status_code == 200
    assert resposta.json()["chat_id"] == 23
    assert resposta.json()["conversation_id"] == "m7-chat-1"
    assert chamadas["usuario"].subject == "usuario-teste"
    assert chamadas["conversation_id"] is None
    assert json.loads(persistencia["resposta"]) == resposta.json()["message"]


def test_assistente_verifica_acesso_e_continua_conversa(monkeypatch):
    from uuid import UUID

    project_id = UUID("7a1d0f4e-2b6c-4c1e-9f3a-5d8e7c6b4a01")
    chamadas = {}

    monkeypatch.setattr(
        "app.main.obter_contexto_conversa",
        lambda _subject, _chat_id: {
            "id_chat": 23,
            "project_id": project_id,
            "m7_conversation_id": "m7-chat-1",
        },
    )
    monkeypatch.setattr(
        "app.main.verificar_acesso_projeto",
        lambda _usuario, projeto: chamadas.update(
            project_id=projeto
        ),
    )
    monkeypatch.setattr(
        "app.main.perguntar_ao_modulo7",
        lambda **kwargs: chamadas.update(kwargs) or {
            "conversation_id": "m7-chat-1",
            "message": {"content": "Continuação"},
        },
    )
    monkeypatch.setattr(
        "app.main.registrar_resposta_assistente",
        lambda **kwargs: 23,
    )

    resposta = client.post(
        "/assistente",
        json={"pergunta": "Continue", "chat_id": 23},
    )

    assert resposta.status_code == 200
    assert chamadas["project_id"] == project_id
    assert chamadas["conversation_id"] == "m7-chat-1"


def test_conversa_de_projeto_revalida_acesso(monkeypatch):
    from uuid import UUID

    project_id = UUID("7a1d0f4e-2b6c-4c1e-9f3a-5d8e7c6b4a01")
    chamadas = {}
    monkeypatch.setattr(
        "app.main.obter_conversa",
        lambda *_args: {
            "chat_id": 23,
            "project_id": str(project_id),
            "mensagens": [],
        },
    )
    monkeypatch.setattr(
        "app.main.verificar_acesso_projeto",
        lambda _usuario, projeto: chamadas.update(project_id=projeto),
    )

    resposta = client.get("/conversas/23")

    assert resposta.status_code == 200
    assert chamadas["project_id"] == project_id


def test_registrar_repositorio_persiste_stack_e_recomendacoes(monkeypatch):
    from uuid import UUID

    project_id = UUID("7a1d0f4e-2b6c-4c1e-9f3a-5d8e7c6b4a01")
    persistencia = {}
    monkeypatch.setattr(
        "app.main.verificar_acesso_projeto",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        "app.main.gerar_feed",
        lambda *_args: {
            "repositorio": "usuario/projeto",
            "stack_detectada": ["Python", "React"],
            "artigos": [
                {
                    "titulo": "Python novidades",
                    "link": "https://example.com/python",
                    "fonte": "Blog",
                    "idioma": "pt",
                    "resumo": "Atualizações de Python",
                },
                {
                    "titulo": "React novidades",
                    "link": "https://example.com/react",
                    "fonte": "Blog",
                    "idioma": "en",
                    "resumo": "New React release",
                },
            ],
        },
    )

    def salvar(**kwargs):
        persistencia.update(kwargs)
        return {
            "github_id": 7,
            "tecnologias": 2,
            "recomendacoes": 2,
        }

    monkeypatch.setattr(
        "app.main.salvar_repositorio_projeto",
        salvar,
    )

    resposta = client.post(
        f"/projetos/{project_id}/repositorios",
        json={"repositorio": "usuario/projeto"},
    )

    assert resposta.status_code == 200
    assert persistencia["subject"] == "usuario-teste"
    assert persistencia["project_id"] == project_id
    assert persistencia["repositorio_url"] == (
        "https://github.com/usuario/projeto"
    )
    assert len(persistencia["recomendacoes"]["Python"]) == 1
    assert len(persistencia["recomendacoes"]["React"]) == 1


def test_categorias():
    resposta = client.get("/categorias")

    assert resposta.status_code == 200
    assert len(resposta.json()["categorias"]) == 5


def test_feed_geral(monkeypatch):
    artigos = [
        criar_artigo(numero)
        for numero in range(1, 11)
    ]

    def listar_fake(limite):
        assert limite == 500
        return artigos

    monkeypatch.setattr(
        "app.main.listar_artigos",
        listar_fake,
    )

    resposta = client.get("/feed")

    assert resposta.status_code == 200

    dados = resposta.json()

    assert dados["total"] == 10
    assert len(dados["artigos"]) == 10
    assert dados["categoria"] == "geral"
    assert dados["repositorio"] is None


def test_feed_categoria(monkeypatch):
    artigos = [
        criar_artigo(numero)
        for numero in range(1, 11)
    ]

    def listar_fake(limite):
        assert limite == 500
        return artigos

    monkeypatch.setattr(
        "app.main.listar_artigos",
        listar_fake,
    )

    resposta = client.get(
        "/feed?categoria=desenvolvimento"
    )

    assert resposta.status_code == 200

    dados = resposta.json()

    assert dados["total"] == 5
    assert len(dados["artigos"]) == 5
    assert dados["categoria"] == "desenvolvimento"


def test_categoria_invalida():
    resposta = client.get(
        "/feed?categoria=desconhecida"
    )

    assert resposta.status_code == 400
    assert resposta.json()["detail"] == (
        "Categoria inválida."
    )


def test_detectar_stack(monkeypatch):
    def detectar_fake(repositorio):
        assert repositorio == "usuario/projeto"

        return {
            "repositorio": repositorio,
            "stack_detectada": ["React", "Docker"],
            "arquivos_analisados": [
                "package.json",
                "Dockerfile",
            ],
        }

    monkeypatch.setattr(
        "app.main.detectar_stack",
        detectar_fake,
    )

    resposta = client.get(
        "/github/stack?repositorio=usuario/projeto"
    )

    assert resposta.status_code == 200

    dados = resposta.json()

    assert dados["repositorio"] == "usuario/projeto"
    assert dados["stack_detectada"] == [
        "React",
        "Docker",
    ]


def test_limite_geral():
    artigos = [
        criar_artigo(numero)
        for numero in range(1, 21)
    ]

    resultado = selecionar_recomendacoes(
        artigos,
        limite=10,
    )

    assert len(resultado) == 10


def test_limite_categoria():
    artigos = [
        criar_artigo(numero)
        for numero in range(1, 21)
    ]

    resultado = selecionar_recomendacoes(
        artigos,
        limite=5,
        categoria="desenvolvimento",
    )

    assert len(resultado) == 5


def test_prioridade_da_stack():
    artigos = [
        {
            **criar_artigo(1),
            "titulo": "Notícias gerais de tecnologia",
        },
        {
            **criar_artigo(2),
            "titulo": "React updates for developers",
        },
    ]

    resultado = selecionar_recomendacoes(
        artigos,
        limite=2,
        stack=["React"],
    )

    assert resultado[0]["titulo"] == (
        "React updates for developers"
    )
