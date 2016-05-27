#!/usr/bin/env python
# -*- coding: UTF-8 -*-

import sys
import matplotlib.pyplot as plt
import numpy as np
import json
import zlib
import binascii
from twisted.internet import protocol, reactor, endpoints

NO_OWNER = 0
FOOD_OWNER = 1
MIN_PID = 1000
PLAYERS_IN_MATCH = 2
BOARD_SIZE = 64
FOOD_ABUNDANCE = 0.01
MAX_ROUNDS = 1000

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
        "game_waiting": [],
        "game_your_turn": ["move"],
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
        self.currentMatch = None
        self.username = None

    def connectionLost(self, reason):
        self.lobby.notifyUserDisconnected(self)
        if self.currentMatch:
            self.currentMatch.removeUser(self)

    def matchStarted(self, match):
        assert isinstance(match, Match)
        self.network_state = "game_waiting"
        self.currentMatch = match

    def askTurn(self):
        names = self.currentMatch.playerNames()
        populated = self.currentMatch.board.populated()
        owners = self.currentMatch.board.owner[populated]
        values = self.currentMatch.board.values[populated]
        used = [(int(x), int(y)) for x, y in zip(populated[0], populated[1])]
        self.network_state = "game_your_turn"
        pkg = {
            "type": "your_turn",
            "player_names": names,
            "fields_used": used,
            "fields_owned_by": [int(x) for x in owners],
            "fields_values": [int(x) for x in values]
        }
        self.transport.write(json.dumps(pkg).encode("utf8"))

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
            else:
                self._sendErrorResponse("Username already taken.")
        elif data["type"] == "login":
            if self.lobby.checkUserLogin(data["user"], data["password"]):
                self._sendSuccessResponse()
                self.network_state = "lobby"
                self.username = data["user"]
                self.lobby.notifyUserConnected(self)
            else:
                self._sendErrorResponse("Invalid login credentials.")
        elif data["type"] == "move":
            ok, message = self.currentMatch.checkedTurn(Turn(data["from"], data["to"], self))
            if ok:
                self._sendSuccessResponse(message)
            else:
                self._sendErrorResponse(message)
            self.network_state = "game_waiting"
            done = self.currentMatch.checkMatchFinished()
            if done:
                self.lobby.finalizeMatch(self.currentMatch)
            else:
                next = self.currentMatch.nextUser()
                next.askTurn()

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
        self.current_user_id = MIN_PID # lower IDs have special meanings ("no owner" etc)
        self.loadUserDb()
        self.activeUsers = []
        self.activeMatches = []
        self.history = MatchHistory()

    def finalizeMatch(self, match):
        for user in match.users:
            user.transport.loseConnection()
        for spec in match.spectators:
            spec.stopSpectating()
        match.status = "finished"
        #match.winner
        # TODO fill in winner
        self.history.addMatch(match.history)
        self.activeMatches.remove(match)

    def notifyUserConnected(self, user):
        print("User connected to lobby:", user)
        self.activeUsers.append(user)
        print("Users active:", len(self.activeUsers))
        idle = [u for u in self.activeUsers if u.network_state == "lobby"]
        print("Users idle:", len(idle))
        if len(idle) >= PLAYERS_IN_MATCH:
            self.makeMatch(idle[:PLAYERS_IN_MATCH])

    def notifyUserDisconnected(self, user):
        print("User disconnected from lobby:", user)
        if user.network_state != "unauthorized":
            self.activeUsers.remove(user)

    def makeMatch(self, users):
        print("Starting new match.")
        board = Board(BOARD_SIZE)
        board.populate(users)
        match = Match(users, board)
        self.activeMatches.append(match)
        for user in users:
            user.matchStarted(match)
        users[0].askTurn()

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
        self.dest = int(dest[0]), int(dest[1])
        self.source = int(source[0]), int(source[1])
        self.player = player


class Match:
    def __init__(self, users, board):
        assert isinstance(board, Board)
        self.board = board
        self.users = users
        self.currentUser = self.users[0]
        self.current_round = 0
        self.history = {
            "users": [u.username for u in self.users],
            "board_size": self.board.size,
            "turns": [],
            "status": "playing",
            "winner": None
        }
        self.spectators = []
        self.addStateToHistory()

    def nextUser(self) -> User:
        i = (self.users.index(self.currentUser) + 1) % len(self.users)
        self.currentUser = self.users[i]
        return self.currentUser

    def playerNames(self):
        return [(u.username, u.userid) for u in self.users]

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
        print("Executing turn:", turn)
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
            return False, "source field not populated by you"

        if (0 > turn.dest[0] >= self.board.size) or (0 > turn.dest[1] >= self.board.size):
            return False, "destination location out of bounds"

        if self.board.owner[turn.dest] != turn.player.userid:
            adj = self.board.adjacent(turn.dest)
            for a in adj:
                if a == turn.source and self.board.values[turn.source] == 1:
                    continue
                if self.board.owner[a] == turn.player.userid:
                    break
            else:
                return False, "no adjacent allied fields at target location"

        destOwner = self.board.owner[turn.dest]
        isEnemy = destOwner > MIN_PID and destOwner != turn.player.userid
        if isEnemy and self.board.values[turn.dest] > self.board.values[turn.source] + 1:
            return False, "you cannot attack fields stronger than you"

        if self.board.values[turn.source] == 1:
            self.board.owner[turn.source] = NO_OWNER
        if not self.board.playerContiguous(turn.player.userid):
            self.board.owner[turn.source] = turn.player.userid
            return False, "you would split yourself"
        self.board.owner[turn.source] = turn.player.userid

        return True, "turn ok"

    def checkedTurn(self, turn):
        ok, message = self.checkTurn(turn)
        self.current_round += 1
        if ok:
            self.execTurn(turn)
            self.addStateToHistory()
            for spectator in self.spectators:
                spectator.sendActiveMatch(self)
        return ok, message

    def checkMatchFinished(self):
        if self.current_round >= MAX_ROUNDS:
            return True
        owned_by_player = self.board.owner >= MIN_PID
        interesting = self.board.owner[owned_by_player]
        return not interesting.any() or (interesting[0] == interesting).all()

    def addStateToHistory(self):
        self.history["turns"].append(MatchHistory.encodeState(self.board.values, self.board.owner))

    def removeUser(self, user):
        if self.currentUser == user:
            next = self.nextUser()
            next.askTurn()
        self.users.remove(user)
        mask = self.board.owner == user.userid
        self.board.values[mask] = 0
        self.board.owner[mask] = NO_OWNER


class Board:
    def __init__(self, size):
        self.values = np.zeros((size, size), dtype=np.uint16)
        self.owner = np.zeros_like(self.values)
        self.size = size

    def adjacent(self, d):
        return [(d[0], d[1]+1), (d[0], d[1]-1), (d[0]+1, d[1]), (d[0]-1, d[1])]

    def random_free_field(self):
        while True:
            x, y = np.random.randint(0, BOARD_SIZE-1), np.random.randint(0, BOARD_SIZE-1)
            if self.owner[x][y] == NO_OWNER:
                return x, y

    def populate(self, users):
        for user in users:
            start = self.random_free_field()
            self.values[start] = 1
            self.owner[start] = user.userid
            self.values[start[0]+1,start[1]] = 1
            self.owner[start[0]+1,start[1]] = user.userid
        for food in range(np.random.poisson(int(FOOD_ABUNDANCE * BOARD_SIZE**2))):
            field = self.random_free_field()
            self.values[field] = 1
            self.owner[field] = FOOD_OWNER

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

    def populated(self):
        return np.where(self.owner != NO_OWNER)


class MatchHistory:
    def __init__(self):
        self.filename = "match.db"
        self.matches = []
        self.player_matches = {}
        self.current_match_id = 0
        self.loadMatchData()

    @staticmethod
    def encodeState(values, owner):
        data = self.board.values.tostring() + self.board.owner.tostring()
        compressed = binascii.b2a_base64(zlib.compress(data)).decode("utf8")
        return compressed

    @staticmethod
    def decodeState(board_size, compressed):
        binary = zlib.decompress(binascii.a2b_base64(compressed))
        values_raw = binary[:len(binary)//2]
        owner_raw = binary[len(binary)//2:]
        values = np.fromstring(values_raw, "uint16", board_size*board_size)
        owner = np.fromstring(owner_raw, "uint16", board_size*board_size)
        values.reshape((board_size, board_size))
        owner.reshape((board_size, board_size))
        return values, owner

    def loadMatchData(self):
        self.matches = []
        self.player_matches = {}
        self.current_match_id = 0
        print("Loading matches…", end="")
        try:
            with open(self.filename) as f:
                for line in f:
                    match = json.loads(line)
                    self.addMatch(match, False)
            print(" done! {} matches loaded".format(self.current_match_id))
        except IOError as e:
            print(" cannot open database. {}".format(str(e)))

    def addMatch(self, match_history, save_to_file=True):
        self.matches.append(match_history)
        for p in match_history["users"]:
            if p in self.player_matches:
                self.player_matches[p].append(self.current_match_id)
            else:
                self.player_matches[p] = [self.current_match_id]
        if save_to_file:
            with open(self.filename, "a") as f:
                f.write(json.dumps(match_history)+"\n")
        self.current_match_id += 1


if __name__ == '__main__':
    #b = Board(40)
    #l = Lobby()
    #u1 = User(1001, None, l)
    #u2 = User(1002, None, l)
    #m = Match([u1, u2], b)
    #b.values[20:30,20:30] = 10
    #b.owner[20:30,20:30] = u1.userid
    #b.owner[28:35,30:35] = u2.userid
    #b.values[28:35,30:35] = 1

    #t = Turn((20,20), (19,22), u1)
    #m.checkedTurn(t)
    #t = Turn((20,21), (28,30), u1)
    #m.checkedTurn(t)
    #plt.imshow(b.values.astype(np.float64), clim=(0, 10), interpolation="nearest", cmap="hot")
    #plt.show()

    l = Lobby()
    endpoints.serverFromString(reactor, "tcp:1234").listen(l)
    reactor.run()




