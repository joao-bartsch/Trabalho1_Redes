"""
Ponto de entrada do cliente de teste.

Uso:
    python -m client.main <nome>
    python -m client.main Ana
"""

import sys
import threading

from server.config import HOST, PORT
from client.cliente import Cliente


def main() -> None:
    if len(sys.argv) < 2:
        print("Uso: python -m client.main <nome>")
        print("Exemplo: python -m client.main Ana")
        sys.exit(1)

    nome = sys.argv[1]

    # Se estiver rodando local, usa 127.0.0.1 em vez de 0.0.0.0
    host = "127.0.0.1" if HOST == "0.0.0.0" else HOST

    cli = Cliente(host, PORT, nome)
    cli.conectar()

    # Thread de recebimento (fica mostrando mensagens)
    t = threading.Thread(target=cli.loop_recebimento, daemon=True)
    t.start()

    # Thread principal: input do usuário
    cli.loop_input()

    print("[CLIENTE] saindo.")


if __name__ == "__main__":
    main()