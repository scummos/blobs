#!/usr/bin/env python
# -*- coding: UTF-8 -*-

NO_OWNER = 0
FOOD_OWNER = 1
MIN_PID = 1000

import sys
import matplotlib.pyplot as plt
import numpy as np
import json
from twisted.internet import protocol, reactor, endpoints

class User(protocol.Protocol):
    """
    A dictionary of all valid network states with accepted requests.
    Used for automated package validity checks.
    """
    network_states = {
        # freshly connected user. No successful registration or login, yet.
        "unauthorized": ["register", "login"],
        # user is in lobby and awaits connection
        "lobby": [],
        "game": ["move"],
    }
    """
    Required fields in the JSON dictionary forming each request.
    Used for automated package validity checks.
    """
    request_fields = {
        "register": ["user", "password"],
        "login": ["user", "password"],
        "move": ["from", "to"]
    }
    def __init__(self, userid, addr, lobby):
        self.userid = userid
        self.address = addr
        self.lobby = lobby
        self.network_state = "unauthorized"

    def sendMessage(self, message):
        pass

    def receiveTurnCommand(self):
        pass

    def askTurn(self, match):
        self.sendMessage(match.stateString())
        return self.receiveTurnCommand()

    def dataReceived(self, rawdata):
        # internal check. Have we set the network state to a valid value?
        if self.network_state not in User.network_states.keys():
            raise Exception("Somewhere an invalid network state was set for user ID {}".format(self.userid))
        try:
            rawdata = rawdata.decode("utf8")
            data = json.loads(rawdata)
        except Exception as e:
            print("Invalid JSON string received from UID {} via {}: {}\n{}".format(
                self.userid, self.address, repr(rawdata), str(e))
            )
            self._sendErrorResponse("Invalid request, JSON/UTF8 error: {}".format(str(e)))
            #self.transport.close()
            return
        # Is the request type known to the server, at all?
        if data["type"] not in User.request_fields.keys():
            self._sendErrorResponse("Unknown request")
            return
        # Is the request allowed in the current network state?
        if data["type"] not in User.network_states[self.network_state]:
            self._sendErrorResponse("Not allowed.")
            return
        # Are all required fields set?
        for field in User.request_fields[data["type"]]:
            if field not in data:
                self._sendErrorResponse("Required field '{}' not found.".format(field))
        # Dispatch user request to different subsytems
        if data["type"] == "register":
            if self.lobby.registerUser(data["user"], data["password"]):
                self._sendSuccessResponse()
                self.network_state = "lobby"
            else:
                self._sendErrorResponse("Username already taken.")
        elif data["type"] == "login":
            if self.lobby.checkUserLogin(data["user"], data["password"]):
                self._sendSuccessResponse()
                self.network_state = "lobby"
            else:
                self._sendErrorResponse("Invalid login credentials.")

    def _sendErrorResponse(self, message):
        pkg = {
            "type": "response",
            "status": "failure",
            "message": message
        }
        self.transport.write(json.dumps(pkg).encode("utf8"))

    def _sendSuccessResponse(self, message="Ok."):
        pkg = {
            "type": "response",
            "status": "success",
            "message": message
        }
        self.transport.write(json.dumps(pkg).encode("utf8"))


class Lobby(protocol.Factory):
    def __init__(self):
        self.user_db = {}
        self.current_user_id = 1000 # lower IDs have special meanings ("no owner" etc)
        self.loadUserDb()

    def registerUser(self, user, password):
        if user in self.user_db:
            return False
        self.user_db[user] = {
            "password": password,
            "score": 0,
        }
        self.writeUserDb()
        return True

    def checkUserLogin(self, user, password):
        if user not in self.user_db:
            return False
        return self.user_db[user]["password"] == password

    def writeUserDb(self):
        with open("user.db", "w") as f:
            f.write(json.dumps(self.user_db, indent=2))

    def loadUserDb(self):
        try:
            with open("user.db") as f:
                self.user_db = json.loads(f.read())
        except IOError:
            print("No user database found.")

    def buildProtocol(self, addr):
        self.current_user_id += 1
        return User(self.current_user_id, addr, self)


class Turn:
    def __init__(self, source, dest, player):
        self.dest = dest
        self.source = source
        self.player = player

class Match:
    def __init__(self, users, board):
        assert isinstance(board, Board)
        self.board = board
        self.users = users

    def splitCreatedByTurn(self, affectedPos, destOwner):
        neighbors = self.board.adjacent(affectedPos)
        full = self.board.ownedByPlayer(destOwner)
        components = []
        for neighbor in neighbors:
            if self.board.owner[neighbor] != destOwner:
                continue
            c = self.board.connected(neighbor)
            if (c == full).all():
                break
            components.append(c)
        return components

    def execFight(self, turn, srcOwner, destOwner):
        self.board.owner[turn.dest] = srcOwner
        destValue = self.board.values[turn.dest]
        srcValue = self.board.values[turn.source]
        self.board.values[turn.dest] = srcValue - destValue - 1

        components = self.splitCreatedByTurn(turn.dest, destOwner)
        if len(components) > 0:
            sizes = [len(q) for q in components]
            largest = components[np.argmax(sizes)]
            for comp in components:
                if comp == largest:
                    continue
                self.board.values[turn.dest] += np.sum(self.board.values[comp])
                self.board.values[comp] = 0
                self.board.owner[comp] = NO_OWNER

    def execTurn(self, turn: Turn):
        destOwner = self.board.owner[turn.dest]
        srcOwner = self.board.owner[turn.source]
        if destOwner == NO_OWNER or srcOwner == destOwner:
            self.board.values[turn.dest] += 1
            self.board.owner[turn.dest] = srcOwner
            self.board.values[turn.source] -= 1
            if self.board.values[turn.source] == 0:
                self.board.owner[turn.source] = NO_OWNER
        elif destOwner == FOOD_OWNER:
            self.board.owner[turn.dest] = srcOwner
        else:
            # field owned by enemy
            self.execFight(turn, srcOwner, destOwner)

        assert self.board.playerContiguous(turn.player.userid)

    def checkTurn(self, turn: Turn):
        if self.board.owner[turn.source] != turn.player.userid:
            print("invalid source owner")
            return False

        if (0 > turn.dest[0] >= self.board.size) or (0 > turn.dest[1] >= self.board.size):
            print("invalid desination location")
            return False

        adj = self.board.adjacent(turn.dest)
        for a in adj:
            if a == turn.source:
                continue
            if self.board.owner[a] == turn.player.userid:
                break
        else:
            print("no adjacent allied fields")
            return False

        destOwner = self.board.owner[turn.dest]
        isEnemy = destOwner > MIN_PID and destOwner != turn.player.userid
        if isEnemy and self.board.values[turn.dest] > self.board.values[turn.source] + 1:
            print("not enough points to DESTROY THE ENEMEY")
            return False

        if len(self.splitCreatedByTurn(turn.source, turn.player.userid)) > 0:
            print("you would split yourself")
            return False

        return True

    def checkedTurn(self, turn):
        if self.checkTurn(turn):
            self.execTurn(turn)
        else:
            print("Invalid turn:", turn)

    def turn(self):
        for user in self.users:
            turn = user.askTurn(self)
            self.checkedTurn(turn)
            self.checkMatchFinished()

    def checkMatchFinished(self):
        owned_by_player = self.board.owner >= MIN_PID
        interesting = self.board.owner[owned_by_player]
        return not interesting.any() or (interesting[0] == interesting).all()

class Board:
    def __init__(self, size):
        self.values = np.zeros((size, size), dtype=np.uint16)
        self.owner = np.zeros_like(self.values)
        self.size = size

    def adjacent(self, d):
        return [(d[0], d[1]+1), (d[0], d[1]-1), (d[0]+1, d[1]), (d[0]-1, d[1])]

    def connected(self, pos):
        owner = self.owner[pos]
        component = np.zeros_like(self.owner, dtype=np.bool)
        component[pos] = True
        interesting = self.owner == owner
        value = -1
        while interesting.any():
            previous_value = value
            value = np.sum(component)
            if previous_value == value:
                break
            component[:,:-1] |= interesting[:,:-1] & component[:,1:]
            component[:,1:] |= interesting[:,1:] & component[:,:-1]
            component[:-1,:] |= interesting[:-1,:] & component[1:,:]
            component[1:,:] |= interesting[1:,:] & component[:-1,:]
        return component

    def playerContiguous(self, player: int):
        field = np.where(self.owner == player)
        field = field[0][0], field[1][0]
        return (self.ownedByPlayer(player) == self.connected(field)).all()

    def ownedByPlayer(self, player: int):
        return self.owner == player

if __name__ == '__main__':
    b = Board(40)
    l = Lobby()
    u1 = User(1001, None, l)
    u2 = User(1002, None, l)
    m = Match([u1, u2], b)
    b.values[20:30,20:30] = 10
    b.owner[20:30,20:30] = u1.userid
    b.owner[28:35,30:35] = u2.userid
    b.values[28:35,30:35] = 1

    t = Turn((20,20), (19,22), u1)
    m.checkedTurn(t)
    t = Turn((20,21), (28,30), u1)
    m.checkedTurn(t)
    plt.imshow(b.values.astype(np.float64), clim=(0, 10), interpolation="nearest", cmap="hot")
    plt.show()

    #l = Lobby()
    #endpoints.serverFromString(reactor, "tcp:1234").listen(l)
    #reactor.run()




