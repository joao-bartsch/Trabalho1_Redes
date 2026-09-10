
import json
import socket
from typing import Any

from .excecoes import (
    MensagemInvalidaError,
    MensagemGrandeError,
    ConexaoFechadaError,
)

# ============================================================
# Constantes
# ============================================================

ENCODING = "utf-8"
DELIMITADOR = "\n"
MAX_TAMANHO_MENSAGEM = 64 * 1024  # 64 KB por mensagem

# ============================================================
# Tipos de mensagem (por categoria)
# ============================================================

# Conexão / Lobby
T_ENTRAR = "entrar"
T_BEM_VINDO = "bem_vindo"
T_REGRAS = "regras"
T_PRONTO = "pronto"
T_LOBBY = "lobby"

# Início de partida
T_MAO_INICIAL = "mao_inicial"
T_SUA_VEZ = "sua_vez"

# Jogada normal
T_JOGAR = "jogar"
T_CARTA_JOGADA = "carta_jogada"
T_RESULTADO_VAZA = "resultado_vaza"
T_FIM_MAO = "fim_mao"

# Truco
T_TRUCO = "truco"
T_TRUCO_PEDIDO = "truco_pedido"
T_RESPOSTA_TRUCO = "resposta_truco"
T_TRUCO_ACEITO = "truco_aceito"
T_TRUCO_CORRIDO = "truco_corrido"
T_TRUCO_AUMENTADO = "truco_aumentado"

# Mostrar a maior
T_MOSTRAR_MAIOR = "mostrar_maior"
T_REVELAR_MAIOR = "revelar_maior"
T_MAIOR_REVELADA = "maior_revelada"
T_FIM_MOSTRAR_MAIOR = "fim_mostrar_maior"

# Mão de 11 / Mão de ferro
T_MAO_DE_11 = "mao_de_11"
T_DECISAO_MAO_11 = "decisao_mao_11"
T_MAO_DE_FERRO = "mao_de_ferro"
T_ESCOLHA_FERRO = "escolha_ferro"
T_RESULTADO_FERRO = "resultado_ferro"

# Revanche / Fim
T_FIM_PARTIDA = "fim_partida"
T_REVANCHE = "revanche"
T_REVANCHE_INICIO = "revanche_inicio"
T_DESCONECTANDO = "desconectando"

# Erros
T_ERRO = "erro"

# Conjuntos para validação rápida
TIPOS_CLIENTE_PARA_SERVIDOR = {
    T_ENTRAR,
    T_REGRAS,
    T_PRONTO,
    T_JOGAR,
    T_TRUCO,
    T_RESPOSTA_TRUCO,
    T_REVELAR_MAIOR,
    T_DECISAO_MAO_11,
    T_ESCOLHA_FERRO,
    T_REVANCHE,
}

TIPOS_SERVIDOR_PARA_CLIENTE = {
    T_BEM_VINDO,
    T_REGRAS,
    T_LOBBY,
    T_MAO_INICIAL,
    T_SUA_VEZ,
    T_CARTA_JOGADA,
    T_RESULTADO_VAZA,
    T_FIM_MAO,
    T_TRUCO_PEDIDO,
    T_TRUCO_ACEITO,
    T_TRUCO_CORRIDO,
    T_TRUCO_AUMENTADO,
    T_MOSTRAR_MAIOR,
    T_MAIOR_REVELADA,
    T_FIM_MOSTRAR_MAIOR,
    T_MAO_DE_11,
    T_MAO_DE_FERRO,
    T_RESULTADO_FERRO,
    T_FIM_PARTIDA,
    T_REVANCHE_INICIO,
    T_DESCONECTANDO,
    T_ERRO,
}


# ============================================================
# Funções principais
# ============================================================

def enviar(sock: socket.socket, mensagem: dict[str, Any]) -> None:
    """
    Serializa um dicionário para JSON + '\n' e envia pelo socket.

    Levanta:
        - MensagemInvalidaError: se a mensagem não for um dict
          ou não tiver a chave 'tipo'.
        - MensagemGrandeError: se a mensagem serializada exceder
          MAX_TAMANHO_MENSAGEM.
        - OSError: se o socket estiver fechado.
    """
    if not isinstance(mensagem, dict):
        raise MensagemInvalidaError("Mensagem deve ser um dicionário.")

    if "tipo" not in mensagem:
        raise MensagemInvalidaError("Mensagem precisa ter a chave 'tipo'.")

    try:
        payload = json.dumps(mensagem, ensure_ascii=False)
    except (TypeError, ValueError) as e:
        raise MensagemInvalidaError(f"Falha ao serializar JSON: {e}") from e

    dados = (payload + DELIMITADOR).encode(ENCODING)

    if len(dados) > MAX_TAMANHO_MENSAGEM:
        raise MensagemGrandeError(
            f"Mensagem excede {MAX_TAMANHO_MENSAGEM} bytes "
            f"({len(dados)} bytes)."
        )

    sock.sendall(dados)


def receber(
    sock: socket.socket,
    buffer: bytes = b"",
) -> tuple[list[dict[str, Any]], bytes]:
    """
    Recebe dados do socket, acumula no buffer e devolve
    (lista_de_mensagens, buffer_restante).

    - Trata fragmentação (mensagem chegando em pedaços).
    - Trata múltiplas mensagens no mesmo recv.
    - Mensagens incompletas (sem '\n') permanecem no buffer.

    Levanta:
        - ConexaoFechadaError: se o outro lado fechou a conexão
          (recv retornou b"").
        - MensagemInvalidaError: se algum JSON for inválido.
        - MensagemGrandeError: se o buffer acumulado crescer
          demais sem encontrar '\n'.
    """
    try:
        chunk = sock.recv(4096)
    except (ConnectionResetError, OSError) as e:
        raise ConexaoFechadaError(f"Erro ao receber dados: {e}") from e

    if not chunk:
        # recv retornou vazio: outro lado fechou a conexão
        raise ConexaoFechadaError("Conexão fechada pelo outro lado.")

    buffer += chunk

    # Proteção contra buffer infinito (cliente malicioso ou bug)
    if len(buffer) > MAX_TAMANHO_MENSAGEM * 4:
        raise MensagemGrandeError(
            "Buffer acumulado excedeu o limite sem encontrar delimitador."
        )

    mensagens: list[dict[str, Any]] = []

    while DELIMITADOR.encode(ENCODING) in buffer:
        linha_bytes, buffer = buffer.split(
            DELIMITADOR.encode(ENCODING), 1
        )
        linha = linha_bytes.decode(ENCODING).strip()

        if not linha:
            continue  # linha vazia, ignora

        try:
            msg = json.loads(linha)
        except json.JSONDecodeError as e:
            raise MensagemInvalidaError(
                f"JSON inválido recebido: {linha!r} ({e})"
            ) from e

        if not isinstance(msg, dict) or "tipo" not in msg:
            raise MensagemInvalidaError(
                f"Mensagem sem 'tipo' ou não é dict: {msg!r}"
            )

        mensagens.append(msg)

    return mensagens, buffer