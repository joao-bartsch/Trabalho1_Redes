from common.cartas import Carta, Baralho, comparar, maior_carta


def c(s):
    return Carta.from_str(s)


# --- Manilhas: 4-paus > 7-copas > A-espadas > 7-ouros ---
print("Manilhas:")
print("  4-paus vs 7-copas:", comparar(c("4-paus"), c("7-copas")))   # 1
print("  7-copas vs A-espadas:", comparar(c("7-copas"), c("A-espadas")))  # 1
print("  A-espadas vs 7-ouros:", comparar(c("A-espadas"), c("7-ouros")))  # 1
print("  7-ouros vs 3-paus:", comparar(c("7-ouros"), c("3-paus")))     # 1 (manilha > 3)

# --- Não-manilhas: 3 > 2 > A > K > J > Q > 7 > 6 > 5 > 4 ---
print("\nNão-manilhas:")
print("  3-ouros vs 2-paus:", comparar(c("3-ouros"), c("2-paus")))    # 1
print("  2-copas vs A-espadas:", comparar(c("2-copas"), c("A-espadas")))  # 1
print("  A-paus vs K-paus:", comparar(c("A-paus"), c("K-paus")))      # 1
print("  J-ouros vs Q-paus:", comparar(c("J-ouros"), c("Q-paus")))    # 1
print("  7-paus vs 6-copas:", comparar(c("7-paus"), c("6-copas")))    # 1

# --- Desempate por naipe ---
print("\nDesempate por naipe:")
print("  3-paus vs 3-copas:", comparar(c("3-paus"), c("3-copas")))    # 1 (paus > copas)
print("  3-copas vs 3-espadas:", comparar(c("3-copas"), c("3-espadas")))  # 1
print("  3-espadas vs 3-ouros:", comparar(c("3-espadas"), c("3-ouros")))  # 1

# --- Caso especial: 7-paus NÃO é manilha, então perde pro 3 ---
print("\n7-paus (não-manilha) vs 3-ouros:")
print("  ", comparar(c("7-paus"), c("3-ouros")))   # -1 (3 > 7)

# --- maior_carta ---
print("\nMaior carta de uma lista:")
mao = [c("3-paus"), c("4-paus"), c("2-copas")]
print("  ", maior_carta(mao))   # 4-paus

# --- Baralho ---
print("\nBaralho:")
b = Baralho()
print("  Tamanho inicial:", len(b))   # 40
b.embaralhar()
mao = b.distribuir(3)
print("  Mão distribuída:", mao)
print("  Tamanho restante:", len(b))   # 37

# --- Carta.from_str com erro ---
try:
    Carta.from_str("8-paus")
except ValueError as e:
    print("\nErro esperado:", e)