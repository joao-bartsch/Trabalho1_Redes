"""
Ponto de entrada do servidor.

Uso:
    python -m server.main
"""

from server.servidor import Servidor


def main() -> None:
    servidor = Servidor()
    servidor.iniciar()


if __name__ == "__main__":
    main()