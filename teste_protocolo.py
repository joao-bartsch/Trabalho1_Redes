import socket
import threading
import time

from common import protocolo as p

def servidor():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 5000))
    srv.listen(1)
    conn, _ = srv.accept()
    buf = b""
    msgs, buf = p.receber(conn, buf)
    print("[SERVER] recebeu:", msgs)
    p.enviar(conn, {"tipo": "bem_vindo", "sala": 1, "jogador": "jogador1"})
    conn.close()
    srv.close()

def cliente():
    time.sleep(0.3)
    c = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    c.connect(("127.0.0.1", 5000))
    p.enviar(c, {"tipo": "entrar", "nome": "Fulano"})
    p.enviar(c, {"tipo": "pronto"})
    buf = b""
    msgs, buf = p.receber(c, buf)
    print("[CLIENT] recebeu:", msgs)
    c.close()

t1 = threading.Thread(target=servidor)
t2 = threading.Thread(target=cliente)
t1.start(); t2.start()
t1.join(); t2.join()