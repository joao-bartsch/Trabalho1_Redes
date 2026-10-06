

TEXTO_REGRAS = """
============================================================
                    TRUCO ONLINE
============================================================

CARTAS
------
Baralho limpo de 40 cartas (sem 8, 9, 10 e sem coringa).

MANILHAS FIXAS (da mais forte pra mais fraca):
    4 de paus  >  7 de copas  >  A de espadas  >  7 de ouros

DEMAIS CARTAS (da mais forte pra mais fraca):
    3 > 2 > A > K > J > Q > 7 > 6 > 5 > 4

Desempate por naipe (quando valores iguais):
    paus > copas > espadas > ouros

MÃO
---
Melhor de 3 vazas. Quem ganhar 2 leva a mão.
Se a 1ª vaza (queda, rodada, etc) empatar → vai direto pro "mostrar a maior".
Se a 3ª vaza empatar → vence quem ganhou a 1ª vaza.
Se todas empatarem → ninguém pontua, nova mão.

MOSTRAR A MAIOR
---------------
Quando a 1ª vaza empata, os dois revelam a maior carta da mão.
Quem começou a vaza revela primeiro. O segundo pode trucar
mesmo já sabendo a carta do adversário.
Sem truco: quem tiver a maior ganha 1 ponto.
Com truco aceito: quem tiver a maior ganha 3 pontos.

TRUCO
-----
Valores: truco (3) → retruco (6) → vale-nove (9) → vale-doze (12).
Só quem está na vez pode pedir.
Quem recebe pode: aceitar, correr ou aumentar.
Correr = adversário ganha o valor anterior.

PONTUAÇÃO
---------
Mão normal .......... 1 ponto
Truco aceito ........ 3 pontos
Retruco aceito ...... 6 pontos
Vale-nove aceito .... 9 pontos
Vale-doze aceito .... 12 pontos

A partida vai até 12 pontos (quem chegar/passar primeiro).

MÃO DE 11
---------
Quando um jogador tem exatamente 11 pontos, ele vê as cartas
e decide jogar ou correr.
Correr: adversário ganha 1 ponto.
Jogar e perder: adversário ganha 3 pontos.
Jogar e ganhar: ele ganha 1 ponto e vence.
Não pode pedir truco.

MÃO DE FERRO
------------
Quando ambos têm 11 pontos, jogam sem ver as cartas.
Escolhem apenas "carta 1", "carta 2" ou "carta 3".
Vale 1 ponto. Se empatar, nova mão de ferro.

WO
--
Se um jogador cair durante a partida, o outro vence por WO.
Se cair no lobby, a sala volta pra "aguardando jogadores".
============================================================

COMANDOS 
--
'regras' → mostra as regras do jogo
'pronto' → pronto para jogar (ou iniciar a partida)
'jogar + nome da carta' → jogar carta da mão (ex: jogar 4-paus)
'truco' → pedir truco (ou retruco, vale-nove, vale-doze)
    dentro do truco:
    'correr' → desistir da mão (perde o valor atual)
    'aceitar' → aceitar o truco (ou retruco, vale-nove, vale-doze)
    'aumentar' → aumentar o truco (ou retruco, vale-nove, vale-doze)
'revelar + nome da maior carta' → revelar a maior carta da mão (ex: revelar 4-paus)
'jogar11' → jogar a mão de 11 pontos
'correr11' → desistir da mão de 11 pontos
"""