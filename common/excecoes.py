"""
Exceções customizadas do projeto Truco Mineiro.

Todas as exceções de domínio herdam de TrucoError, facilitando
captura genérica no servidor e no cliente.
"""


class TrucoError(Exception):
    """Exceção base do projeto. Todas as outras herdam dela."""
    pass


# ============================================================
# Exceções de Protocolo / Rede
# ============================================================

class ProtocoloError(TrucoError):
    """Erro genérico de protocolo (mensagem malformada, etc.)."""
    pass


class MensagemInvalidaError(ProtocoloError):
    """Mensagem recebida não é um JSON válido ou não tem 'tipo'."""
    pass


class MensagemGrandeError(ProtocoloError):
    """Mensagem excede o tamanho máximo permitido."""
    pass


class ConexaoFechadaError(ProtocoloError):
    """A conexão foi fechada pelo outro lado (recv retornou vazio)."""
    pass


# ============================================================
# Exceções de Jogo
# ============================================================

class JogoError(TrucoError):
    """Erro genérico de lógica de jogo."""
    pass


class JogadaInvalidaError(JogoError):
    """Jogada não permitida (carta não está na mão, fora da vez, etc.)."""
    pass


class JogadorNaoEstaNaVezError(JogoError):
    """O jogador tentou agir fora da sua vez."""
    pass


class CartaNaoEstaNaMaoError(JogoError):
    """A carta jogada não está na mão do jogador."""
    pass


class TrucoInvalidoError(JogoError):
    """Pedido de truco inválido (fora da vez, valor errado, etc.)."""
    pass


class RespostaTrucoInvalidaError(JogoError):
    """Resposta a truco inválida."""
    pass


class MostrarMaiorInvalidoError(JogoError):
    """Carta revelada no 'mostrar a maior' não é a maior da mão."""
    pass


class MaoDeFerroInvalidaError(JogoError):
    """Escolha inválida na mão de ferro."""
    pass


class MaoDe11InvalidaError(JogoError):
    """Decisão inválida na mão de 11."""
    pass


class PartidaFinalizadaError(JogoError):
    """Tentou agir em uma partida já finalizada."""
    pass


# ============================================================
# Exceções de Sala / Servidor
# ============================================================

class SalaError(TrucoError):
    """Erro genérico de sala."""
    pass


class SalaCheiaError(SalaError):
    """Tentou entrar em uma sala que já tem 2 jogadores."""
    pass


class SalaNaoEncontradaError(SalaError):
    """Sala não existe."""
    pass


class NenhumaSalaDisponivelError(SalaError):
    """Todas as salas estão cheias / em jogo."""
    pass


class JogadorJaNaSalaError(SalaError):
    """Jogador tentou entrar em uma sala onde já está."""
    pass


class EstadoSalaInvalidoError(SalaError):
    """Ação não permitida no estado atual da sala."""
    pass