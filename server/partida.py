"""
Classe Partida: roda o jogo do Truco dentro de uma Sala.

Responsabilidades:
    - Sorteio inicial, alternância de quem começa a mão.
    - Distribuição de cartas e envio de mao_inicial.
    - Fluxo de 3 vazas (ou "mostrar a maior" se a 1ª empatar).
    - Fluxo de truco/retruco/vale-nove/vale-doze.
    - Fluxo de mão de 11 e mão de ferro.
    - Cálculo de pontos e detecção de fim de partida.
    - Registro de WO (desconexão/timeout).

Arquitetura:
    - Roda em uma thread própria (Sala.iniciar_partida a dispara).
    - Consome mensagens da fila de cada jogador (jogador.fila).
    - Sincroniza via Sala.condicao (thread leitora notifica).
"""

import queue
import random
import time
from typing import Optional

from common.cartas import Carta, Baralho, comparar, maior_carta
from common import protocolo as p
from server.config import (
    DEBUG,
    PONTOS_PARTIDA,
    TIMEOUT_JOGADA,
    TIMEOUT_TRUCO,
    TIMEOUT_REVELAR_MAIOR,
    TIMEOUT_DECISAO_MAO_11,
    TIMEOUT_ESCOLHA_FERRO,
)
from server.jogador import Jogador
from server.sala import Sala


# ============================================================
# Constantes auxiliares
# ============================================================

SLOT1 = "jogador1"
SLOT2 = "jogador2"

# Valor da mão em cada nível de truco (0 = mão normal).
# O índice é o nível atual; o valor é quantos pontos vale a mão.
VALORES_NIVEL = {
    0: 1,    # mão normal
    1: 3,    # truco
    2: 6,    # retruco
    3: 9,    # vale-nove
    4: 12,   # vale-doze
}

# Nome amigável de cada nível (usado só em logs/mensagens).
NOMES_NIVEL = {
    1: "truco",
    2: "retruco",
    3: "vale-nove",
    4: "vale-doze",
}


# ============================================================
# Classe Partida
# ============================================================

class Partida:

    def __init__(self, sala: Sala):
        self.sala = sala

        # Atalhos pros dois jogadores
        self.j1 = sala.jogadores[SLOT1]
        self.j2 = sala.jogadores[SLOT2]
        self.jogadores = {SLOT1: self.j1, SLOT2: self.j2}

        # Placar acumulado da partida (vai até 12)
        self.placar = {SLOT1: 0, SLOT2: 0}

        # Controle global
        self.terminou = False
        self.vencedor_wo: Optional[str] = None

        # Estado da mão atual
        self.comeca_mao: Optional[str] = None
        self.nivel_truco = 0       # 0=sem truco, 1=truco, 2=retruco...
        self.valor_mao = 1         # quantos pontos vale a mão atual

        # Estado da vaza atual
        self.cartas_na_mesa: dict[str, Optional[Carta]] = {
            SLOT1: None, SLOT2: None,
        }
        self.vitorias_vaza = {SLOT1: 0, SLOT2: 0}
        self.quem_ganhou_vaza_1: Optional[str] = None
        self.quem_comecou_vaza: Optional[str] = None

        # Controle de truco corrido: quando alguém corre, a mão
        # NÃO termina imediatamente aqui dentro — sinalizamos via essas
        # flags e quem decide o vencedor é o loop principal (rodar()).
        self._mao_encerrada_por_truco = False
        self._vencedor_mao_por_truco: Optional[str] = None
        self._pontos_mao_por_truco = 0

        # Controle da mão de 11
        self._em_mao_de_11 = False
        # Quantos pontos o vencedor da mão de 11 leva.
        # Regra: quem tem 11 e GANHA leva 1; quem tem 11 e PERDE dá 3.
        self._pontos_mao_11 = 0

    # ========================================================
    # LOOP PRINCIPAL
    # ========================================================

    def rodar(self) -> None:
        """
        Loop principal da partida (roda em thread própria).

        Ciclo:
            1. Se alguém já fez 12+, encerra.
            2. Decide o tipo da próxima mão (normal / 11 / ferro).
            3. Executa a mão (retorna o slot vencedor ou None).
            4. Atualiza placar e broadcast de fim de mão.
            5. Alterna quem começa e repete.
        """
        try:
            self._log("PARTIDA INICIADA")
            self._sortear_quem_comeca()

            while not self.terminou:
                # Encerra se alguém já bateu 12
                if self._alguem_atingiu_12():
                    break

                tipo = self._tipo_de_mao()

                if tipo == "ferro":
                    vencedor = self._mao_de_ferro()
                elif tipo == "onze":
                    vencedor = self._mao_de_11()
                else:
                    vencedor = self._mao_normal()

                if self.terminou:
                    break

                # ------------------------------------------------
                # Atualiza placar conforme o resultado da mão.
                # ------------------------------------------------
                # Caso especial: mão encerrada por truco corrido.
                # O placar já foi somado dentro do _iniciar_truco,
                # então aqui só sinalizamos o fim da mão.
                if self._mao_encerrada_por_truco:
                    vencedor = self._vencedor_mao_por_truco
                    self._log(
                        f"Mão encerrada por truco corrido. "
                        f"Placar: {self.placar}"
                    )
                    self.sala.broadcast({
                        "tipo": p.T_FIM_MAO,
                        "vencedor": vencedor,
                        "pontos": dict(self.placar),
                    })
                    self._mao_encerrada_por_truco = False
                    self._vencedor_mao_por_truco = None
                    self._pontos_mao_por_truco = 0

                # Caso normal
                elif vencedor is not None:
                    # Mão de 11 tem valor especial:
                    #   - se o jogador de 11 GANHOU: +1
                    #   - se o jogador de 11 PERDEU: adversário +3
                    if self._em_mao_de_11:
                        pontos = self._pontos_mao_11 or self.valor_mao
                        self.placar[vencedor] += pontos
                        self._log(
                            f"FIM DA MÃO DE 11: {vencedor} ganhou "
                            f"{pontos} ponto(s). Placar: {self.placar}"
                        )
                    else:
                        self.placar[vencedor] += self.valor_mao
                        self._log(
                            f"FIM DA MÃO: {vencedor} ganhou "
                            f"{self.valor_mao} ponto(s). "
                            f"Placar: {self.placar}"
                        )

                    self.sala.broadcast({
                        "tipo": p.T_FIM_MAO,
                        "vencedor": vencedor,
                        "pontos": dict(self.placar),
                    })

                    # Reset dos controles de mão de 11
                    self._em_mao_de_11 = False
                    self._pontos_mao_11 = 0

                # Alterna quem começa a próxima mão (J1 ↔ J2)
                self.comeca_mao = SLOT2 if self.comeca_mao == SLOT1 else SLOT1

                # Pequeno delay pra não floodar clientes
                time.sleep(0.5)

            # Fim de partida: vencedor por WO tem prioridade.
            if self.vencedor_wo:
                vencedor = self.vencedor_wo
            else:
                vencedor = self._quem_atingiu_12()

            self._fim_de_partida(vencedor)

        except Exception as e:
            if DEBUG:
                import traceback
                traceback.print_exc()
            self._log(f"ERRO NA PARTIDA: {e}")
            self.sala.finalizar_partida(SLOT1)

    # ========================================================
    # SETUP / SORTEIO
    # ========================================================

    def _sortear_quem_comeca(self) -> None:
        """Sorteia quem começa a primeira mão (só na 1ª)."""
        self.comeca_mao = random.choice([SLOT1, SLOT2])
        self._log(f"Sorteio: {self.comeca_mao} começa a partida.")

    def _alguem_atingiu_12(self) -> bool:
        """True se algum jogador chegou (ou passou) de 12 pontos."""
        return (self.placar[SLOT1] >= PONTOS_PARTIDA or
                self.placar[SLOT2] >= PONTOS_PARTIDA)

    def _quem_atingiu_12(self) -> Optional[str]:
        """Retorna o slot do vencedor por pontos (ou None)."""
        if self.placar[SLOT1] >= PONTOS_PARTIDA:
            return SLOT1
        if self.placar[SLOT2] >= PONTOS_PARTIDA:
            return SLOT2
        return None

    def _tipo_de_mao(self) -> str:
        """
        Decide o tipo da próxima mão conforme o placar:
            - 'ferro'  : ambos com 11
            - 'onze'   : alguém com 11
            - 'normal' : caso contrário
        """
        p1 = self.placar[SLOT1]
        p2 = self.placar[SLOT2]
        if p1 == 11 and p2 == 11:
            return "ferro"
        if p1 == 11 or p2 == 11:
            return "onze"
        return "normal"

    # ========================================================
    # MÃO NORMAL
    # ========================================================

    def _mao_normal(self) -> Optional[str]:
        """
        Executa uma mão normal.

        Fluxo:
            - Vaza 1: quem começa joga primeiro.
                - Se NÃO empatar → continua pra vaza 2.
                - Se EMPATAR → vai direto pro 'mostrar a maior' e acaba.
            - Vaza 2: se alguém fizer 2 vitórias → mão acaba.
            - Vaza 3: quem ganhar leva a mão. Empate → quem ganhou a 1ª.

        Retorna o slot vencedor ou None (se houve WO/truco corrido).
        """
        self._log(f"--- MÃO NORMAL (começa: {self.comeca_mao}) ---")

        # Reseta o estado da mão
        self.nivel_truco = 0
        self.valor_mao = 1
        self.vitorias_vaza = {SLOT1: 0, SLOT2: 0}
        self.quem_ganhou_vaza_1 = None
        self._mao_encerrada_por_truco = False
        self._vencedor_mao_por_truco = None
        self._pontos_mao_por_truco = 0
        self._em_mao_de_11 = False

        # Distribui 3 cartas pra cada
        baralho = Baralho()
        baralho.embaralhar()
        for slot, jog in self.jogadores.items():
            mao = baralho.distribuir(3)
            jog.mao = [str(c) for c in mao]

        self._enviar_mao_inicial()

        # -------------------- VAZA 1 --------------------
        self.quem_comecou_vaza = self.comeca_mao
        vencedor_v1 = self._jogar_vaza(numero=1)

        if self.terminou:
            return None
        if self._mao_encerrada_por_truco:
            return self._vencedor_mao_por_truco

        if vencedor_v1 is None:
            # Vaza 1 empatou → não tem vaza 2 nem 3.
            self._log("Vaza 1 empatou → MOSTRAR A MAIOR")
            return self._mostrar_a_maior(
                quem_revela_primeiro=self.comeca_mao
            )

        self.vitorias_vaza[vencedor_v1] += 1
        self.quem_ganhou_vaza_1 = vencedor_v1

        # -------------------- VAZA 2 --------------------
        # Quem ganhou a vaza 1 começa a vaza 2.
        self.quem_comecou_vaza = vencedor_v1
        vencedor_v2 = self._jogar_vaza(numero=2)

        if self.terminou:
            return None
        if self._mao_encerrada_por_truco:
            return self._vencedor_mao_por_truco

        if vencedor_v2 is None:
            # Empate na vaza 2 → vence quem ganhou a vaza 1
            self._log("Vaza 2 empatou → Vence quem ganhou a 1ª vaza!")
            return self.quem_ganhou_vaza_1

        self.vitorias_vaza[vencedor_v2] += 1

        # Alguém já fez 2 vitórias? Então a mão acabou.
        if self.vitorias_vaza[SLOT1] == 2:
            return SLOT1
        if self.vitorias_vaza[SLOT2] == 2:
            return SLOT2

        # -------------------- VAZA 3 --------------------
        # Quem ganhou a vaza 2 começa a vaza 3.
        self.quem_comecou_vaza = vencedor_v2
        vencedor_v3 = self._jogar_vaza(numero=3)

        if self.terminou:
            return None
        if self._mao_encerrada_por_truco:
            return self._vencedor_mao_por_truco

        if vencedor_v3 is not None:
            self.vitorias_vaza[vencedor_v3] += 1

        # Empate final (1x1 + empate na 3ª) → quem ganhou a 1ª leva
        if self.vitorias_vaza[SLOT1] == self.vitorias_vaza[SLOT2]:
            self._log("3ª vaza empatou → vence quem ganhou a 1ª vaza")
            return self.quem_ganhou_vaza_1

        if self.vitorias_vaza[SLOT1] > self.vitorias_vaza[SLOT2]:
            return SLOT1
        return SLOT2

    def _jogar_vaza(self, numero: int) -> Optional[str]:
        """
        Executa uma vaza completa.

        - Ordem: quem começou a vaza joga primeiro, depois o outro.
        - Cada jogador recebe 'sua_vez' e o servidor espera a jogada.
        - Ao final, compara as cartas e faz broadcast do vencedor.

        Retorna:
            - slot vencedor (SLOT1/SLOT2)
            - None se empatou
            - None se houve WO / truco corrido (checar flags externas)
        """
        self._log(
            f"--- VAZA {numero} (começa: {self.quem_comecou_vaza}) ---"
        )

        self.cartas_na_mesa = {SLOT1: None, SLOT2: None}

        ordem = [
            self.quem_comecou_vaza,
            SLOT2 if self.quem_comecou_vaza == SLOT1 else SLOT1,
        ]

        for slot in ordem:
            if self.terminou:
                return None

            # Avisa o jogador que é a vez dele
            self.sala.enviar_para(slot, {"tipo": p.T_SUA_VEZ})

            # Espera a jogada (ou truco no meio)
            carta = self._aguardar_jogada(slot)

            if self.terminou:
                return None
            if self._mao_encerrada_por_truco:
                return None

            if carta is None:
                # Timeout → WO
                self._log(f"Timeout de {slot} → WO")
                self.registrar_wo(slot)
                return None

            # Guarda a carta e avisa os dois
            self.cartas_na_mesa[slot] = carta
            self.sala.broadcast({
                "tipo": p.T_CARTA_JOGADA,
                "jogador": slot,
                "carta": str(carta),
            })

        # As duas cartas estão na mesa: resolve a vaza
        c1 = self.cartas_na_mesa[SLOT1]
        c2 = self.cartas_na_mesa[SLOT2]

        if c1 is None or c2 is None:
            return None

        resultado = comparar(c1, c2)

        if resultado == 0:
            self._log(f"Vaza {numero} EMPATOU ({c1} vs {c2})")
            self.sala.broadcast({
                "tipo": p.T_RESULTADO_VAZA,
                "vencedor": None,
                "vaza": numero,
            })
            return None

        vencedor = SLOT1 if resultado > 0 else SLOT2
        self._log(f"Vaza {numero}: {vencedor} venceu ({c1} vs {c2})")
        self.sala.broadcast({
            "tipo": p.T_RESULTADO_VAZA,
            "vencedor": vencedor,
            "vaza": numero,
        })
        return vencedor

    # ========================================================
    # ESPERA DE JOGADA (com truco no meio)
    # ========================================================

    def _aguardar_jogada(self, slot: str) -> Optional[Carta]:
        """
        Espera o jogador 'slot' jogar uma carta.

        Detalhe importante: o pedido de truco NÃO consome a vez.
        Se o jogador mandar 'truco', o servidor resolve o fluxo
        (aceitar/correr/aumentar) e VOLTA a esperar a jogada dele.

        Exceção: durante a mão de 11, truco é proibido.

        Retorna:
            - Carta jogada
            - None em caso de timeout/WO/truco corrido
              (checar self.terminou e self._mao_encerrada_por_truco)
        """
        deadline = time.time() + TIMEOUT_JOGADA

        while time.time() < deadline and not self.terminou:
            msg = self._esperar_mensagem(
                slot,
                tipos_validos={p.T_JOGAR, p.T_TRUCO},
                timeout=deadline - time.time(),
            )

            if self.terminou:
                return None
            if msg is None:
                return None  # timeout

            tipo = msg.get("tipo")

            # ------------------------------------------------
            # TRUCO (não consome a vez)
            # ------------------------------------------------
            if tipo == p.T_TRUCO:
                # Regra: não se pode trucar na mão de 11 (individual
                # ou de ferro). Se o jogador tentar, devolve erro
                # e continua esperando a jogada.
                if self._em_mao_de_11:
                    self.sala.enviar_para(slot, {
                        "tipo": p.T_ERRO,
                        "codigo": "truco_proibido_mao_11",
                        "msg": "Não é permitido trucar na mão de 11.",
                    })
                    continue

                if not self._iniciar_truco(slot):
                    return None  # WO durante o truco

                if self._mao_encerrada_por_truco:
                    return None  # truco corrido → mão acaba
                continue

            # ------------------------------------------------
            # JOGAR
            # ------------------------------------------------
            if tipo == p.T_JOGAR:
                carta_str = msg.get("carta")
                try:
                    carta = Carta.from_str(carta_str)
                except ValueError:
                    self.sala.enviar_para(slot, {
                        "tipo": p.T_ERRO,
                        "codigo": "carta_invalida",
                        "msg": f"Carta inválida: {carta_str}",
                    })
                    continue

                if str(carta) not in self.jogadores[slot].mao:
                    self.sala.enviar_para(slot, {
                        "tipo": p.T_ERRO,
                        "codigo": "carta_nao_esta_na_mao",
                        "msg": f"A carta {carta} não está na sua mão.",
                    })
                    continue

                # Remove da mão e devolve pro chamador
                self.jogadores[slot].mao.remove(str(carta))
                return carta

        return None  # timeout

    # ========================================================
    # MOSTRAR A MAIOR
    # ========================================================

    def _mostrar_a_maior(
        self, quem_revela_primeiro: str
    ) -> Optional[str]:
        """
        Executa o fluxo de 'mostrar a maior'.

        Ocorre APENAS quando a vaza 1 empata.

        Assimetria proposital:
            - O primeiro jogador (quem começou a vaza 1) revela
              SEM ver a carta do adversário.
            - O segundo PODE trucar depois de ver a carta revelada,
              aproveitando a informação.

        Valores:
            - Sem truco aceito: quem tem a maior ganha 1 ponto.
            - Truco aceito: quem tem a maior ganha o valor do truco
              (3, 6, 9 ou 12).
        """
        self.nivel_truco = 0
        self.valor_mao = 1

        outro = SLOT2 if quem_revela_primeiro == SLOT1 else SLOT1

        self.sala.broadcast({
            "tipo": p.T_MOSTRAR_MAIOR,
            "primeiro": quem_revela_primeiro,
        })

        # 1) Primeiro revela (sem ver nada do outro)
        carta1 = self._aguardar_revelacao(quem_revela_primeiro)
        if self.terminou:
            return None
        if carta1 is None:
            self.registrar_wo(quem_revela_primeiro)
            return None

        self.sala.broadcast({
            "tipo": p.T_MAIOR_REVELADA,
            "jogador": quem_revela_primeiro,
            "carta": str(carta1),
        })

        # 2) Segundo pode trucar OU revelar direto.
        #    Se trucar, resolve antes de revelar.
        carta2 = self._aguardar_revelacao_ou_truco(outro)
        if self.terminou:
            return None
        if carta2 is None:
            self.registrar_wo(outro)
            return None

        self.sala.broadcast({
            "tipo": p.T_MAIOR_REVELADA,
            "jogador": outro,
            "carta": str(carta2),
        })

        # 3) Decide vencedor
        resultado = comparar(carta1, carta2)
        if resultado == 0:
            # Não deveria acontecer (cartas únicas no baralho),
            # mas em caso de empate exato, quem revelou primeiro leva.
            vencedor = quem_revela_primeiro
        else:
            vencedor = quem_revela_primeiro if resultado > 0 else outro

        self._log(
            f"MOSTRAR A MAIOR: {vencedor} ganhou "
            f"(valor da mão: {self.valor_mao})"
        )
        self.sala.broadcast({
            "tipo": p.T_FIM_MOSTRAR_MAIOR,
            "vencedor": vencedor,
            "pontos": self.valor_mao,
        })

        return vencedor

    def _aguardar_revelacao(self, slot: str) -> Optional[Carta]:
        """Espera a revelação da maior carta de um jogador (sem truco)."""
        msg = self._esperar_mensagem(
            slot,
            tipos_validos={p.T_REVELAR_MAIOR},
            timeout=TIMEOUT_REVELAR_MAIOR,
        )
        if msg is None:
            return None
        return self._validar_revelacao(slot, msg)

    def _aguardar_revelacao_ou_truco(self, slot: str) -> Optional[Carta]:
        """
        Espera do segundo jogador: revelar a maior OU trucar.

        Se ele trucar, resolve o truco (aceitar/correr/aumentar) e
        depois volta a esperar a revelação. Isso explora a assimetria
        proposital do 'mostrar a maior'.
        """
        deadline = time.time() + TIMEOUT_REVELAR_MAIOR

        while time.time() < deadline and not self.terminou:
            msg = self._esperar_mensagem(
                slot,
                tipos_validos={p.T_REVELAR_MAIOR, p.T_TRUCO},
                timeout=deadline - time.time(),
            )
            if self.terminou:
                return None
            if msg is None:
                return None

            tipo = msg.get("tipo")

            if tipo == p.T_TRUCO:
                if not self._iniciar_truco(slot):
                    return None
                continue

            if tipo == p.T_REVELAR_MAIOR:
                return self._validar_revelacao(slot, msg)

        return None

    def _validar_revelacao(self, slot: str, msg: dict) -> Optional[Carta]:
        """
        Valida se a carta revelada é de fato a maior da mão do jogador.

        Regras:
            - A carta precisa estar na mão.
            - A carta precisa ser a maior da mão (regra do jogo).
        """
        carta_str = msg.get("carta")
        try:
            carta = Carta.from_str(carta_str)
        except ValueError:
            self.sala.enviar_para(slot, {
                "tipo": p.T_ERRO,
                "codigo": "carta_invalida",
                "msg": f"Carta inválida: {carta_str}",
            })
            return None

        mao = self.jogadores[slot].mao
        if str(carta) not in mao:
            self.sala.enviar_para(slot, {
                "tipo": p.T_ERRO,
                "codigo": "carta_nao_esta_na_mao",
                "msg": f"A carta {carta} não está na sua mão.",
            })
            return None

        maior = maior_carta([Carta.from_str(c) for c in mao])
        if maior is None or str(maior) != str(carta):
            self.sala.enviar_para(slot, {
                "tipo": p.T_ERRO,
                "codigo": "nao_e_a_maior",
                "msg": "Você deve revelar a maior carta da sua mão.",
            })
            return None

        return carta

    # ========================================================
    # TRUCO
    # ========================================================

    def _iniciar_truco(self, slot_pediu: str) -> bool:
        """
        Inicia o fluxo de truco.

        Funcionamento:
            - Sobe o nível atual (truco → retruco → vale-nove → vale-doze).
            - Envia 'truco_pedido' pro adversário.
            - Espera resposta:
                - 'aceitar'   → só sobe o valor da mão e segue o jogo.
                - 'correr'    → adversário ganha o valor ANTERIOR.
                                Marca a mão como encerrada via flags.
                - 'aumentar'  → inverte os papéis e continua o loop.
            - Pode acontecer várias vezes seguidas (aumentos sucessivos).

        Retorna:
            True  → truco resolvido (aceito ou corrido)
            False → houve WO durante o processo
        """
        if self.nivel_truco >= 4:
            # Já está no máximo (vale-doze), não pode subir mais.
            self.sala.enviar_para(slot_pediu, {
                "tipo": p.T_ERRO,
                "codigo": "truco_maximo",
                "msg": "O truco já está no valor máximo (vale-doze).",
            })
            return True

        # Sobe o nível e recalcula o valor da mão
        self.nivel_truco += 1
        self.valor_mao = VALORES_NIVEL[self.nivel_truco]
        nome = NOMES_NIVEL[self.nivel_truco]

        outro = SLOT2 if slot_pediu == SLOT1 else SLOT1

        self._log(
            f"{slot_pediu} pediu {nome} (valor {self.valor_mao})"
        )

        self.sala.enviar_para(outro, {
            "tipo": p.T_TRUCO_PEDIDO,
            "de": slot_pediu,
            "valor": self.valor_mao,
        })

        # Loop de respostas — permite aumentos sucessivos.
        while True:
            msg = self._esperar_mensagem(
                outro,
                tipos_validos={p.T_RESPOSTA_TRUCO},
                timeout=TIMEOUT_TRUCO,
            )
            if self.terminou:
                return False
            if msg is None:
                self.registrar_wo(outro)
                return False

            acao = msg.get("acao")

            # ------------------------------------------------
            # CORRER → quem pediu ganha o valor ANTERIOR
            # ------------------------------------------------
            if acao == "correr":
                valor_ganho = VALORES_NIVEL[self.nivel_truco - 1]
                self.valor_mao = valor_ganho

                self._log(
                    f"{outro} correu. {slot_pediu} ganha {valor_ganho}."
                )

                # Soma os pontos AQUI e sinaliza pro loop principal
                # que a mão acabou por truco corrido.
                self.placar[slot_pediu] += valor_ganho
                self._mao_encerrada_por_truco = True
                self._vencedor_mao_por_truco = slot_pediu
                self._pontos_mao_por_truco = valor_ganho

                self.sala.broadcast({
                    "tipo": p.T_TRUCO_CORRIDO,
                    "quem_correu": outro,
                    "vencedor": slot_pediu,
                    "pontos": valor_ganho,
                })
                return True

            # ------------------------------------------------
            # ACEITAR → só sobe o valor da mão
            # ------------------------------------------------
            if acao == "aceitar":
                self._log(f"{outro} aceitou {nome}.")
                self.sala.broadcast({
                    "tipo": p.T_TRUCO_ACEITO,
                    "valor": self.valor_mao,
                })
                return True

            # ------------------------------------------------
            # AUMENTAR → inverte papéis e continua o loop
            # ------------------------------------------------
            if acao == "aumentar":
                if self.nivel_truco >= 4:
                    self.sala.enviar_para(outro, {
                        "tipo": p.T_ERRO,
                        "codigo": "truco_maximo",
                        "msg": "Não é possível aumentar além do vale-doze.",
                    })
                    continue

                # Quem respondeu vira quem pede.
                slot_pediu, outro = outro, slot_pediu
                self.nivel_truco += 1
                self.valor_mao = VALORES_NIVEL[self.nivel_truco]
                nome = NOMES_NIVEL[self.nivel_truco]

                self._log(f"{slot_pediu} aumentou para {nome}.")
                self.sala.enviar_para(outro, {
                    "tipo": p.T_TRUCO_PEDIDO,
                    "de": slot_pediu,
                    "valor": self.valor_mao,
                })
                continue

            # Ação desconhecida
            self.sala.enviar_para(outro, {
                "tipo": p.T_ERRO,
                "codigo": "resposta_invalida",
                "msg": f"Ação inválida: {acao}",
            })

    # ========================================================
    # MÃO DE 11
    # ========================================================

    def _mao_de_11(self) -> Optional[str]:
        """
        Executa a mão de 11.

        Regras:
            - Só o jogador com 11 vê as cartas e decide.
            - 'correr'  → adversário ganha 1 ponto.
            - 'jogar'   → mão normal (3 vazas, SEM truco):
                - se o jogador de 11 GANHAR → ele ganha 1 ponto
                - se o jogador de 11 PERDER → adversário ganha 3 pontos

        Retorna slot vencedor, ou None (WO).
        """
        self._log("--- MÃO DE 11 ---")

        # Marca o estado pra bloquear truco em _aguardar_jogada
        self._em_mao_de_11 = True
        self._pontos_mao_11 = 0

        # Descobre quem tem 11
        slot_11 = SLOT1 if self.placar[SLOT1] == 11 else SLOT2
        outro = SLOT2 if slot_11 == SLOT1 else SLOT1

        # Distribui cartas (só o jogador de 11 vê)
        baralho = Baralho()
        baralho.embaralhar()
        mao_11 = baralho.distribuir(3)
        self.jogadores[slot_11].mao = [str(c) for c in mao_11]

        # Avisa o jogador com 11
        self.sala.enviar_para(slot_11, {
            "tipo": p.T_MAO_DE_11,
            "cartas": [str(c) for c in mao_11],
            "pontos": dict(self.placar),
        })

        # Avisa o outro (só informativo)
        self.sala.enviar_para(outro, {
            "tipo": p.T_MAO_DE_11,
            "cartas": [],
            "pontos": dict(self.placar),
            "aguardando": slot_11,
        })

        # Espera decisão
        msg = self._esperar_mensagem(
            slot_11,
            tipos_validos={p.T_DECISAO_MAO_11},
            timeout=TIMEOUT_DECISAO_MAO_11,
        )
        if self.terminou:
            return None
        if msg is None:
            self.registrar_wo(slot_11)
            return None

        acao = msg.get("acao")

        # ------------------------------------------------
        # CORRER → adversário ganha 1 ponto
        # ------------------------------------------------
        if acao == "correr":
            self._log(f"{slot_11} correu da mão de 11.")
            self.valor_mao = 1
            self._pontos_mao_11 = 1
            return outro

        # ------------------------------------------------
        # JOGAR → mão normal sem truco
        # ------------------------------------------------
        if acao == "jogar":
            self._log(f"{slot_11} decidiu jogar a mão de 11.")
            vencedor = self._jogar_mao_11_normal(slot_11, outro)

            # Regra de pontos:
            #   - Se o jogador de 11 ganhou → 1 ponto.
            #   - Se ele perdeu → adversário ganha 3 pontos.
            if vencedor == slot_11:
                self._pontos_mao_11 = 1
            else:
                self._pontos_mao_11 = 3

            return vencedor

        return None

    def _jogar_mao_11_normal(
        self, slot_11: str, outro: str
    ) -> Optional[str]:
        """
        Mão de 11 normal — 3 vazas, SEM truco.

        O vencedor é retornado; o valor dos pontos é decidido
        pela `_mao_de_11` (1 se o jogador de 11 ganhar, 3 se perder).
        """
        # Distribui cartas pro outro também (agora ele vê as dele)
        baralho = Baralho()
        baralho.embaralhar()
        mao_outro = baralho.distribuir(3)
        self.jogadores[outro].mao = [str(c) for c in mao_outro]

        # Envia mao_inicial pro outro (não tem truco nessa mão)
        self.sala.enviar_para(outro, {
            "tipo": p.T_MAO_INICIAL,
            "cartas": [str(c) for c in mao_outro],
            "pontos": dict(self.placar),
            "comeca": slot_11,
        })

        self.valor_mao = 1
        self.vitorias_vaza = {SLOT1: 0, SLOT2: 0}
        self.quem_ganhou_vaza_1 = None
        self.quem_comecou_vaza = slot_11

        # Vaza 1
        v1 = self._jogar_vaza_sem_truco(1, slot_11, outro)
        if self.terminou:
            return None
        if v1 is None:
            # Empate na vaza 1 → quem começou leva
            return slot_11
        self.vitorias_vaza[v1] += 1
        self.quem_ganhou_vaza_1 = v1

        # Vaza 2
        v2 = self._jogar_vaza_sem_truco(
            2, v1, SLOT2 if v1 == SLOT1 else SLOT1
        )
        if self.terminou:
            return None
        if v2 is not None:
            self.vitorias_vaza[v2] += 1

        if self.vitorias_vaza[SLOT1] == 2:
            return SLOT1
        if self.vitorias_vaza[SLOT2] == 2:
            return SLOT2

        # Vaza 3
        v3 = self._jogar_vaza_sem_truco(
            3, v1, SLOT2 if v1 == SLOT1 else SLOT1
        )
        if self.terminou:
            return None
        if v3 is not None:
            self.vitorias_vaza[v3] += 1

        if self.vitorias_vaza[SLOT1] == self.vitorias_vaza[SLOT2]:
            return self.quem_ganhou_vaza_1
        if self.vitorias_vaza[SLOT1] > self.vitorias_vaza[SLOT2]:
            return SLOT1
        return SLOT2

    def _jogar_vaza_sem_truco(
        self, numero: int, comeca: str, outro: str
    ) -> Optional[str]:
        """
        Executa uma vaza SEM permitir truco.

        Usada SOMENTE na mão de 11 — por isso não tem a lógica de
        truco que existe em `_aguardar_jogada`.

        Se a carta enviada for inválida ou não estiver na mão,
        devolve erro e continua esperando a jogada correta.
        """
        self.cartas_na_mesa = {SLOT1: None, SLOT2: None}

        for slot in [comeca, outro]:
            if self.terminou:
                return None

            self.sala.enviar_para(slot, {"tipo": p.T_SUA_VEZ})

            # Loop interno: só sai quando tiver uma carta válida.
            carta = None
            deadline = time.time() + TIMEOUT_JOGADA
            while time.time() < deadline and not self.terminou:
                msg = self._esperar_mensagem(
                    slot,
                    tipos_validos={p.T_JOGAR},
                    timeout=deadline - time.time(),
                )
                if self.terminou:
                    return None
                if msg is None:
                    self.registrar_wo(slot)
                    return None

                carta_str = msg.get("carta")
                try:
                    carta_tentativa = Carta.from_str(carta_str)
                except ValueError:
                    self.sala.enviar_para(slot, {
                        "tipo": p.T_ERRO,
                        "codigo": "carta_invalida",
                        "msg": f"Carta inválida: {carta_str}",
                    })
                    continue

                if str(carta_tentativa) not in self.jogadores[slot].mao:
                    self.sala.enviar_para(slot, {
                        "tipo": p.T_ERRO,
                        "codigo": "carta_nao_esta_na_mao",
                        "msg": f"A carta {carta_tentativa} não está na sua mão.",
                    })
                    continue

                carta = carta_tentativa
                break

            if carta is None:
                self.registrar_wo(slot)
                return None

            self.jogadores[slot].mao.remove(str(carta))
            self.cartas_na_mesa[slot] = carta
            self.sala.broadcast({
                "tipo": p.T_CARTA_JOGADA,
                "jogador": slot,
                "carta": str(carta),
            })

        c1 = self.cartas_na_mesa[SLOT1]
        c2 = self.cartas_na_mesa[SLOT2]
        if c1 is None or c2 is None:
            return None

        r = comparar(c1, c2)
        if r == 0:
            self.sala.broadcast({
                "tipo": p.T_RESULTADO_VAZA,
                "vencedor": None,
                "vaza": numero,
            })
            return None

        vencedor = SLOT1 if r > 0 else SLOT2
        self.sala.broadcast({
            "tipo": p.T_RESULTADO_VAZA,
            "vencedor": vencedor,
            "vaza": numero,
        })
        return vencedor

    # ========================================================
    # MÃO DE FERRO
    # ========================================================

    def _mao_de_ferro(self) -> Optional[str]:
        """
        Mão de ferro (ambos com 11 pontos).

        Regras:
            - Ninguém vê as cartas — só escolhe o ÍNDICE (0, 1, 2).
            - Vale 1 ponto.
            - Se empatar, roda OUTRA mão de ferro (loop até desempatar).
        """
        self._log("--- MÃO DE FERRO ---")

        self.valor_mao = 1
        self._em_mao_de_11 = True  # bloqueia truco nessa mão também

        while not self.terminou:
            # Nova distribuição a cada iteração (empate = novo jogo)
            baralho = Baralho()
            baralho.embaralhar()
            for slot in [SLOT1, SLOT2]:
                mao = baralho.distribuir(3)
                self.jogadores[slot].mao = [str(c) for c in mao]

            self.sala.broadcast({
                "tipo": p.T_MAO_DE_FERRO,
                "pontos": dict(self.placar),
            })

            self.vitorias_vaza = {SLOT1: 0, SLOT2: 0}
            self.quem_ganhou_vaza_1 = None

            resultado = self._jogar_ferro_3_vazas()
            if self.terminou:
                return None

            if resultado is None:
                # Empate total → joga de novo
                self._log("Mão de ferro empatou → nova mão de ferro.")
                continue

            self._log(f"Mão de ferro: {resultado} venceu.")
            self.sala.broadcast({
                "tipo": p.T_RESULTADO_FERRO,
                "vencedor": resultado,
                "pontos": 1,
            })
            return resultado

        return None

    def _jogar_ferro_3_vazas(self) -> Optional[str]:
        """
        Joga as 3 vazas da mão de ferro.

        Os jogadores só mandam o índice (0, 1, 2) da carta escolhida.
        O servidor resolve silenciosamente (sem revelar as cartas).

        Retorna:
            - slot vencedor (SLOT1/SLOT2)
            - None se houve empate total (força nova mão de ferro)
        """
        comeca = self.comeca_mao

        for numero in range(1, 4):
            outro = SLOT2 if comeca == SLOT1 else SLOT1
            cartas = {SLOT1: None, SLOT2: None}

            for slot in [comeca, outro]:
                if self.terminou:
                    return None

                msg = self._esperar_mensagem(
                    slot,
                    tipos_validos={p.T_ESCOLHA_FERRO},
                    timeout=TIMEOUT_ESCOLHA_FERRO,
                )
                if self.terminou:
                    return None
                if msg is None:
                    self.registrar_wo(slot)
                    return None

                indice = msg.get("indice")
                if indice not in (0, 1, 2):
                    self.sala.enviar_para(slot, {
                        "tipo": p.T_ERRO,
                        "codigo": "indice_invalido",
                        "msg": "Escolha 0, 1 ou 2.",
                    })
                    continue

                carta_str = self.jogadores[slot].mao[indice]
                cartas[slot] = Carta.from_str(carta_str)

            if cartas[SLOT1] is None or cartas[SLOT2] is None:
                return None

            r = comparar(cartas[SLOT1], cartas[SLOT2])

            if r > 0:
                self.vitorias_vaza[SLOT1] += 1
                if self.quem_ganhou_vaza_1 is None:
                    self.quem_ganhou_vaza_1 = SLOT1
                self.sala.broadcast({
                    "tipo": p.T_RESULTADO_VAZA,
                    "vencedor": SLOT1,
                    "vaza": numero,
                })
            elif r < 0:
                self.vitorias_vaza[SLOT2] += 1
                if self.quem_ganhou_vaza_1 is None:
                    self.quem_ganhou_vaza_1 = SLOT2
                self.sala.broadcast({
                    "tipo": p.T_RESULTADO_VAZA,
                    "vencedor": SLOT2,
                    "vaza": numero,
                })
            else:
                self.sala.broadcast({
                    "tipo": p.T_RESULTADO_VAZA,
                    "vencedor": None,
                    "vaza": numero,
                })

            # Empate total na 3ª vaza → nova mão de ferro
            if (self.vitorias_vaza[SLOT1] == self.vitorias_vaza[SLOT2]
                    and numero == 3):
                return None

            if self.vitorias_vaza[SLOT1] == 2:
                return SLOT1
            if self.vitorias_vaza[SLOT2] == 2:
                return SLOT2

            # Alterna quem começa na próxima vaza
            comeca = SLOT2 if comeca == SLOT1 else SLOT1

        # Acabaram as 3 vazas
        if self.vitorias_vaza[SLOT1] > self.vitorias_vaza[SLOT2]:
            return SLOT1
        if self.vitorias_vaza[SLOT2] > self.vitorias_vaza[SLOT1]:
            return SLOT2
        return None

    # ========================================================
    # ESPERA DE MENSAGEM (núcleo da sincronização)
    # ========================================================

    def _esperar_mensagem(
        self,
        slot: str,
        tipos_validos: set,
        timeout: float,
    ) -> Optional[dict]:
        """
        Espera uma mensagem de um tipo válido vinda do jogador 'slot'.

        Como funciona a sincronização:
            - Cada jogador tem uma fila (jogador.fila).
            - A thread leitora da Sala insere mensagens nessa fila e
              chama `sala.condicao.notify_all()`.
            - Aqui, tentamos tirar da fila sem bloquear (`get_nowait`).
            - Se estiver vazia, dormimos em `condicao.wait()` até
              alguém notificar (ou até dar timeout curto).

        Mensagens com tipo inválido geram erro pro cliente e o
        loop continua esperando.

        Retorna a mensagem (dict) ou None em caso de timeout.
        """
        if timeout <= 0:
            return None

        deadline = time.time() + timeout
        fila = self.jogadores[slot].fila

        while time.time() < deadline and not self.terminou:
            try:
                msg = fila.get_nowait()
            except queue.Empty:
                # Fila vazia: dorme até ser notificado
                with self.sala.condicao:
                    self.sala.condicao.wait(timeout=0.5)
                continue

            tipo = msg.get("tipo")
            if tipo in tipos_validos:
                return msg

            self.sala.enviar_para(slot, {
                "tipo": p.T_ERRO,
                "codigo": "acao_invalida",
                "msg": f"Ação '{tipo}' não permitida agora.",
            })

        return None

    # ========================================================
    # WO / FIM
    # ========================================================

    def registrar_wo(self, slot: str) -> None:
        """
        Registra WO de um jogador (desconexão ou timeout).

        Efeito: adversário vence a partida independente de pontos.
        O `notify_all` acorda qualquer thread que estiver esperando
        na condição (por exemplo, `_esperar_mensagem`).
        """
        if self.terminou:
            return
        outro = SLOT2 if slot == SLOT1 else SLOT1
        self._log(f"WO registrado: {slot} caiu. Vencedor: {outro}")
        self.vencedor_wo = outro
        self.terminou = True
        with self.sala.condicao:
            self.sala.condicao.notify_all()

    def _fim_de_partida(self, vencedor: Optional[str]) -> None:
        """Encerra a partida e avisa os jogadores."""
        if vencedor is None:
            # Fallback: quem tem mais pontos
            if self.placar[SLOT1] >= self.placar[SLOT2]:
                vencedor = SLOT1
            else:
                vencedor = SLOT2

        self._log(
            f"FIM DA PARTIDA: {vencedor} venceu! Placar: {self.placar}"
        )
        self.sala.broadcast({
            "tipo": p.T_FIM_PARTIDA,
            "vencedor": vencedor,
            "pontos": dict(self.placar),
        })
        self.terminou = True
        self.sala.finalizar_partida(vencedor)

    # ========================================================
    # UTIL
    # ========================================================

    def _enviar_mao_inicial(self) -> None:
        """Envia a mão inicial pra cada jogador com o placar atual."""
        for slot, jog in self.jogadores.items():
            self.sala.enviar_para(slot, {
                "tipo": p.T_MAO_INICIAL,
                "cartas": list(jog.mao),
                "pontos": dict(self.placar),
                "comeca": self.comeca_mao,
            })

    def _log(self, texto: str) -> None:
        if DEBUG:
            print(f"[PARTIDA {self.sala.id}] {texto}")