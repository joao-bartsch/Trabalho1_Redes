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
        self.slot = slot                 # "jogador1" | "jogador2"
        self.nome: Optional[str] = None  # apelido enviado no "entrar"
        self.mao: list[str] = []         # ex: ["4-paus", "7-copas", "A-espadas"]
        self.pontos: int = 0
        self.pronto: bool = False
        self._buffer: bytes = b""        # buffer de recv por jogador
        self._vivo: bool = True          # vira False quando a conexão morre

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