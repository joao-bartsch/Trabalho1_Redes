"""
Classe Servidor: aceita conexões, distribui jogadores em salas
e gerencia o ciclo de vida das salas.
"""

import socket
import threading
from typing import Optional

from common import protocolo as p
from common.excecoes import (
    NenhumaSalaDisponivelError,
    SalaCheiaError,
    TrucoError,
)
from server.config import HOST, PORT, BACKLOG, NUM_SALAS, DEBUG
from server.jogador import Jogador
from server.sala import Sala, Estado


class Servidor:

    def __init__(self):
        self.host = HOST
        self.port = PORT
        self.salas: list[Sala] = [Sala(i + 1) for i in range(NUM_SALAS)]
        self.socket: Optional[socket.socket] = None
        self._rodando = False

    # --------------------------------------------------------
    # Ciclo de vida
    # --------------------------------------------------------

    def iniciar(self) -> None:
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind((self.host, self.port))
        self.socket.listen(BACKLOG)

        self._rodando = True
        print(f"[SERVIDOR] escutando em {self.host}:{self.port}")
        print(f"[SERVIDOR] {NUM_SALAS} salas criadas.")

        try:
            while self._rodando:
                conn, addr = self.socket.accept()
                if DEBUG:
                    print(f"[SERVIDOR] nova conexão de {addr}")
                t = threading.Thread(
                    target=self._tratar_novo_cliente,
                    args=(conn, addr),
                    daemon=True,
                )
                t.start()
        except KeyboardInterrupt:
            print("\n[SERVIDOR] encerrando...")
        finally:
            self.encerrar()

    def encerrar(self) -> None:
        self._rodando = False
        if self.socket:
            try:
                self.socket.close()
            except OSError:
                pass

    # --------------------------------------------------------
    # Novo cliente
    # --------------------------------------------------------

    def _tratar_novo_cliente(self, conn: socket.socket, addr: tuple) -> None:
        """
        Fluxo inicial:
            1. Cria Jogador provisório.
            2. Espera mensagem 'entrar' com o nome.
            3. Aloca em uma sala disponível.
            4. Manda 'bem_vindo'.
            5. Sala assume o jogador (cria thread leitora).
        """
        jogador = Jogador(conn, addr, slot="?")

        # Espera 'entrar'
        try:
            msgs = []
            while not msgs:
                msgs, jogador._buffer = p.receber(conn, jogador._buffer)
        except Exception as e:
            if DEBUG:
                print(f"[SERVIDOR] erro esperando 'entrar': {e}")
            jogador.fechar()
            return

        msg = msgs[0]
        if msg.get("tipo") != p.T_ENTRAR:
            jogador.enviar({
                "tipo": p.T_ERRO,
                "codigo": "esperado_entrar",
                "msg": "Primeira mensagem deve ser 'entrar'.",
            })
            jogador.fechar()
            return

        jogador.nome = msg.get("nome", "Anônimo")

        # Aloca em uma sala disponível
        sala = self._encontrar_sala_disponivel()
        if sala is None:
            jogador.enviar({
                "tipo": p.T_ERRO,
                "codigo": "sem_sala",
                "msg": "Todas as salas estão cheias. Tente novamente.",
            })
            jogador.fechar()
            return

        try:
            sala.adicionar_jogador(jogador)
        except TrucoError as e:
            jogador.enviar({
                "tipo": p.T_ERRO,
                "codigo": "erro_sala",
                "msg": str(e),
            })
            jogador.fechar()
            return

        # Manda bem_vindo
        jogador.enviar({
            "tipo": p.T_BEM_VINDO,
            "sala": sala.id,
            "jogador": jogador.slot,
        })

        if DEBUG:
            print(f"[SERVIDOR] {jogador.nome} ({jogador.slot}) "
                  f"entrou na sala {sala.id}")

        # Se a sala ficou com 2 jogadores, avisa o estado do lobby
        if sala.esta_cheia():
            sala.broadcast_estado_lobby()

    def _encontrar_sala_disponivel(self) -> Optional[Sala]:
        """
        Procura a primeira sala que não esteja cheia nem em jogo.
        Prefere salas com 1 jogador (AGUARDANDO_JOGADORES).
        """
        # Prioridade 1: sala com 1 jogador esperando
        for sala in self.salas:
            if sala.estado == Estado.AGUARDANDO_JOGADORES:
                return sala

        # Prioridade 2: sala vazia
        for sala in self.salas:
            if sala.estado == Estado.VAZIA:
                return sala

        return None