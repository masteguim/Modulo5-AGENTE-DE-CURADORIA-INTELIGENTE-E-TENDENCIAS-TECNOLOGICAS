import json
import sys
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version
from packaging.utils import canonicalize_name
from app.avisos_github import (
    buscar_avisos_ecossistema,
    formatar_aviso,
)
from app.dependencias import identificar_dependencias


def normalizar_pacote(nome, ecossistema):
    if ecossistema == "pip":
        return canonicalize_name(nome)

    return nome.strip().lower()


def verificar_intervalo_python(versao, intervalo):
    if not versao or not intervalo:
        return None

    try:
        versao_instalada = Version(versao)
    except InvalidVersion:
        return None

    resultados = []

    for alternativa in intervalo.split("||"):
        especificadores = []

        for parte in alternativa.split(","):
            parte = parte.strip()

            if not parte:
                continue

            if parte.startswith("=") and not parte.startswith(
                "=="
            ):
                parte = "=" + parte

            especificadores.append(parte)

        if not especificadores:
            continue

        try:
            conjunto = SpecifierSet(
                ",".join(especificadores)
            )

            resultados.append(
                versao_instalada in conjunto
            )

        except InvalidSpecifier:
            resultados.append(None)

    if True in resultados:
        return True

    if resultados and all(
        resultado is False
        for resultado in resultados
    ):
        return False

    return None


def verificar_versao(dependencia, intervalo):
    versao = dependencia.get("versao_exata")
    ecossistema = dependencia.get("ecossistema")

    if not versao:
        return {
            "situacao": "versao_nao_fixada",
            "justificativa": (
                "A dependência não possui versão "
                "exata declarada."
            ),
        }

    if ecossistema != "pip":
        return {
            "situacao": "verificacao_inconclusiva",
            "justificativa": (
                "A comparação automática deste "
                "ecossistema ainda não está disponível."
            ),
        }

    resultado = verificar_intervalo_python(
        versao,
        intervalo,
    )

    if resultado is True:
        return {
            "situacao": "potencialmente_vulneravel",
            "justificativa": (
                "A versão declarada pertence ao "
                "intervalo afetado pelo aviso."
            ),
        }

    if resultado is False:
        return {
            "situacao": "versao_declarada_nao_afetada",
            "justificativa": (
                "A versão declarada não pertence "
                "ao intervalo informado no aviso."
            ),
        }

    return {
        "situacao": "verificacao_inconclusiva",
        "justificativa": (
            "Não foi possível interpretar "
            "o intervalo de versões."
        ),
    }


def criar_indice_dependencias(dependencias):
    indice = {}

    for dependencia in dependencias:
        ecossistema = dependencia["ecossistema"]

        chave = (
            ecossistema,
            normalizar_pacote(
                dependencia["nome"],
                ecossistema,
            ),
        )

        indice.setdefault(chave, []).append(
            dependencia
        )

    return indice


def analisar_repositorio(repositorio):
    dados = identificar_dependencias(
        repositorio
    )

    dependencias = dados["dependencias"]

    indice = criar_indice_dependencias(
        dependencias
    )

    ecossistemas = sorted({
        dependencia["ecossistema"]
        for dependencia in dependencias
    })

    resultados = []
    erros = list(dados.get("erros", []))
    avisos_consultados = 0

    for ecossistema in ecossistemas:
        try:
            avisos = buscar_avisos_ecossistema(
                ecossistema,
                limite=100,
            )

        except Exception as erro:
            erros.append({
                "ecossistema": ecossistema,
                "erro": str(erro),
            })
            continue

        avisos_consultados += len(avisos)

        for aviso_bruto in avisos:
            if aviso_bruto.get("withdrawn_at"):
                continue

            aviso = formatar_aviso(
                aviso_bruto
            )

            for pacote in aviso["pacotes_afetados"]:
                nome = pacote.get("nome")
                ecossistema_pacote = pacote.get(
                    "ecossistema"
                )

                if not nome or not ecossistema_pacote:
                    continue

                chave = (
                    ecossistema_pacote.lower(),
                    normalizar_pacote(
                        nome,
                        ecossistema_pacote.lower(),
                    ),
                )

                dependencias_encontradas = indice.get(
                    chave, []
                )

                for dependencia in dependencias_encontradas:
                    verificacao = verificar_versao(
                        dependencia,
                        pacote.get("versoes_afetadas"),
                    )

                    resultados.append({
                        "pacote": dependencia["nome"],
                        "ecossistema": ecossistema_pacote,
                        "versao_declarada": dependencia.get(
                            "versao_exata"
                        ),
                        "especificacao": dependencia.get(
                            "especificacao"
                        ),
                        "arquivo": dependencia["arquivo"],
                        "grupo": dependencia["grupo"],
                        "ghsa": aviso["id"],
                        "cve": aviso["cve"],
                        "titulo": aviso["titulo"],
                        "gravidade": aviso["gravidade"],
                        "versoes_afetadas": pacote.get(
                            "versoes_afetadas"
                        ),
                        "versao_corrigida": pacote.get(
                            "primeira_versao_corrigida"
                        ),
                        "link": aviso["link"],
                        **verificacao,
                    })

    resultados.sort(
        key=lambda item: (
            item["situacao"]
            != "potencialmente_vulneravel",
            item["pacote"].lower(),
            item["ghsa"] or "",
        )
    )

    contagem = {
        "potencialmente_vulneravel": 0,
        "versao_declarada_nao_afetada": 0,
        "versao_nao_fixada": 0,
        "verificacao_inconclusiva": 0,
    }

    for resultado in resultados:
        contagem[resultado["situacao"]] += 1

    return {
        "repositorio": dados["repositorio"],
        "total_dependencias": len(dependencias),
        "avisos_consultados": avisos_consultados,
        "avisos_correspondentes": len(resultados),
        "resumo": contagem,
        "resultados": resultados,
        "erros": erros,
        "arquivos_encontrados": dados[
            "arquivos_encontrados"
        ],
        "observacao": (
            "Análise preliminar dos avisos recentes "
            "retornados pela API do GitHub. Não é uma "
            "auditoria completa. Versões declaradas "
            "não garantem que sejam as instaladas, "
            "e dependências transitivas podem "
            "não estar representadas."
        ),
    }


if __name__ == "__main__":
    repositorio = (
        sys.argv[1]
        if len(sys.argv) > 1
        else (
            "masteguim/"
            "Modulo5-AGENTE-DE-CURADORIA-"
            "INTELIGENTE-E-TENDENCIAS-TECNOLOGICAS"
        )
    )

    resultado = analisar_repositorio(
        repositorio
    )

    print(
        json.dumps(
            resultado,
            indent=2,
            ensure_ascii=False,
        )
    )
