import socket
import sys

import json

HOST = 'localhost'
PORT = 1234
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.connect((HOST, PORT))

s.sendall(('{{"type": "register", "user": "{0}", "password": "tollespasswort"}}'.format(sys.argv[1])).encode("utf8"))
data = s.recv(1024)
print('Received', repr(data))

s.sendall(('{{"type": "login", "user": "{0}", "password": "tollespasswort"}}'.format(sys.argv[1])).encode("utf8"))
data = s.recv(1024)
print('Received', repr(data))

while True:
    buf = bytes()
    while len(buf) == 0 or buf[-1] != ord('}'):
        data = s.recv(1024)
        if len(data) == 0:
            print("Connection closed")
            exit(1)
        buf += data
    state = json.loads(buf.decode("utf8"))
    print(state)

s.close()
