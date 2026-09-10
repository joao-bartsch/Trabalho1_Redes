"""
Classe Jogador: representa um cliente conectado dentro de uma sala.

Guarda a conexão (socket), o endereço, o nome/apelido, a mão atual,
os pontos, o estado de "pronto" no lobby e uma fila de mensagens
recebidas (preenchida pela thread leitora da Sala).

A mão é uma lista de strings no formato "valor-naipe"
(ex: "4-paus"), que serão convertidas em Carta pela Partida.
"""

import queue
import socket
from typing import Optional

from common import protocolo as p
from common.excecoes import ConexaoFechadaError


class Jogador:
    """Representa um jogador conectado."""

    def __init__(self, conn: socket.socket, addr: tuple, slot: str):
        """
        Args:
            conn: socket da conexão com o cliente.
            addr: tupla (host, porta) do cliente.
            slot: "jogador1" ou "jogador2" — posição na sala.
        """
        self.conn = conn
        self.addr = addr
        self.slot = slot
        self.nome: Optional[str] = None
        self.mao: list[str] = []
        self.pontos: int = 0
        self.pronto: bool = False

        # Buffer de recv (fragmentação) — usado pela thread leitora.
        self._buffer: bytes = b""

        # Flag de vida — vira False quando a conexão morre.
        self._vivo: bool = True

        # Fila de mensagens recebidas (consumida pela Sala ou Partida).
        self.fila: queue.Queue = queue.Queue()

    # --------------------------------------------------------
    # Rede
    # --------------------------------------------------------

    def enviar(self, mensagem: dict) -> bool:
        """
        Envia uma mensagem pro cliente.

        Returns:
            True se enviou com sucesso, False se a conexão caiu.
        """
        try:
            p.enviar(self.conn, mensagem)
            return True
        except (OSError, ConexaoFechadaError):
            self._vivo = False
            return False

    def receber(self) -> list[dict]:
        """
        Recebe mensagens do cliente (pode ser mais de uma por chamada).

        Returns:
            Lista de mensagens. Se a conexão caiu, marca _vivo=False
            e retorna lista vazia.
        """
        try:
            msgs, self._buffer = p.receber(self.conn, self._buffer)
            return msgs
        except ConexaoFechadaError:
            self._vivo = False
            return []

    def fechar(self) -> None:
        """Fecha a conexão, ignorando erros."""
        self._vivo = False
        try:
            self.conn.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self.conn.close()
        except OSError:
            pass

    # --------------------------------------------------------
    # Estado
    # --------------------------------------------------------

    @property
    def vivo(self) -> bool:
        return self._vivo

    def resetar_para_nova_partida(self) -> None:
        """Zera mão, pontos e pronto (mas mantém nome e socket)."""
        self.mao = []
        self.pontos = 0
        self.pronto = False

    def __repr__(self) -> str:
        nome = self.nome or "?"
        return f"Jogador(slot={self.slot}, nome={nome}, pontos={self.pontos})"