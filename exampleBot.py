import random
import socket
import sys

import json
import numpy as np

from blobs import Board, Match, Turn

NO_OWNER = 0
FOOD_OWNER = 1

PLAYER_NAME = sys.argv[1]

#HOST = '94.45.244.97'
HOST = '127.0.0.1'
PORT = 1234
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.connect((HOST, PORT))

s.sendall(('{{"type": "register", "user": "{0}", "password": "tollespasswort"}}'.format(PLAYER_NAME)).encode("utf8"))
data = s.recv(1024)
print('Received', repr(data))

s.sendall(('{{"type": "login", "user": "{0}", "password": "tollespasswort"}}'.format(PLAYER_NAME)).encode("utf8"))
data = s.recv(1024)
print('Received', repr(data))

def num_own_neighbors(d, fields, my_pid, ignore=[]):
    adjacent = [[d[0], d[1]+1], [d[0], d[1]-1], [d[0]+1, d[1]], [d[0]-1, d[1]]]
    return len([f for f in fields if f[0] in adjacent and f[1] == my_pid and f[0] not in ignore])

class User:
    def __init__(self, id):
        self.connection_id = id
        self.username = "Foo"

for line in s.makefile("rb"):
    state = json.loads(line.decode("utf8"))

    current_board = Board(state["board_size"])
    slx = [x[0] for x in state["fields_used"]]
    sly = [x[1] for x in state["fields_used"]]
    current_board.owner[slx,sly] = np.array(state["fields_owned_by"])
    current_board.values[slx,sly] = np.array(state["fields_values"])

    #print(state)
    my_pid = [p[1] for p in state["player_names"] if p[0] == PLAYER_NAME][0]
    fields = list(zip(state["fields_used"], state["fields_owned_by"], state["fields_values"]))
    #print(fields)
    food = [f[0] for f in fields if f[1] == FOOD_OWNER]
    me = [f[0] for f in fields if f[1] == my_pid]
    neigh = [num_own_neighbors(f[0], fields, my_pid) for f in fields if f[1] == my_pid]
    best = max(neigh)
    print("Num neighbors, best:", neigh, best)
    print(me, my_pid)

    source = tuple(random.choice(me))
    dist_to_food = [(abs(source[0] - f[0]) + abs(source[1] - f[1])) for f in food]
    best_food = food[dist_to_food.index(min(dist_to_food))]
    dist_to_best = [(abs(best_food[0] - f[0]) + abs(best_food[1] - f[1])) for f in me]
    move_to = me[dist_to_best.index(min(dist_to_best))]
    for item in me:
        source = tuple(item)
        if move_to[0] > best_food[0]:
            dest = (move_to[0]-1, move_to[1])
        elif move_to[0] < best_food[0]:
            dest = (move_to[0]+1, move_to[1])
        elif move_to[1] > best_food[1]:
            dest = (move_to[0], move_to[1]-1)
        else:
            dest = (move_to[0], move_to[1]+1)

        t = Turn(source, dest, User(my_pid))
        m = Match([User(my_pid)], current_board, None)
        ok, message = m.checkTurn(t)
        print(ok, message)
        if ok:
            break

    print("Sending turn:", source, dest, "towards", best_food)
    s.sendall('{{ "type": "move", "from": {0}, "to": {1} }}\n'.format(list(source), list(dest)).encode("utf8"))
    print("Reply:", s.recv(1024))

s.close()
