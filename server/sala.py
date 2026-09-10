"""
Classe Sala: representa uma sala de jogo com até 2 jogadores.

Responsabilidades:
    - Guardar o estado da sala (VAZIA, AGUARDANDO_JOGADORES, LOBBY,
      EM_JOGO, FINALIZADA).
    - Proteger o estado com RLock (acesso concorrente das threads).
    - Coordenar turnos com uma Condition única (jogadores "dormem"
      até ser a vez deles).
    - Fazer broadcast de mensagens pra todos os jogadores.
    - Gerenciar lobby (pronto), WO e revanche.

Fluxo de estados:
    VAZIA
      → AGUARDANDO_JOGADORES (1 jogador)
      → LOBBY (2 jogadores, pelo menos 1 ainda não pronto)
      → EM_JOGO (ambos prontos)
      → FINALIZADA (fim da partida)
          ├─ ambos aceitam revanche → volta pra EM_JOGO
          └─ alguém recusa / cai     → volta pra AGUARDANDO_JOGADORES ou VAZIA

Regra de WO:
    Se um jogador cair no lobby → o outro continua esperando
    (sala volta pra AGUARDANDO_JOGADORES).
    Se um jogador cair durante a partida → o outro vence a partida,
    sem revanche. Sala volta pra AGUARDANDO_JOGADORES.
"""

import threading
from typing import Optional

from common import protocolo as p
from common.excecoes import (
    SalaCheiaError,
    JogadorJaNaSalaError,
    EstadoSalaInvalidoError,
)

from server.jogador import Jogador


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

        # Partida em andamento (criada quando ambos prontos)
        self.partida = None   # type: ignore  # será Partida

        # Revanche: {"jogador1": bool, "jogador2": bool}
        self.revanche: dict[str, bool] = {
            "jogador1": False,
            "jogador2": False,
        }

        # ---------------------------------------------------
        # Concorrência
        # ---------------------------------------------------
        # RLock: protege o estado da sala (estado, jogadores, revanche).
        # Permite reentrada (evita deadlock em chamadas aninhadas).
        self.lock = threading.RLock()

        # Condition: usada pra sincronizar turnos da partida.
        # A thread de cada jogador "dorme" até ser a vez dela.
        self.condicao = threading.Condition(self.lock)

    # ========================================================
    # Consultas rápidas
    # ========================================================

    def esta_cheia(self) -> bool:
        return all(j is not None for j in self.jogadores.values())

    def esta_vazia(self) -> bool:
        return all(j is None for j in self.jogadores.values())

    def jogadores_ativos(self) -> list[Jogador]:
        """Retorna lista (sem Nones) dos jogadores presentes."""
        return [j for j in self.jogadores.values() if j is not None]

    def slot_livre(self) -> Optional[str]:
        """Retorna 'jogador1' ou 'jogador2' se houver vaga, senão None."""
        for slot, j in self.jogadores.items():
            if j is None:
                return slot
        return None

    def adversario_de(self, slot: str) -> Optional[Jogador]:
        """Retorna o Jogador do outro slot (ou None se não houver)."""
        outro = "jogador2" if slot == "jogador1" else "jogador1"
        return self.jogadores.get(outro)

    # ========================================================
    # Entrada / saída de jogadores
    # ========================================================

    def adicionar_jogador(self, jogador: Jogador) -> None:
        """
        Coloca um jogador na sala (no primeiro slot livre).

        Transições:
            VAZIA → AGUARDANDO_JOGADORES (1 jogador)
            AGUARDANDO_JOGADORES → LOBBY (2 jogadores)

        Levanta:
            SalaCheiaError: se a sala já está cheia.
        """
        with self.lock:
            if self.esta_cheia():
                raise SalaCheiaError(f"Sala {self.id} já está cheia.")

            if self.estado in (Estado.EM_JOGO, Estado.FINALIZADA):
                raise EstadoSalaInvalidoError(
                    f"Sala {self.id} não aceita novos jogadores "
                    f"(estado: {self.estado})."
                )

            # Evita duplicar o mesmo jogador (mesmo socket)
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

            # Atualiza estado
            if self.esta_cheia():
                self.estado = Estado.LOBBY
            else:
                self.estado = Estado.AGUARDANDO_JOGADORES

            # Notifica quem estiver esperando (lobby)
            self.condicao.notify_all()

    def remover_jogador(self, slot: str, motivo: str = "desconectado") -> None:
        """
        Remove um jogador da sala (por desconexão ou saída voluntária).

        Regra de WO:
            - Se havia partida em andamento → adversário vence, sem revanche.
            - Sala volta pra AGUARDANDO_JOGADORES (se sobrar 1 jogador)
              ou VAZIA (se não sobrar ninguém).
        """
        with self.lock:
            jogador = self.jogadores.get(slot)
            if jogador is None:
                return

            # Se havia partida em andamento, considera WO
            if self.estado == Estado.EM_JOGO and self.partida is not None:
                adversario = self.adversario_de(slot)
                # Avisa a partida do WO (ela decide o vencedor e encerra)
                try:
                    self.partida.registrar_wo(slot)
                except Exception:
                    pass  # partida pode já estar encerrando
                if adversario is not None:
                    self.broadcast({
                        "tipo": "desconectando",
                        "motivo": f"{jogador.nome or slot} desconectou. "
                                  f"Você venceu a partida por WO.",
                    })

            # Remove o jogador
            jogador.fechar()
            self.jogadores[slot] = None
            self.partida = None
            self.revanche = {"jogador1": False, "jogador2": False}

            # Reajusta estado
            if self.esta_vazia():
                self.estado = Estado.VAZIA
            elif self.esta_cheia():
                self.estado = Estado.LOBBY
            else:
                self.estado = Estado.AGUARDANDO_JOGADORES

            self.condicao.notify_all()

    # ========================================================
    # Lobby
    # ========================================================

    def marcar_pronto(self, slot: str) -> bool:
        """
        Marca um jogador como pronto.

        Returns:
            True se ambos ficaram prontos (partida deve iniciar),
            False caso contrário.
        """
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
        """Envia o estado atual do lobby pra todos os jogadores."""
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
    # Partida
    # ========================================================

    def iniciar_partida(self) -> None:
        """
        Cria a Partida e muda o estado pra EM_JOGO.
        Deve ser chamada quando ambos estiverem prontos.
        """
        with self.lock:
            if not self.esta_cheia():
                raise EstadoSalaInvalidoError(
                    "Não é possível iniciar partida sem 2 jogadores."
                )

            # Import tardio pra evitar dependência circular
            from server.partida import Partida

            self.estado = Estado.EM_JOGO
            self.revanche = {"jogador1": False, "jogador2": False}
            self.partida = Partida(self)

            # A Partida roda em uma thread própria (loop de jogo)
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

    def registrar_revanche(self, slot: str, aceitou: bool) -> Optional[str]:
        """
        Registra o voto de revanche de um jogador.

        Returns:
            - "reiniciar" se ambos aceitaram
            - "encerrar"  se alguém recusou
            - None        se ainda falta o voto do outro
        """
        with self.lock:
            if self.estado != Estado.FINALIZADA:
                raise EstadoSalaInvalidoError(
                    "Revanche só pode ser registrada após a partida."
                )

            self.revanche[slot] = aceitou

            if not aceitou:
                return "encerrar"

            # Vê se o outro também já aceitou
            outro = "jogador2" if slot == "jogador1" else "jogador1"
            if self.revanche.get(outro):
                return "reiniciar"

            return None

    def reiniciar_para_revanche(self) -> None:
        """Reseta pontos e prontos e inicia uma nova partida."""
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
        """Envia mensagem pra todos os jogadores ativos da sala."""
        for j in self.jogadores_ativos():
            j.enviar(mensagem)

    def enviar_para(self, slot: str, mensagem: dict) -> None:
        """Envia mensagem pra um jogador específico."""
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