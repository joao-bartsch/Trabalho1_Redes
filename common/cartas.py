import random
from typing import Iterable, Optional


# ============================================================
# Constantes
# ============================================================

VALORES = ["4", "5", "6", "7", "Q", "J", "K", "A", "2", "3"]
NAIPES = ["paus", "copas", "espadas", "ouros"]

# Manilhas fixas: chave = (valor, naipe), valor = força absoluta
# Forças acima de qualquer não-manilha (que vai de 0 a 9).
MANILHAS = {
    ("4", "paus"): 14,   # mais forte
    ("7", "copas"): 13,
    ("A", "espadas"): 12,
    ("7", "ouros"): 11,  # mais fraca entre as manilhas
}

# Força das não-manilhas (0 a 9)
FORCA_VALOR = {
    "3": 9,
    "2": 8,
    "A": 7,
    "K": 6,
    "J": 5,
    "Q": 4,
    "7": 3,
    "6": 2,
    "5": 1,
    "4": 0,
}

# Força do naipe pra desempate (quando valores iguais)
FORCA_NAIPE = {
    "paus": 3,
    "copas": 2,
    "espadas": 1,
    "ouros": 0,
}


# ============================================================
# Classe Carta
# ============================================================

class Carta:
    """Uma carta do baralho (valor + naipe)."""

    __slots__ = ("valor", "naipe")

    def __init__(self, valor: str, naipe: str):
        if valor not in VALORES:
            raise ValueError(f"Valor inválido: {valor!r}")
        if naipe not in NAIPES:
            raise ValueError(f"Naipe inválido: {naipe!r}")

        self.valor = valor
        self.naipe = naipe

    # --------------------------------------------------------
    # Conversão / representação
    # --------------------------------------------------------

    def __str__(self) -> str:
        """Formato do protocolo: 'valor-naipe'."""
        return f"{self.valor}-{self.naipe}"

    def __repr__(self) -> str:
        return f"Carta({self})"

    def __eq__(self, outro) -> bool:
        if not isinstance(outro, Carta):
            return NotImplemented
        return self.valor == outro.valor and self.naipe == outro.naipe

    def __hash__(self) -> int:
        return hash((self.valor, self.naipe))

    # --------------------------------------------------------
    # Construtores alternativos
    # --------------------------------------------------------

    @classmethod
    def from_str(cls, texto: str) -> "Carta":
        """
        Cria uma Carta a partir de uma string 'valor-naipe'.

        Levanta ValueError se o formato for inválido.
        """
        partes = texto.strip().split("-")
        if len(partes) != 2:
            raise ValueError(f"Formato de carta inválido: {texto!r}")
        valor, naipe = partes
        return cls(valor, naipe)

    # --------------------------------------------------------
    # Força / comparação
    # --------------------------------------------------------

    def eh_manilha(self) -> bool:
        """Retorna True se essa carta é uma das 4 manilhas fixas."""
        return (self.valor, self.naipe) in MANILHAS

    def forca(self) -> int:
        """
        Força absoluta da carta (para comparação).

        - Manilhas: 11 a 14 (sempre acima das não-manilhas).
        - Não-manilhas: 0 a 9.

        Quando duas não-manilhas têm a mesma força (mesmo valor),
        o desempate é por naipe — use comparar() para isso.
        """
        chave = (self.valor, self.naipe)
        if chave in MANILHAS:
            return MANILHAS[chave]
        return FORCA_VALOR[self.valor]

    def naipe_forca(self) -> int:
        """Força do naipe (paus > copas > espadas > ouros)."""
        return FORCA_NAIPE[self.naipe]

    def to_dict(self) -> dict:
        """Serializa pra JSON (útil no protocolo)."""
        return {"valor": self.valor, "naipe": self.naipe}


# ============================================================
# Funções utilitárias
# ============================================================

def comparar(a: Carta, b: Carta) -> int:
    """
    Compara duas cartas por força.

    Returns:
         1 se a > b
        -1 se a < b
         0 se empatarem em força E naipe (mesma carta) — não deveria
           acontecer no jogo real, mas fica como segurança.
    """
    fa, fb = a.forca(), b.forca()

    if fa > fb:
        return 1
    if fa < fb:
        return -1

    # Mesma força: desempata por naipe
    na, nb = a.naipe_forca(), b.naipe_forca()
    if na > nb:
        return 1
    if na < nb:
        return -1

    # Mesma força E mesmo naipe → mesma carta (empate exato)
    return 0


def maior_carta(cartas: Iterable[Carta]) -> Optional[Carta]:
    """
    Retorna a maior carta de uma coleção (usando comparar).

    Retorna None se a coleção estiver vazia.
    """
    cartas = list(cartas)
    if not cartas:
        return None

    maior = cartas[0]
    for c in cartas[1:]:
        if comparar(c, maior) > 0:
            maior = c
    return maior


# ============================================================
# Classe Baralho
# ============================================================

class Baralho:
    """Baralho limpo de 40 cartas (sem 8, 9, 10, sem coringa)."""

    def __init__(self):
        self.cartas: list[Carta] = [
            Carta(valor, naipe)
            for valor in VALORES
            for naipe in NAIPES
        ]

    def embaralhar(self) -> None:
        """Embaralha as cartas in-place."""
        random.shuffle(self.cartas)

    def distribuir(self, n: int) -> list[Carta]:
        """
        Remove e retorna as n primeiras cartas do topo.

        Levanta ValueError se não houver cartas suficientes.
        """
        if n > len(self.cartas):
            raise ValueError(
                f"Baralho tem {len(self.cartas)} cartas, "
                f"mas foram pedidas {n}."
            )
        cartas = self.cartas[:n]
        self.cartas = self.cartas[n:]
        return cartas

    def __len__(self) -> int:
        return len(self.cartas)

    def __repr__(self) -> str:
        return f"Baralho({len(self.cartas)} cartas)"