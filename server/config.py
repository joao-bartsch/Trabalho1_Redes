
# ============================================================
# Rede
# ============================================================

HOST = "0.0.0.0"          # escuta em todas as interfaces
PORT = 5000               # porta do servidor
BACKLOG = 10              # fila de conexões pendentes do listen()

# ============================================================
# Salas
# ============================================================

NUM_SALAS = 4             # quantas salas fixas o servidor cria no boot
JOGADORES_POR_SALA = 2

# ============================================================
# Partida
# ============================================================

PONTOS_PARTIDA = 12       # quem chegar/passar primeiro vence

# Valores de truco (índice = nível atual, valor = pontos)
VALORES_TRUCO = {
    0: 1,    # mão normal
    1: 3,    # truco
    2: 6,    # retruco
    3: 9,    # vale-nove
    4: 12,   # vale-doze
}

NOMES_TRUCO = {
    1: "truco",
    2: "retruco",
    3: "vale-nove",
    4: "vale-doze",
}

# ============================================================
# Timeouts (em segundos)
# ============================================================

TIMEOUT_LOBBY = 120       # jogador tem 2 min pra dar pronto, senão é removido
TIMEOUT_JOGADA = 60       # jogador tem 1 min pra jogar, senão perde a vez
TIMEOUT_TRUCO = 30        # tempo pra responder a um truco
TIMEOUT_REVELAR_MAIOR = 30
TIMEOUT_DECISAO_MAO_11 = 30
TIMEOUT_ESCOLHA_FERRO = 30
TIMEOUT_REVANCHE = 60

# ============================================================
# Debug / Logs
# ============================================================

DEBUG = True              # se True, imprime logs detalhados no console
LOG_JOGADAS = True        # registra cada jogada no console