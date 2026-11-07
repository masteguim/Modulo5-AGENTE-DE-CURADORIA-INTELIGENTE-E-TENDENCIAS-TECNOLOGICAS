import logging
import time
from datetime import datetime, timezone

from app.curadoria import coletar_fontes
from app.database import (
    inicializar_banco,
    salvar_artigos,
    contar_artigos,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)

INTERVALO_COLETA = 3600
TERMO_ARXIV = "software engineering"


def executar_coleta():
    logger.info("Iniciando coleta de artigos...")

    inicio = datetime.now(timezone.utc)

    try:
        resultado = coletar_fontes(TERMO_ARXIV)

        artigos = resultado.get("artigos", [])
        fontes = resultado.get("fontes_consultadas", [])
        indisponiveis = resultado.get(
            "fontes_indisponiveis", []
        )

        if len(indisponiveis) == len(fontes):
            logger.error(
                "Todas as fontes estão indisponíveis."
            )

            return {
                "status": "erro",
                "mensagem": "Todas as fontes falharam.",
            }

        estatisticas = salvar_artigos(artigos)

        resposta = {
            "status": "sucesso",
            "inicio": inicio.isoformat(),
            "fim": datetime.now(
                timezone.utc
            ).isoformat(),
            "fontes_consultadas": fontes,
            "fontes_indisponiveis": indisponiveis,
            "artigos_recebidos": estatisticas["recebidos"],
            "artigos_novos": estatisticas["novos"],
            "artigos_duplicados": estatisticas[
                "duplicados_ou_invalidos"
            ],
            "total_armazenado": contar_artigos(),
        }

        logger.info(
            "Coleta concluída: %s artigos novos.",
            resposta["artigos_novos"],
        )

        logger.info(
            "Total armazenado: %s artigos.",
            resposta["total_armazenado"],
        )

        if indisponiveis:
            logger.warning(
                "Fontes indisponíveis: %s",
                ", ".join(indisponiveis),
            )

        return resposta

    except Exception:
        logger.exception(
            "Erro inesperado durante a coleta."
        )

        return {
            "status": "erro",
            "mensagem": "Falha inesperada na coleta.",
        }


def iniciar_coletor():
    inicializar_banco()

    logger.info(
        "Coletor iniciado. Intervalo: %s segundos.",
        INTERVALO_COLETA,
    )

    while True:
        executar_coleta()

        logger.info(
            "Próxima coleta em %s segundos.",
            INTERVALO_COLETA,
        )

        try:
            time.sleep(INTERVALO_COLETA)
        except KeyboardInterrupt:
            logger.info("Coletor encerrado.")
            break


if __name__ == "__main__":
    iniciar_coletor()
