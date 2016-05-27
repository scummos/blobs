import socket
import sys

import json

NO_OWNER = 0
FOOD_OWNER = 1

PLAYER_NAME = sys.argv[1]

HOST = 'localhost'
PORT = 1234
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.connect((HOST, PORT))

s.sendall(('{{"type": "register", "user": "{0}", "password": "tollespasswort"}}'.format(PLAYER_NAME)).encode("utf8"))
data = s.recv(1024)
print('Received', repr(data))

s.sendall(('{{"type": "login", "user": "{0}", "password": "tollespasswort"}}'.format(PLAYER_NAME)).encode("utf8"))
data = s.recv(1024)
print('Received', repr(data))

def num_own_neighbors(d, fields, my_pid):
    adjacent = [[d[0], d[1]+1], [d[0], d[1]-1], [d[0]+1, d[1]], [d[0]-1, d[1]]]
    return len([f for f in fields if f[0] in adjacent and f[1] == my_pid])

while True:
    buf = bytes()
    while len(buf) == 0 or buf[-1] != ord('}'):
        data = s.recv(1024)
        if len(data) == 0:
            print("Connection closed")
            exit(1)
        buf += data
    state = json.loads(buf.decode("utf8"))
    my_pid = [p[1] for p in state["player_names"] if p[0] == PLAYER_NAME][0]
    fields = list(zip(state["fields_used"], state["fields_owned_by"], state["fields_values"]))
    print(fields)
    food = [f[0] for f in fields if f[1] == FOOD_OWNER]
    me = [f[0] for f in fields if f[1] == my_pid]
    neigh = [num_own_neighbors(f[0], fields, my_pid) for f in fields if f[1] == my_pid]
    best = max(neigh)
    print("Num neighbors, best:", neigh, best)

    source = fields[neigh.index(best)][0]
    dist_to_food = [(abs(source[0] - f[0]) + abs(source[1] - f[1])) for f in food]
    best_food = food[dist_to_food.index(min(dist_to_food))]
    dist_to_best = [(abs(best_food[0] - f[0]) + abs(best_food[1] - f[1])) for f in me]
    move_to = food[dist_to_best.index(min(dist_to_best))]
    if move_to[0] > best_food[0]:
        dest = (move_to[0]-1, move_to)
    elif move_to[0] < best_food[0]:
        dest = (move_to[0]+1, move_to)
    elif move_to[1] > best_food[1]:
        dest = (move_to[0], move_to[1]-1)
    else:
        dest = (move_to[0], move_to[1]+1)

    print("Sending turn:", source, dest)
    s.sendall('{{ "type": "move", "from": "{0}", "to": "{1}" }}\n'.format(source, dest).encode("utf8"))

s.close()
