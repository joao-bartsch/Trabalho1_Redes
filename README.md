# Truco Online — Trabalho 1 de Redes de Computadores

Implementação do jogo **Truco** em Python, utilizando
**sockets TCP** e arquitetura **cliente-servidor** com suporte a
múltiplas salas concorrentes, comunicação baseada em **JSON sobre TCP**
e sincronização de turnos entre jogadores.

---

## Membros do Grupo

João Vitor Bartsch Morasi - 15464090
Gustavo Silverio Arruda - 15458162
Mateus Bellon Liparizi - 15478811
Carlos Eduardo da Silva Zecchi - 13817245

---

## Ambiente de Desenvolvimento

| Item | Versão / Detalhe |
|---|---|
| **Sistema Operacional** | Fedora Linux 41 (Workstation Edition) |
| **Linguagem** | Python 3.13.9 |
| **Compilador/Interpretador** | CPython 3.13 (interpretador oficial) |
| **Bibliotecas externas** | Nenhuma — apenas biblioteca padrão do Python (`socket`, `threading`, `queue`, `json`, `random`, `time`) |
| **IDE / Editor** | Visual Studio Code |
| **Controle de versão** | Git + GitHub |
---

## Como Executar

### Pré-requisitos

- Python 3.11+ instalado
- Dois ou mais terminais (um para o servidor, dois para os clientes)

### Passo 1: Subir o servidor

Em um terminal, a partir da raiz do projeto:

```bash
python -m server.main
```

Saída esperada:

```
[SERVIDOR] escutando em 0.0.0.0:5000
[SERVIDOR] 4 salas criadas.
```

### Passo 2: Conectar dois clientes

Em **dois terminais separados**, a partir da raiz do projeto:

```bash
# Terminal 2
python -m client.main Ana

# Terminal 3
python -m client.main Bia
```

Cada cliente recebe um slot (`jogador1` ou `jogador2`) e uma sala.

### Passo 3: Jogar

Nos dois terminais de cliente, digite:

```
> pronto
```

Quando **ambos** enviarem `pronto`, a partida começa automaticamente
e cada jogador recebe suas 3 cartas.
---


## Protocolo de Comunicação

### Formato

- **Transporte**: TCP
- **Serialização**: JSON
- **Framing**: uma mensagem JSON por linha, terminada em `\n`
- **Encoding**: UTF-8
- **Tamanho máximo por mensagem**: 64 KB

### Exemplo de mensagem

```json
{"tipo": "jogar", "carta": "7-paus"}\n
```

### Categorias de mensagens

| Categoria | Exemplos |
|---|---|
| Conexão / Lobby | `entrar`, `bem_vindo`, `regras`, `pronto`, `lobby` |
| Início de partida | `mao_inicial`, `sua_vez` |
| Jogada | `jogar`, `carta_jogada`, `resultado_vaza`, `fim_mao` |
| Truco | `truco`, `truco_pedido`, `resposta_truco`, `truco_aceito`, `truco_corrido`, `truco_aumentado` |
| Mostrar a maior | `mostrar_maior`, `revelar_maior`, `maior_revelada`, `fim_mostrar_maior` |
| Mão de 11 / Ferro | `mao_de_11`, `decisao_mao_11`, `mao_de_ferro`, `escolha_ferro`, `resultado_ferro` |
| Revanche / Fim | `fim_partida`, `revanche`, `revanche_inicio`, `desconectando` |
| Erros | `erro` (com `codigo` e `msg`) |

---

## Verificações de Falha na Conexão

O sistema foi projetado para **detectar e tratar** falhas de conexão em
vários níveis. Abaixo estão as principais verificações implementadas.

### 1. Detecção de queda de conexão (cliente → servidor)

A thread leitora de cada jogador (`Sala._loop_leitura`) chama
`Jogador.receber()`. Se o `recv()` retorna vazio (conexão fechada pelo
outro lado), a exceção `ConexaoFechadaError` é lançada em
`common/protocolo.py`, a flag `Jogador._vivo` vira `False` e a sala
chama automaticamente `remover_jogador(slot)`.

**Consequência:**
- Se o jogador cai **no lobby** → a sala volta pra `AGUARDANDO_JOGADORES`.
- Se o jogador cai **durante a partida** → o adversário ganha a partida
  por **WO (walkover)**, sem revanche, e a sala é liberada.

### 2. Timeout de jogada

Em `server/config.py` há `TIMEOUT_JOGADA = 60` (segundos). Se um
jogador não enviar `jogar` ou `truco` dentro desse tempo,
`Partida._aguardar_jogada` retorna `None`, e o servidor registra
**WO automático** pro adversário.

### 3. Validação de mensagens recebidas

Antes de processar qualquer mensagem, o servidor valida:

- **JSON válido** (`json.loads`) → se não for, `MensagemInvalidaError`.
- **Tipo obrigatório** (`"tipo"` deve existir) → senão, erro.
- **Tamanho máximo** (64 KB) → se exceder, `MensagemGrandeError`.
- **Buffer acumulado** (limite 256 KB) → protege contra clientes que
  enviam dados sem delimitador.

### 4. Validação de ações no jogo

Todas as ações são **validadas no servidor** (o cliente nunca decide
nada crítico):

- **Jogar carta** → carta precisa estar na mão do jogador.
- **Truco** → só na vez, e só fora da mão de 11.
- **Revelar** → a carta revelada precisa ser a **maior** da mão.
- **Escolha de ferro** → índice precisa ser 0, 1 ou 2.
- **Ação fora da vez** → `JogadorNaoEstaNaVezError`.

### 5. Fechamento correto de socket

O método `Jogador.fechar()` faz `shutdown(SHUT_RDWR)` seguido de
`close()`, garantindo que **tanto leitura quanto escrita** sejam
encerradas e que a thread leitora seja desbloqueada.

### 6. Proteção contra travamento do servidor

- **Locks por sala** (`RLock`) evitam condições de corrida no estado
  compartilhado entre threads leitoras e a thread da partida.
- **`Condition` única por sala** sincroniza turnos de forma eficiente
  (threads dormem até serem notificadas, em vez de fazer `busy wait`).
- **Socket timeout** de 0.5 s nas esperas internas permite que a
  thread da partida **verifique periodicamente** se precisa abortar
  (por exemplo, após um WO).

---

## Transmissão das Informações

### Fluxo de dados

1. **Cliente → servidor**: envia comandos (JSON + `\n`).
2. **Servidor → cliente**: envia eventos e o estado atualizado.
3. **Broadcast**: quando algo afeta os dois jogadores (ex:
   `carta_jogada`), o servidor envia a **mesma mensagem** para ambos.

### Ordem e consistência

- Toda mensagem é **atômica** (uma linha JSON).
- O servidor **nunca** envia estado parcial — ou o cliente recebe
  a mensagem completa, ou nada.
- Múltiplas mensagens podem vir em um único `recv()`: o parser
  separa por `\n` e processa uma por vez.

### Sincronização de turnos

A sincronização é feita pela **fila por jogador** + **`Condition` da
sala**:

1. A thread leitora insere a mensagem na fila e chama `notify_all()`.
2. A thread da partida, que estava dormindo em `condicao.wait()`,
   acorda, consome a mensagem e continua o processamento.

Isso garante que **não há `busy wait`** e que o servidor aproveita a
CPU de forma eficiente.

### Verificação de integridade

- **Sem corrupção**: o `sendall()` garante que **todos** os bytes
  sejam enviados (mesmo em conexões fragmentadas).
- **Sem duplicação**: cada mensagem tem um `tipo` e o servidor só
  processa **uma vez** (não há retransmissão a nível de aplicação,
  pois o TCP garante isso).
- **Sem reordenação**: TCP entrega os bytes **na ordem** em que
  foram enviados.

---
