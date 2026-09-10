"""
Classe Sala: representa uma sala de jogo com até 2 jogadores.

Responsabilidades:
    - Guardar o estado da sala (VAZIA, AGUARDANDO_JOGADORES, LOBBY,
      EM_JOGO, FINALIZADA).
    - Proteger o estado com RLock.
    - Coordenar turnos com uma Condition única.
    - Criar e gerenciar a thread leitora de cada jogador.
    - Fazer broadcast de mensagens pra todos os jogadores.
    - Gerenciar lobby (pronto/regras), WO e revanche.
"""

import threading
from typing import Optional

from common import protocolo as p
from common.excecoes import (
    SalaCheiaError,
    JogadorJaNaSalaError,
    EstadoSalaInvalidoError,
)
from server.config import DEBUG
from server.jogador import Jogador
from server.regras import TEXTO_REGRAS   # texto fixo das regras


# ============================================================
# Estados possíveis
# ============================================================

class Estado:
    VAZIA = "VAZIA"
    AGUARDANDO_JOGADORES = "AGUARDANDO_JOGADORES"
    LOBBY = "LOBBY"
    EM_JOGO = "EM_JOGO"
    FINALIZADA = "FINALIZADA"


# ============================================================
# Classe Sala
# ============================================================

class Sala:

    def __init__(self, id_sala: int):
        self.id = id_sala
        self.estado: str = Estado.VAZIA

        # Jogadores: {"jogador1": Jogador | None, "jogador2": Jogador | None}
        self.jogadores: dict[str, Optional[Jogador]] = {
            "jogador1": None,
            "jogador2": None,
        }

        # Partida em andamento
        self.partida = None   # type: ignore

        # Revanche
        self.revanche: dict[str, bool] = {
            "jogador1": False,
            "jogador2": False,
        }

        # Concorrência
        self.lock = threading.RLock()
        self.condicao = threading.Condition(self.lock)

        # Threads leitoras (por slot)
        self.threads_leitoras: dict[str, Optional[threading.Thread]] = {
            "jogador1": None,
            "jogador2": None,
        }

    # ========================================================
    # Consultas rápidas
    # ========================================================

    def esta_cheia(self) -> bool:
        return all(j is not None for j in self.jogadores.values())

    def esta_vazia(self) -> bool:
        return all(j is None for j in self.jogadores.values())

    def jogadores_ativos(self) -> list[Jogador]:
        return [j for j in self.jogadores.values() if j is not None]

    def slot_livre(self) -> Optional[str]:
        for slot, j in self.jogadores.items():
            if j is None:
                return slot
        return None

    def adversario_de(self, slot: str) -> Optional[Jogador]:
        outro = "jogador2" if slot == "jogador1" else "jogador1"
        return self.jogadores.get(outro)

    # ========================================================
    # Entrada / saída de jogadores
    # ========================================================

    def adicionar_jogador(self, jogador: Jogador) -> None:
        """
        Coloca um jogador na sala (primeiro slot livre) e dispara
        a thread leitora dele.
        """
        with self.lock:
            if self.esta_cheia():
                raise SalaCheiaError(f"Sala {self.id} já está cheia.")

            if self.estado in (Estado.EM_JOGO, Estado.FINALIZADA):
                raise EstadoSalaInvalidoError(
                    f"Sala {self.id} não aceita novos jogadores "
                    f"(estado: {self.estado})."
                )

            for j in self.jogadores.values():
                if j is not None and j.conn is jogador.conn:
                    raise JogadorJaNaSalaError(
                        f"Jogador já está na sala {self.id}."
                    )

            slot = self.slot_livre()
            if slot is None:
                raise SalaCheiaError(f"Sala {self.id} sem slot livre.")

            jogador.slot = slot
            self.jogadores[slot] = jogador

            if self.esta_cheia():
                self.estado = Estado.LOBBY
            else:
                self.estado = Estado.AGUARDANDO_JOGADORES

            self._iniciar_thread_leitora(jogador)
            self.condicao.notify_all()

    def _iniciar_thread_leitora(self, jogador: Jogador) -> None:
        """Cria e inicia a thread leitora do jogador."""
        t = threading.Thread(
            target=self._loop_leitura,
            args=(jogador,),
            name=f"leitor-{self.id}-{jogador.slot}",
            daemon=True,
        )
        self.threads_leitoras[jogador.slot] = t
        t.start()

    def _loop_leitura(self, jogador: Jogador) -> None:
        """
        Loop de leitura do socket do jogador.

        - Recebe mensagens via protocolo.
        - Despacha por estado da sala:
            - LOBBY / AGUARDANDO_JOGADORES → trata aqui mesmo (regras/pronto).
            - EM_JOGO → enfileira na fila da Partida.
            - Outros → ignora / erro.
        - Quando a conexão cai (recv vazio), chama remover_jogador(slot).
        """
        while jogador.vivo:
            msgs = jogador.receber()
            if not jogador.vivo:
                # Conexão caiu → remove da sala
                self.remover_jogador(jogador.slot, motivo="conexão caiu")
                return

            for msg in msgs:
                self._despachar(jogador, msg)

    def _despachar(self, jogador: Jogador, msg: dict) -> None:
        """Decide o que fazer com uma mensagem recebida do jogador."""
        tipo = msg.get("tipo")
        estado = self.estado

        if estado in (Estado.AGUARDANDO_JOGADORES, Estado.LOBBY):
            self._tratar_lobby(jogador, msg)
        elif estado == Estado.EM_JOGO:
            # Manda pra Partida consumir
            jogador.fila.put(msg)
            with self.condicao:
                self.condicao.notify_all()
        elif estado == Estado.FINALIZADA:
            self._tratar_revanche(jogador, msg)
        else:
            jogador.enviar({
                "tipo": "erro",
                "codigo": "estado_invalido",
                "msg": f"Ação '{tipo}' não permitida no estado {estado}.",
            })

    # ========================================================
    # Lobby
    # ========================================================

    def _tratar_lobby(self, jogador: Jogador, msg: dict) -> None:
        """Trata mensagens recebidas enquanto a sala está no lobby."""
        tipo = msg.get("tipo")

        if tipo == p.T_REGRAS:
            jogador.enviar({"tipo": "regras", "texto": TEXTO_REGRAS})

        elif tipo == p.T_PRONTO:
            ambos_prontos = self.marcar_pronto(jogador.slot)
            if ambos_prontos:
                self.iniciar_partida()

        else:
            jogador.enviar({
                "tipo": "erro",
                "codigo": "acao_invalida_lobby",
                "msg": f"Ação '{tipo}' não é válida no lobby.",
            })

    def marcar_pronto(self, slot: str) -> bool:
        """Marca o jogador como pronto. Retorna True se ambos prontos."""
        with self.lock:
            jogador = self.jogadores.get(slot)
            if jogador is None:
                return False

            if self.estado not in (Estado.LOBBY, Estado.AGUARDANDO_JOGADORES):
                raise EstadoSalaInvalidoError(
                    f"Não é possível marcar pronto no estado {self.estado}."
                )

            jogador.pronto = True
            self.broadcast_estado_lobby()

            if self.esta_cheia() and all(
                j is not None and j.pronto for j in self.jogadores.values()
            ):
                return True
            return False

    def broadcast_estado_lobby(self) -> None:
        with self.lock:
            dados = []
            for slot, j in self.jogadores.items():
                if j is not None:
                    dados.append({
                        "slot": slot,
                        "nome": j.nome or slot,
                        "pronto": j.pronto,
                    })
            self.broadcast({
                "tipo": "lobby",
                "jogadores": dados,
                "estado": self.estado,
            })

    # ========================================================
    # Remoção de jogador (WO / desconexão)
    # ========================================================

    def remover_jogador(self, slot: str, motivo: str = "desconectado") -> None:
        """
        Remove um jogador da sala.

        - Fecha o socket dele (mata a thread leitora naturalmente).
        - Se havia partida em andamento, avisa a Partida (WO).
        - Ajusta o estado da sala.
        """
        with self.lock:
            jogador = self.jogadores.get(slot)
            if jogador is None:
                return

            if DEBUG:
                print(f"[SALA {self.id}] removendo {slot} ({motivo})")

            # Avisa a Partida (se houver) → WO
            if self.estado == Estado.EM_JOGO and self.partida is not None:
                try:
                    self.partida.registrar_wo(slot)
                except Exception as e:
                    if DEBUG:
                        print(f"[SALA {self.id}] erro ao registrar WO: {e}")

            jogador.fechar()
            self.jogadores[slot] = None
            self.threads_leitoras[slot] = None

            if self.esta_vazia():
                self.estado = Estado.VAZIA
            else:
                self.estado = Estado.AGUARDANDO_JOGADORES
                # Reseta pronto do que sobrou
                for j in self.jogadores.values():
                    if j is not None:
                        j.pronto = False

            self.condicao.notify_all()

    # ========================================================
    # Partida
    # ========================================================

    def iniciar_partida(self) -> None:
        """Cria a Partida e muda o estado pra EM_JOGO."""
        with self.lock:
            if not self.esta_cheia():
                raise EstadoSalaInvalidoError(
                    "Não é possível iniciar partida sem 2 jogadores."
                )

            from server.partida import Partida

            self.estado = Estado.EM_JOGO
            self.revanche = {"jogador1": False, "jogador2": False}
            self.partida = Partida(self)

            thread_partida = threading.Thread(
                target=self.partida.rodar,
                name=f"partida-sala-{self.id}",
                daemon=True,
            )
            thread_partida.start()

    def finalizar_partida(self, vencedor_slot: str) -> None:
        """Marca a sala como FINALIZADA após o fim da partida."""
        with self.lock:
            self.estado = Estado.FINALIZADA
            self.revanche = {"jogador1": False, "jogador2": False}
            self.condicao.notify_all()

    # ========================================================
    # Revanche
    # ========================================================

    def _tratar_revanche(self, jogador: Jogador, msg: dict) -> None:
        tipo = msg.get("tipo")
        if tipo != p.T_REVANCHE:
            jogador.enviar({
                "tipo": "erro",
                "codigo": "acao_invalida_revanche",
                "msg": f"Ação '{tipo}' não permitida agora.",
            })
            return

        aceitou = msg.get("acao") == "aceitar"
        resultado = self.registrar_revanche(jogador.slot, aceitou)

        if resultado == "reiniciar":
            self.broadcast({"tipo": "revanche_inicio"})
            self.reiniciar_para_revanche()
        elif resultado == "encerrar":
            # Um recusou → manda desconectando pros dois
            self.broadcast({
                "tipo": "desconectando",
                "motivo": "Revanche recusada.",
            })
            # Fecha os dois sockets (threads leitoras morrem)
            for slot in list(self.jogadores.keys()):
                j = self.jogadores.get(slot)
                if j is not None:
                    j.fechar()
                    self.jogadores[slot] = None
            self.estado = Estado.VAZIA

    def registrar_revanche(self, slot: str, aceitou: bool) -> Optional[str]:
        with self.lock:
            if self.estado != Estado.FINALIZADA:
                raise EstadoSalaInvalidoError(
                    "Revanche só pode ser registrada após a partida."
                )

            self.revanche[slot] = aceitou

            if not aceitou:
                return "encerrar"

            outro = "jogador2" if slot == "jogador1" else "jogador1"
            if self.revanche.get(outro):
                return "reiniciar"

            return None

    def reiniciar_para_revanche(self) -> None:
        with self.lock:
            for j in self.jogadores.values():
                if j is not None:
                    j.resetar_para_nova_partida()
            self.revanche = {"jogador1": False, "jogador2": False}
            self.iniciar_partida()

    # ========================================================
    # Broadcast / envio
    # ========================================================

    def broadcast(self, mensagem: dict) -> None:
        for j in self.jogadores_ativos():
            j.enviar(mensagem)

    def enviar_para(self, slot: str, mensagem: dict) -> None:
        j = self.jogadores.get(slot)
        if j is not None:
            j.enviar(mensagem)

    # ========================================================
    # Debug
    # ========================================================

    def __repr__(self) -> str:
        nomes = [
            (j.nome if j and j.nome else slot)
            for slot, j in self.jogadores.items()
        ]
        return f"Sala(id={self.id}, estado={self.estado}, jogadores={nomes})"