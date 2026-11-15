import json
import logging
import re
from contextlib import asynccontextmanager
from typing import Annotated, Any, Literal
from uuid import UUID

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError

from app.alertas import gerar_alertas
from app.auth import AuthenticatedUser, get_current_user
from app.curadoria import (
    buscar_conteudos,
    extrair_termos,
    normalizar,
    pontuar_artigo,
    selecionar_artigos,
)
from app.database import (
    contar_artigos,
    inicializar_banco,
    listar_artigos,
    listar_conversas,
    listar_recomendacoes_projeto,
    listar_repositorios_projeto,
    obter_contexto_conversa,
    obter_conversa,
    registrar_consulta,
    registrar_resposta_assistente,
    salvar_repositorio_projeto,
)
from app.em_alta import gerar_em_alta
from app.github_stack import detectar_stack
from app.integracoes import (
    perguntar_ao_modulo7,
    verificar_acesso_projeto,
)
from app.monitoramento import monitorar_repositorio
from app.vulnerabilidades_router import router as vulnerabilidades_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    inicializar_banco()
    yield


app = FastAPI(
    title="Agente de Curadoria Inteligente",
    version="3.4.0",
    description=(
        "Curadoria tecnológica, tendências, GitHub, "
        "monitoramento de alterações e segurança."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://frontmodulo5-ecaqg8fghzhyeuh2.brazilsouth-01.azurewebsites.net",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(vulnerabilidades_router)

CATEGORIAS = {
    "inteligencia-artificial": {
        "nome": "Inteligência Artificial",
        "termos": [
            "artificial intelligence",
            "machine learning",
            "deep learning",
            "llm",
            "inteligencia artificial",
        ],
    },
    "desenvolvimento": {
        "nome": "Desenvolvimento de Software",
        "termos": [
            "software development",
            "python",
            "javascript",
            "react",
            "programming",
        ],
    },
    "seguranca": {
        "nome": "Segurança",
        "termos": [
            "cybersecurity",
            "vulnerability",
            "security",
            "cve",
            "seguranca",
        ],
    },
    "devops": {
        "nome": "DevOps e Infraestrutura",
        "termos": [
            "docker",
            "kubernetes",
            "devops",
            "cloud",
            "container",
        ],
    },
    "computacao-quantica": {
        "nome": "Computação Quântica",
        "termos": [
            "quantum computing",
            "qubit",
            "quantum algorithms",
            "computacao quantica",
        ],
    },
}

TERMOS_STACK = {
    "FastAPI": ["fastapi", "asgi", "python"],
    "Flask": ["flask", "python"],
    "Django": ["django", "python"],
    "React": ["react", "reactjs", "react.js"],
    "Vite": ["vite", "vitejs"],
    "Next.js": ["next.js", "nextjs"],
    "Docker": ["docker", "container"],
    "Python": ["python"],
    "JavaScript": ["javascript"],
    "TypeScript": ["typescript"],
    "GitHub Actions": ["github actions", "ci/cd"],
    "Pytest": ["pytest", "python testing"],
    "Qiskit": ["qiskit", "quantum computing"],
    "Pydantic": ["pydantic"],
    "NumPy": ["numpy"],
    "Pandas": ["pandas"],
    "Vue": ["vue", "vuejs"],
    "Angular": ["angular"],
    "Express": ["express", "node.js"],
    "Tailwind CSS": ["tailwind", "tailwindcss"],
    "Uvicorn": ["uvicorn", "asgi"],
}


class ConsultaEntrada(BaseModel):
    pergunta: str = Field(min_length=1)
    project_id: UUID | None = None
    chat_id: int | None = Field(default=None, gt=0)


class AssistenteEntrada(BaseModel):
    pergunta: str = Field(min_length=1, max_length=20000)
    project_id: UUID | None = None
    chat_id: int | None = Field(default=None, gt=0)
    perfil: Literal[
        "Desenvolvedor",
        "Product Owner",
        "Gerente de Projetos",
    ] = "Desenvolvedor"
    temperatura: float = Field(default=0.4, ge=0, le=1)


class RepositorioEntrada(BaseModel):
    repositorio: str = Field(min_length=3, max_length=200)


class Artigo(BaseModel):
    titulo: str
    link: str
    fonte: str
    idioma: str
    data_publicacao: str | None = None


class ConsultaResposta(BaseModel):
    pergunta: str
    artigos: list[Artigo]
    chat_id: int


class FeedResposta(BaseModel):
    artigos: list[Artigo]
    total: int
    categoria: str
    repositorio: str | None = None
    stack_detectada: list[str] = Field(default_factory=list)
    tecnologias_alteradas: list[str] = Field(
        default_factory=list
    )
    termos_recomendacao: list[str] = Field(
        default_factory=list
    )
    fontes_consultadas: list[str] = Field(
        default_factory=list
    )
    fontes_indisponiveis: list[str] = Field(
        default_factory=list
    )


class Alerta(BaseModel):
    titulo: str
    descricao: str
    link: str
    fonte: str
    gravidade: str
    tecnologias: list[str]
    data_publicacao: str | None = None
    identificado_em: str
    tipo: str


class AlertasResposta(BaseModel):
    total: int
    alertas: list[Alerta]
    stack_monitorada: list[str]
    artigos_analisados: int
    repositorio: str | None = None


class ArtigoEmAlta(BaseModel):
    titulo: str
    link: str
    fonte: str
    idioma: str
    resumo: str
    data_publicacao: str | None = None
    categoria: str
    pontuacao: float


class CategoriaEmAlta(BaseModel):
    nome: str
    quantidade: int


class EmAltaResposta(BaseModel):
    total: int
    artigos: list[ArtigoEmAlta]
    categorias: list[CategoriaEmAlta]
    artigos_analisados: int
    atualizado_em: str
    metodo_ranking: str


def termos_repositorio(stack):
    termos = []

    for tecnologia in stack:
        termos.extend(
            TERMOS_STACK.get(tecnologia, [tecnologia])
        )

    return list(dict.fromkeys(termos))


def corresponde_termo(conteudo, termo):
    termo_normalizado = normalizar(termo)

    if not termo_normalizado:
        return False

    padrao = (
        r"(?<!\w)"
        + re.escape(termo_normalizado)
        + r"(?!\w)"
    )

    return bool(re.search(padrao, conteudo))


def obter_contexto_autorizado(
    usuario: AuthenticatedUser,
    chat_id: int,
) -> dict[str, Any]:
    try:
        contexto = obter_contexto_conversa(
            usuario.subject,
            chat_id,
        )
    except SQLAlchemyError as erro:
        logger.exception("Falha ao carregar o contexto da conversa.")
        raise HTTPException(
            status_code=503,
            detail="Não foi possível carregar a conversa do banco.",
        ) from erro

    if contexto is None:
        raise HTTPException(
            status_code=404,
            detail="Conversa não encontrada.",
        )
    if contexto["project_id"]:
        verificar_acesso_projeto(usuario, contexto["project_id"])
    return contexto


def pontuar_recomendacao(
    artigo,
    termos,
    stack,
    termos_alteracoes=None,
):
    conteudo = normalizar(
        (artigo.get("titulo") or "")
        + " "
        + (artigo.get("resumo") or "")
    )

    pontos = pontuar_artigo(
        artigo,
        extrair_termos(" ".join(termos)),
    )

    for termo in termos_repositorio(stack):
        if corresponde_termo(conteudo, termo):
            pontos += 6

    for termo in termos_alteracoes or []:
        if corresponde_termo(conteudo, termo):
            pontos += 12

    return pontos


def obter_contexto_repositorio(repositorio):
    dados_stack = detectar_stack(repositorio)

    stack = dados_stack.get(
        "stack_detectada", []
    )

    nome_repositorio = dados_stack.get(
        "repositorio", repositorio
    )

    tecnologias_alteradas = []
    termos_alteracoes = []

    try:
        monitoramento = monitorar_repositorio(
            nome_repositorio,
            limite=5,
        )

        termos_alteracoes = monitoramento.get(
            "termos_recomendacao", []
        )

        tecnologias_alteradas = [
            item["tecnologia"]
            for item in monitoramento.get(
                "resumo", {}
            ).get("tecnologias_alteradas", [])
        ]

    except (
        httpx.HTTPError,
        RuntimeError,
        ValueError,
    ) as erro:
        logger.warning(
            "Monitoramento indisponível para %s: %s",
            nome_repositorio,
            erro,
        )

    return {
        "repositorio": nome_repositorio,
        "stack": stack,
        "tecnologias_alteradas": tecnologias_alteradas,
        "termos_alteracoes": termos_alteracoes,
    }


def gerar_feed(categoria, repositorio):
    if (
        categoria != "geral"
        and categoria not in CATEGORIAS
    ):
        raise HTTPException(
            status_code=400,
            detail="Categoria inválida.",
        )

    stack = []
    nome_repositorio = None
    tecnologias_alteradas = []
    termos_alteracoes = []

    if repositorio:
        contexto = obter_contexto_repositorio(
            repositorio
        )

        stack = contexto["stack"]
        nome_repositorio = contexto["repositorio"]

        tecnologias_alteradas = contexto[
            "tecnologias_alteradas"
        ]

        termos_alteracoes = contexto[
            "termos_alteracoes"
        ]

    artigos_banco = listar_artigos(500)

    termos_categoria = CATEGORIAS.get(
        categoria, {}
    ).get("termos", [])

    termos = list(dict.fromkeys(
        termos_categoria
        + termos_repositorio(stack)
        + termos_alteracoes
    ))

    artigos_pontuados = []

    for artigo in artigos_banco:
        conteudo = normalizar(
            (artigo.get("titulo") or "")
            + " "
            + (artigo.get("resumo") or "")
        )

        if categoria != "geral":
            relevante_categoria = any(
                corresponde_termo(conteudo, termo)
                for termo in termos_categoria
            )

            if not relevante_categoria:
                continue

        pontos = pontuar_recomendacao(
            artigo,
            termos,
            stack,
            termos_alteracoes,
        )

        artigos_pontuados.append({
            **artigo,
            "_pontuacao": pontos,
        })

    artigos_pontuados.sort(
        key=lambda artigo: (
            artigo["_pontuacao"],
            artigo.get("data_publicacao")
            or artigo.get("coletado_em")
            or "",
        ),
        reverse=True,
    )

    limite = (
        10 if categoria == "geral"
        else 5
    )

    artigos = selecionar_artigos(
        artigos_pontuados,
        limite,
    )

    fontes = sorted({
        artigo["fonte"]
        for artigo in artigos_banco
    })

    return {
        "artigos": artigos,
        "total": len(artigos),
        "categoria": categoria,
        "repositorio": nome_repositorio,
        "stack_detectada": stack,
        "tecnologias_alteradas": tecnologias_alteradas,
        "termos_recomendacao": termos_alteracoes,
        "fontes_consultadas": fontes,
        "fontes_indisponiveis": [],
    }


@app.get("/")
def inicio():
    return {
        "aplicacao": "Agente de Curadoria Inteligente",
        "versao": "3.4.0",
        "status": "online",
        "artigos_armazenados": contar_artigos(),
    }


@app.get("/categorias")
def listar_categorias():
    return {
        "categorias": [
            {
                "id": identificador,
                "nome": dados["nome"],
            }
            for identificador, dados
            in CATEGORIAS.items()
        ]
    }


@app.get("/github/stack")
def analisar_repositorio(
    repositorio: str = Query(
        min_length=3,
        max_length=200,
    ),
):
    return detectar_stack(repositorio)


@app.get("/github/alteracoes")
def consultar_alteracoes(
    repositorio: str = Query(
        min_length=3,
        max_length=200,
    ),
    limite: int = Query(
        default=5,
        ge=1,
        le=20,
    ),
):
    try:
        return monitorar_repositorio(
            repositorio,
            limite=limite,
        )

    except ValueError as erro:
        raise HTTPException(
            status_code=400,
            detail=str(erro),
        ) from erro

    except (httpx.HTTPError, RuntimeError) as erro:
        logger.warning(
            "Falha no monitoramento: %s",
            erro,
        )

        raise HTTPException(
            status_code=502,
            detail=(
                "Não foi possível consultar "
                "as alterações no GitHub."
            ),
        ) from erro


@app.get("/artigos")
def artigos_armazenados(
    limite: int = Query(
        default=50,
        ge=1,
        le=500,
    ),
):
    return {
        "total_armazenado": contar_artigos(),
        "artigos": listar_artigos(limite),
    }


@app.get(
    "/feed",
    response_model=FeedResposta,
)
def feed(
    categoria: str = "geral",
    repositorio: str | None = None,
):
    return gerar_feed(
        categoria,
        repositorio,
    )


@app.get(
    "/alertas",
    response_model=AlertasResposta,
)
def listar_alertas(
    repositorio: str | None = Query(
        default=None,
        max_length=200,
    ),
    limite: int = Query(
        default=20,
        ge=1,
        le=100,
    ),
):
    stack = []
    nome_repositorio = None

    if repositorio:
        dados_github = detectar_stack(
            repositorio
        )

        stack = dados_github[
            "stack_detectada"
        ]

        nome_repositorio = dados_github[
            "repositorio"
        ]

        if not stack:
            return AlertasResposta(
                total=0,
                alertas=[],
                stack_monitorada=[],
                artigos_analisados=len(
                    listar_artigos(500)
                ),
                repositorio=nome_repositorio,
            )

    resultado = gerar_alertas(
        stack=stack,
        limite=limite,
    )

    return AlertasResposta(
        **resultado,
        repositorio=nome_repositorio,
    )


@app.get(
    "/em-alta",
    response_model=EmAltaResposta,
)
def listar_em_alta(
    limite: int = Query(
        default=20,
        ge=1,
        le=100,
    ),
    categoria: str | None = Query(
        default=None,
    ),
):
    categorias_validas = [
        "geral",
        "Inteligência Artificial",
        "Desenvolvimento",
        "Segurança",
        "DevOps",
        "Computação Quântica",
        "Outros",
    ]

    if (
        categoria
        and categoria not in categorias_validas
    ):
        raise HTTPException(
            status_code=400,
            detail="Categoria inválida.",
        )

    return gerar_em_alta(
        limite=limite,
        categoria=categoria,
    )


@app.post(
    "/consultas",
    response_model=ConsultaResposta,
)
def consultar(
    dados: ConsultaEntrada,
    usuario: Annotated[AuthenticatedUser, Depends(get_current_user)],
):
    project_id = dados.project_id
    if dados.chat_id is not None:
        contexto = obter_contexto_autorizado(
            usuario,
            dados.chat_id,
        )
        if project_id and project_id != contexto["project_id"]:
            raise HTTPException(
                status_code=400,
                detail="A conversa não pertence ao projeto informado.",
            )
        project_id = contexto["project_id"]
    elif project_id:
        verificar_acesso_projeto(usuario, project_id)

    resultado = buscar_conteudos(
        dados.pergunta
    )

    fontes = resultado.get(
        "fontes_consultadas", []
    )

    indisponiveis = resultado.get(
        "fontes_indisponiveis", []
    )

    if (
        fontes
        and len(indisponiveis) == len(fontes)
    ):
        raise HTTPException(
            status_code=502,
            detail=(
                "Todas as fontes estão "
                "indisponíveis."
            ),
        )

    try:
        chat_id = registrar_consulta(
            subject=usuario.subject,
            pergunta=dados.pergunta,
            resposta=json.dumps(
                resultado["artigos"],
                ensure_ascii=False,
            ),
            project_id=project_id,
            chat_id=dados.chat_id,
        )
    except LookupError as erro:
        raise HTTPException(
            status_code=404,
            detail="Conversa não encontrada.",
        ) from erro
    except ValueError as erro:
        raise HTTPException(
            status_code=400,
            detail=str(erro),
        ) from erro
    except SQLAlchemyError as erro:
        logger.exception("Falha ao persistir a consulta.")
        raise HTTPException(
            status_code=503,
            detail="Não foi possível salvar a consulta no banco.",
        ) from erro

    return {
        "pergunta": dados.pergunta,
        "artigos": resultado["artigos"],
        "chat_id": chat_id,
    }


@app.post("/assistente")
def consultar_assistente(
    dados: AssistenteEntrada,
    usuario: Annotated[AuthenticatedUser, Depends(get_current_user)],
):
    project_id = dados.project_id
    m7_conversation_id = None

    if dados.chat_id is not None:
        contexto = obter_contexto_autorizado(
            usuario,
            dados.chat_id,
        )
        if project_id and project_id != contexto["project_id"]:
            raise HTTPException(
                status_code=400,
                detail="A conversa não pertence ao projeto informado.",
            )
        project_id = contexto["project_id"]
        m7_conversation_id = contexto["m7_conversation_id"]

    if project_id:
        verificar_acesso_projeto(usuario, project_id)

    resposta = perguntar_ao_modulo7(
        usuario=usuario,
        pergunta=dados.pergunta,
        project_id=project_id,
        conversation_id=m7_conversation_id,
        profile=dados.perfil,
        temperature=dados.temperatura,
    )

    try:
        chat_id = registrar_resposta_assistente(
            subject=usuario.subject,
            pergunta=dados.pergunta,
            resposta=json.dumps(
                resposta["message"],
                ensure_ascii=False,
            ),
            m7_conversation_id=resposta["conversation_id"],
            project_id=project_id,
            chat_id=dados.chat_id,
        )
    except (LookupError, ValueError) as erro:
        raise HTTPException(
            status_code=404 if isinstance(erro, LookupError) else 400,
            detail=str(erro),
        ) from erro
    except SQLAlchemyError as erro:
        logger.exception(
            "Falha ao persistir a resposta do Módulo 7."
        )
        raise HTTPException(
            status_code=503,
            detail=(
                "O Módulo 7 respondeu, mas não foi possível "
                "salvar a conversa no banco."
            ),
        ) from erro

    return {
        "chat_id": chat_id,
        "project_id": str(project_id) if project_id else None,
        "conversation_id": resposta["conversation_id"],
        "message": resposta["message"],
    }


@app.get("/conversas")
def consultar_conversas(
    usuario: Annotated[AuthenticatedUser, Depends(get_current_user)],
    project_id: UUID | None = None,
    limite: int = Query(default=50, ge=1, le=100),
):
    if project_id:
        verificar_acesso_projeto(usuario, project_id)
    try:
        conversas = listar_conversas(
            usuario.subject,
            project_id,
            limite,
        )
    except SQLAlchemyError as erro:
        logger.exception("Falha ao listar conversas.")
        raise HTTPException(
            status_code=503,
            detail="Não foi possível consultar o histórico no banco.",
        ) from erro
    return {"conversas": conversas}


@app.get("/conversas/{chat_id}")
def consultar_conversa(
    chat_id: int,
    usuario: Annotated[AuthenticatedUser, Depends(get_current_user)],
):
    try:
        conversa = obter_conversa(usuario.subject, chat_id)
    except SQLAlchemyError as erro:
        logger.exception("Falha ao carregar conversa.")
        raise HTTPException(
            status_code=503,
            detail="Não foi possível consultar a conversa no banco.",
        ) from erro
    if conversa is None:
        raise HTTPException(
            status_code=404,
            detail="Conversa não encontrada.",
        )
    if conversa["project_id"]:
        verificar_acesso_projeto(
            usuario,
            UUID(conversa["project_id"]),
        )
    return conversa


@app.post("/projetos/{project_id}/repositorios")
def registrar_repositorio(
    project_id: UUID,
    dados: RepositorioEntrada,
    usuario: Annotated[AuthenticatedUser, Depends(get_current_user)],
):
    verificar_acesso_projeto(usuario, project_id)
    try:
        resultado = gerar_feed("geral", dados.repositorio)
        stack = resultado["stack_detectada"]
        artigos = resultado["artigos"]
        recomendacoes_por_tecnologia = {}

        for tecnologia in stack:
            termos = termos_repositorio([tecnologia])
            recomendacoes_por_tecnologia[tecnologia] = [
                artigo
                for artigo in artigos
                if any(
                    corresponde_termo(
                        normalizar(
                            (artigo.get("titulo") or "")
                            + " "
                            + (artigo.get("resumo") or "")
                        ),
                        termo,
                    )
                    for termo in termos
                )
            ]

        persistencia = salvar_repositorio_projeto(
            subject=usuario.subject,
            project_id=project_id,
            repositorio_url=(
                f"https://github.com/{resultado['repositorio']}"
            ),
            stack=stack,
            recomendacoes=recomendacoes_por_tecnologia,
        )
    except SQLAlchemyError as erro:
        logger.exception("Falha ao persistir a integração GitHub.")
        raise HTTPException(
            status_code=503,
            detail=(
                "Não foi possível carregar ou salvar os dados "
                "do repositório no banco."
            ),
        ) from erro

    return {
        "project_id": str(project_id),
        "repositorio": resultado["repositorio"],
        "stack_detectada": stack,
        "recomendacoes": [
            {
                "tecnologia": tecnologia,
                "artigos": recomendacoes_por_tecnologia[tecnologia],
            }
            for tecnologia in stack
        ],
        "persistencia": persistencia,
    }


@app.get("/projetos/{project_id}/repositorios")
def consultar_repositorios_projeto(
    project_id: UUID,
    usuario: Annotated[AuthenticatedUser, Depends(get_current_user)],
):
    verificar_acesso_projeto(usuario, project_id)
    try:
        repositorios = listar_repositorios_projeto(
            project_id,
        )
    except SQLAlchemyError as erro:
        logger.exception("Falha ao listar repositórios do projeto.")
        raise HTTPException(
            status_code=503,
            detail="Não foi possível consultar os repositórios no banco.",
        ) from erro
    return {
        "project_id": str(project_id),
        "repositorios": repositorios,
    }


@app.get("/projetos/{project_id}/recomendacoes")
def consultar_recomendacoes_projeto(
    project_id: UUID,
    usuario: Annotated[AuthenticatedUser, Depends(get_current_user)],
):
    verificar_acesso_projeto(usuario, project_id)
    try:
        recomendacoes = listar_recomendacoes_projeto(
            project_id,
        )
    except SQLAlchemyError as erro:
        logger.exception("Falha ao listar recomendações do projeto.")
        raise HTTPException(
            status_code=503,
            detail="Não foi possível consultar recomendações no banco.",
        ) from erro
    return {
        "project_id": str(project_id),
        "recomendacoes": recomendacoes,
    }
