from server.sala import Sala, Estado

s = Sala(1)
print("Estado inicial:", s.estado)

# Simula dois jogadores fake (só pra testar a máquina de estados)
class FakeJogador:
    def __init__(self, nome):
        self.conn = object()
        self.addr = ("127.0.0.1", 0)
        self.slot = None
        self.nome = nome
        self.mao = []
        self.pontos = 0
        self.pronto = False
        self._vivo = True
    @property
    def vivo(self): return True
    def enviar(self, m): print(f"  [{self.nome}] recebeu:", m); return True
    def receber(self): return []
    def fechar(self): pass
    def resetar_para_nova_partida(self): pass

s.adicionar_jogador(FakeJogador("Ana"))
print("Depois de Ana:", s.estado)
s.adicionar_jogador(FakeJogador("Bia"))
print("Depois de Bia:", s.estado)

s.marcar_pronto("jogador1")
s.marcar_pronto("jogador2")