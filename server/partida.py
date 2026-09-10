"""
STUB temporário da Partida. Será substituído pelo código real
no próximo passo.

Por enquanto, só registra que foi chamada e dorme um pouco,
simulando uma partida.
"""

import time


class Partida:
    def __init__(self, sala):
        self.sala = sala

    def rodar(self) -> None:
        """Loop de jogo (stub)."""
        self.sala.broadcast({
            "tipo": "fim_partida",
            "vencedor": "jogador1",
            "pontos": {"jogador1": 12, "jogador2": 0},
            "stub": True,
        })
        self.sala.finalizar_partida("jogador1")

    def registrar_wo(self, slot: str) -> None:
        """Registra WO (stub)."""
        pass