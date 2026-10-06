import socket
import threading
import time
from typing import Optional

from common import protocolo as p
from common.excecoes import ConexaoFechadaError


class Cliente:
    def __init__(self, host: str, port: int, nome: str):
        self.host = host
        self.port = port
        self.nome = nome

        self.conn: Optional[socket.socket] = None
        self._buffer = b""
        self._vivo = True

        # Estado local (só pra debug/exibição)
        self.meu_slot: Optional[str] = None
        self.minha_mao: list[str] = []
        self.ultimo_estado = ""

    # --------------------------------------------------------
    # Conexão
    # --------------------------------------------------------

    def conectar(self) -> None:
        self.conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.conn.connect((self.host, self.port))
        print(f"[CLIENTE] conectado em {self.host}:{self.port}")

        # Manda 'entrar'
        self.enviar({"tipo": p.T_ENTRAR, "nome": self.nome})

    def enviar(self, mensagem: dict) -> None:
        if self.conn is None:
            return
        try:
            p.enviar(self.conn, mensagem)
        except (OSError, ConexaoFechadaError):
            self._vivo = False

    # --------------------------------------------------------
    # Loop de recebimento
    # --------------------------------------------------------

    def loop_recebimento(self) -> None:
        while self._vivo:
            try:
                msgs, self._buffer = p.receber(self.conn, self._buffer)
            except ConexaoFechadaError:
                print("\n[CLIENTE] conexão encerrada pelo servidor.")
                self._vivo = False
                return

            for msg in msgs:
                self._tratar(msg)

    def _tratar(self, msg: dict) -> None:
        tipo = msg.get("tipo")

        # --------------------------------------------------------
        # Conexão / Lobby
        # --------------------------------------------------------
        if tipo == p.T_BEM_VINDO:
            self.meu_slot = msg.get("jogador")
            print(f"\n[CLIENTE] bem-vindo! Sala {msg.get('sala')}, "
                  f"você é {self.meu_slot}.")

        elif tipo == p.T_REGRAS:
            print("\n=== REGRAS ===")
            print(msg.get("texto"))
            print("==============\n")

        elif tipo == p.T_LOBBY:
            print(f"\n[LOBBY] estado={msg.get('estado')}")
            for j in msg.get("jogadores", []):
                marca = "✓" if j.get("pronto") else " "
                print(f"  [{marca}] {j.get('slot')}: {j.get('nome')}")

        # --------------------------------------------------------
        # Início de partida
        # --------------------------------------------------------
        elif tipo == p.T_MAO_INICIAL:
            self.minha_mao = msg.get("cartas", [])
            print(f"\n[MAO INICIAL] suas cartas: {self.minha_mao}")
            print(f"  Placar: {msg.get('pontos')}")
            print(f"  Começa: {msg.get('comeca')}")

        elif tipo == p.T_SUA_VEZ:
            print(f"\n>>> SUA VEZ <<<  (mão: {self.minha_mao})")

        elif tipo == p.T_CARTA_JOGADA:
            print(f"  [{msg.get('jogador')}] jogou: {msg.get('carta')}")
            # Remove da mão local se foi eu
            if msg.get("jogador") == self.meu_slot:
                c = msg.get("carta")
                if c in self.minha_mao:
                    self.minha_mao.remove(c)

        elif tipo == p.T_RESULTADO_VAZA:
            v = msg.get("vencedor")
            if v is None:
                print(f"  Vaza {msg.get('vaza')}: EMPATE")
            else:
                print(f"  Vaza {msg.get('vaza')}: venceu {v}")

        elif tipo == p.T_FIM_MAO:
            print(f"\n[FIM DE MÃO] vencedor: {msg.get('vencedor')}")
            print(f"  Placar: {msg.get('pontos')}")

        # --------------------------------------------------------
        # Truco
        # --------------------------------------------------------
        elif tipo == p.T_TRUCO_PEDIDO:
            print(f"\n[TRUCO] {msg.get('de')} pediu! Valor: {msg.get('valor')}")
            print("  Responda: aceitar | correr | aumentar")

        elif tipo == p.T_TRUCO_ACEITO:
            print(f"[TRUCO] aceito. Valor da mão: {msg.get('valor')}")

        elif tipo == p.T_TRUCO_CORRIDO:
            print(f"[TRUCO] {msg.get('quem_correu')} correu. "
                  f"{msg.get('vencedor')} ganhou {msg.get('pontos')} pontos.")

        elif tipo == p.T_TRUCO_AUMENTADO:
            print(f"[TRUCO] {msg.get('de')} aumentou! Valor: {msg.get('valor')}")

        # --------------------------------------------------------
        # Mostrar a maior
        # --------------------------------------------------------
        elif tipo == p.T_MOSTRAR_MAIOR:
            print(f"\n[MOSTRAR A MAIOR] primeiro a revelar: {msg.get('primeiro')}")

        elif tipo == p.T_MAIOR_REVELADA:
            print(f"  [{msg.get('jogador')}] revelou: {msg.get('carta')}")

        elif tipo == p.T_FIM_MOSTRAR_MAIOR:
            print(f"[MOSTRAR A MAIOR] vencedor: {msg.get('vencedor')} "
                  f"({msg.get('pontos')} pontos)")

        # --------------------------------------------------------
        # Mão de 11 / ferro
        # --------------------------------------------------------
        elif tipo == p.T_MAO_DE_11:
            if msg.get("cartas"):
                print(f"\n[MÃO DE 11] suas cartas: {msg.get('cartas')}")
                print("  Decida: jogar | correr")
            else:
                print(f"[MÃO DE 11] aguardando decisão de {msg.get('aguardando')}")

        elif tipo == p.T_MAO_DE_FERRO:
            print(f"\n[MÃO DE FERRO] sem ver as cartas!")
            print("  Escolha: 0 | 1 | 2")

        elif tipo == p.T_RESULTADO_FERRO:
            print(f"[MÃO DE FERRO] vencedor: {msg.get('vencedor')} "
                  f"({msg.get('pontos')} ponto)")

        # --------------------------------------------------------
        # Fim / revanche
        # --------------------------------------------------------
        elif tipo == p.T_FIM_PARTIDA:
            print(f"\n{'='*40}")
            print(f"  FIM DE PARTIDA! Vencedor: {msg.get('vencedor')}")
            print(f"  Placar final: {msg.get('pontos')}")
            print(f"{'='*40}")
            print("  Envie: revanche aceitar | revanche recusar")

        elif tipo == p.T_REVANCHE_INICIO:
            print("\n[REVANCHE] nova partida iniciando...")

        elif tipo == p.T_DESCONECTANDO:
            print(f"\n[SERVIDOR] {msg.get('motivo')}")
            self._vivo = False

        # --------------------------------------------------------
        # Erros
        # --------------------------------------------------------
        elif tipo == p.T_ERRO:
            print(f"\n[ERRO] {msg.get('codigo')}: {msg.get('msg')}")

        else:
            print(f"\n[?] mensagem desconhecida: {msg}")

    # --------------------------------------------------------
    # Loop de input do usuário
    # --------------------------------------------------------

    def loop_input(self) -> None:
        """
        Lê comandos do usuário e traduz em mensagens pro servidor.

        Comandos:
            regras
            pronto
            jogar <carta>          (ex: jogar 4-paus)
            truco
            aceitar | correr | aumentar
            revelar <carta>        (mostrar a maior)
            jogar11 | correr11     (mão de 11)
            0 | 1 | 2              (mão de ferro)
            revanche aceitar | revanche recusar
            sair
        """
        while self._vivo:
            try:
                linha = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                break

            if not linha:
                continue

            partes = linha.split(maxsplit=1)
            cmd = partes[0].lower()
            arg = partes[1] if len(partes) > 1 else ""

            if cmd == "sair":
                self._vivo = False
                break

            elif cmd == "regras":
                self.enviar({"tipo": p.T_REGRAS})

            elif cmd == "pronto":
                self.enviar({"tipo": p.T_PRONTO})

            elif cmd == "jogar":
                self.enviar({"tipo": p.T_JOGAR, "carta": arg})

            elif cmd == "truco":
                self.enviar({"tipo": p.T_TRUCO})

            elif cmd in ("aceitar", "correr", "aumentar"):
                self.enviar({"tipo": p.T_RESPOSTA_TRUCO, "acao": cmd})

            elif cmd == "revelar":
                self.enviar({"tipo": p.T_REVELAR_MAIOR, "carta": arg})

            elif cmd == "jogar11":
                self.enviar({"tipo": p.T_DECISAO_MAO_11, "acao": "jogar"})

            elif cmd == "correr11":
                self.enviar({"tipo": p.T_DECISAO_MAO_11, "acao": "correr"})

            elif cmd in ("0", "1", "2"):
                self.enviar({"tipo": p.T_ESCOLHA_FERRO, "int": int(cmd)})

            elif cmd == "revanche":
                self.enviar({"tipo": p.T_REVANCHE, "acao": arg})

            else:
                print(f"[?] comando desconhecido: {linha!r}")
                print("    tente: regras | pronto | jogar <carta> | truco | "
                      "aceitar/correr/aumentar | revelar <carta> | "
                      "jogar11/correr11 | 0/1/2 | revanche aceitar/recusar | sair")