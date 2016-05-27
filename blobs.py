#!/usr/bin/env python
# -*- coding: UTF-8 -*-

import sys
import matplotlib.pyplot as plt
import numpy as np
import json
import zlib
import logging
import binascii
from twisted.internet import protocol, reactor, endpoints

NO_OWNER = 0
FOOD_OWNER = 1
MIN_PID = 1000
PLAYERS_IN_MATCH = 2
BOARD_SIZE = 64
FOOD_ABUNDANCE = 0.01
MAX_ROUNDS = 5000

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
    def __init__(self, connection_id, addr, lobby):
        self.logger = logging.getLogger("User(id={})".format(connection_id))
        self.connection_id = connection_id
        self.address = addr
        self.lobby = lobby
        self.network_state = "unauthorized"
        self.currentMatch = None
        self.username = None

    def __str__(self):
        return "User(id={}, name={})".format(self.connection_id, self.username)

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
            raise Exception("Somewhere an invalid network state was set for connection ID {}".format(self.connection_id))
        try:
            rawdata = rawdata.decode("utf8")
            data = json.loads(rawdata)
        except Exception as e:
            self.logger.error("Invalid JSON string received from connection ID {} via {}\n{}".format(
                self.connection_id, self.address, str(e))
            )
            self._sendErrorResponse("Invalid request, JSON/UTF8 error: {}".format(str(e)))
            self.transport.loseConnection()
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
            done, winner = self.currentMatch.checkMatchFinished()
            if done:
                self.finalize()
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
        self.logger = logging.getLogger("Lobby")
        self.user_db = {}
        self.current_user_id = MIN_PID # lower IDs have special meanings ("no owner" etc)
        self.loadUserDb()
        self.activeUsers = []
        self.activeMatches = []
        self.history = MatchHistory()
        self.waiting_spectators = []

    def addSpectator(self, spectator):
        if self.activeMatches:
            self.activeMatches[0].spectators.append(spectator)
            spectator.startSpectating(self.activeMatches[0])
        else:
            self.waiting_spectators.append(spectator)

    def removeSpectator(self, spectator):
        spectator.stopSpectating()
        try:
            self.waiting_spectators.remove(spectator)
        except ValueError:
            pass

    def notifyUserConnected(self, user):
        self.logger.info("User connected to lobby: {}".format(user))
        self.activeUsers.append(user)
        self.logger.debug("Users active: {}".format(len(self.activeUsers)))
        idle = [u for u in self.activeUsers if u.network_state == "lobby"]
        self.logger.debug("Users idle: {}".format(len(idle)))
        if len(idle) >= PLAYERS_IN_MATCH:
            self.makeMatch(idle[:PLAYERS_IN_MATCH])

    def notifyUserDisconnected(self, user):
        self.logger.info("User disconnected from lobby: {}".format(user))
        if user.network_state != "unauthorized":
            self.activeUsers.remove(user)

    def makeMatch(self, users):
        self.logger.info("Starting new match.")
        board = Board(BOARD_SIZE)
        board.populate(users)
        match = Match(users, board)
        self.activeMatches.append(match)
        for user in users:
            user.matchStarted(match)
        users[0].askTurn()
        for spec in self.waiting_spectators:
            spec.startSpectating(match)

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
            self.logger.info("No user database found.")

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
        self.logger = logging.getLogger("Match({})".format(
            ", ".join("{}({})".format(u.username, u.connection_id) for u in users)))
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


    def finalize(self):
        self.logger.info("Finalize")
        for user in self.users:
            user.transport.loseConnection()
        specs = self.spectators[:]
        for spec in self.spectators:
            spec.streamFinished()
        done, winner = self.checkMatchFinished()
        self.history["status"] = "finished"
        if winner:
            self.history["winner"] = winner.username
        else:
            winner = self.getLargestPlayer()
            if winner:
                self.history["winner"] = winner.username
            self.history["score"] = dict((user.username, score) for user, score in self.getPlayerSizes().items())
        if self.history["winner"]:
            self.user_db[self.history["winner"]]["score"] += 1
            self.writeUserDb()
        self.addStateToHistory()
        for spectator in self.spectators:
            spectator.sendActiveMatch(self)
        self.lobby.history.addMatch(self.history)
        self.lobby.activeMatches.remove(self)
        for spec in specs:
            self.lobby.addSpectator(spec)

    def getUserById(self, uid):
        for user in self.users:
            if user.connection_id == uid:
                return user
        return None

    def nextUser(self) -> User:
        i = (self.users.index(self.currentUser) + 1) % len(self.users)
        self.currentUser = self.users[i]
        return self.currentUser

    def playerNames(self):
        return [(u.username, u.connection_id) for u in self.users]

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
                if (comp == largest).all():
                    continue
                self.board.values[turn.dest] += np.sum(self.board.values[comp])
                self.board.values[comp] = 0
                self.board.owner[comp] = NO_OWNER

    def execTurn(self, turn: Turn):
        self.logger.debug("Executing turn {}".format(self.current_round))
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
        assert self.board.playerContiguous(turn.player.connection_id)

    def paintTurn(self, out):
        plt.imshow(self.board.owner.astype(np.float64), clim=(1000, 1005), interpolation="nearest", cmap="hot")
        plt.savefig(out)
        plt.clf()

    def checkTurn(self, turn: Turn):
        if self.board.owner[turn.source] != turn.player.connection_id:
            return False, "source field not populated by you"

        if (0 > turn.dest[0] >= self.board.size) or (0 > turn.dest[1] >= self.board.size):
            return False, "destination location out of bounds"

        if self.board.owner[turn.dest] != turn.player.connection_id:
            adj = self.board.adjacent(turn.dest)
            for a in adj:
                if a == turn.source and self.board.values[turn.source] == 1:
                    continue
                if self.board.owner[a] == turn.player.connection_id:
                    break
            else:
                return False, "no adjacent allied fields at target location"

        destOwner = self.board.owner[turn.dest]
        isEnemy = destOwner > MIN_PID and destOwner != turn.player.connection_id
        if isEnemy and self.board.values[turn.dest] > self.board.values[turn.source] + 1:
            return False, "you cannot attack fields stronger than you"

        if self.board.values[turn.source] == 1:
            self.board.owner[turn.source] = NO_OWNER
        if not self.board.playerContiguous(turn.player.connection_id):
            self.board.owner[turn.source] = turn.player.connection_id
            return False, "you would split yourself"
        self.board.owner[turn.source] = turn.player.connection_id

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
            return True, None
        owned_by_player = self.board.owner >= MIN_PID
        interesting = self.board.owner[owned_by_player]
        return not interesting.any() or (interesting[0] == interesting).all(), self.getUserById(interesting[0])

    def getLargestPlayer(self):
        sizes = self.getPlayerSizes()
        user, max_score = max(sizes.items(), key=lambda x: x[1])
        if list(sizes.values()).count(max_score) > 1:
            return None
        else:
            return user

    def getPlayerSizes(self):
        sizes = {}
        for user in self.users:
            size = int(np.sum(self.board.values[self.board.owner == user.connection_id]))
            sizes[user] = size
        return sizes

    def addStateToHistory(self):
        self.history["turns"].append(MatchHistory.encodeState(self.board.values, self.board.owner))

    def removeUser(self, user):
        if self.currentUser == user:
            next = self.nextUser()
            next.askTurn()
        self.users.remove(user)
        mask = self.board.owner == user.connection_id
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
            self.owner[start] = user.connection_id
            self.values[start[0]+1,start[1]] = 1
            self.owner[start[0]+1,start[1]] = user.connection_id
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
        self.logger = logging.getLogger("MatchHistory")
        self.filename = "match.db"
        self.matches = []
        self.player_matches = {}
        self.current_match_id = 0
        self.loadMatchData()

    @staticmethod
    def encodeState(values, owner):
        data = values.tostring() + owner.tostring()
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
        self.logger.info("Loading matches…")
        try:
            with open(self.filename) as f:
                for line in f:
                    match = json.loads(line)
                    self.addMatch(match, False)
            self.logger.info(" … done! {} matches loaded".format(self.current_match_id))
        except IOError as e:
            self.logger.info(" cannot open database. {}".format(str(e)))

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


class Spectator(protocol.Protocol):
    def __init__(self, lobby, addr):
        self.logger = logging.getLogger("Spectator({})".format(str(addr)))
        self.lobby = lobby
        self.addr = addr
        self.watchedMatch = None

    def startSpectating(self, match):
        assert(self.watchedMatch is None)
        self.watchedMatch = match
        try:
            self.lobby.waiting_spectators.remove(self)
        except ValueError:
            pass
        self.watchedMatch.spectators.append(self)
        self._sendMessage({"type":"start_stream"})

    def streamFinished(self):
        self._sendMessage({"type":"stream_finished", "message":"Match is finished."})
        try:
            self.watchedMatch.spectators.remove(self)
        except ValueError:
            pass
        self.watchedMatch = None

    def stopSpectating(self):
        if self.watchedMatch:
            self.watchedMatch.spectators.remove(self)
            self.watchedMatch = None
        try:
            self.lobby.waiting_spectators.remove(self)
        except ValueError:
            pass

    def connectionLost(self, reason):
        self.logger.info("Spectator disconnected: "+str(reason))
        self.stopSpectating()

    def dataReceived(self, rawdata):
        try:
            data = json.loads(rawdata.decode("utf8"))
        except Exception as e:
            self._sendErrorResponse("Error while parsing JSON package: {}".format(str(e)))
            return
        try:
            if "type" not in data:
                self._sendErrorResponse("Required 'type' field not found.")
                return
            if data["type"] == "get_historic_match":
                if "match_id" not in data:
                    self._sendErrorResponse("match_id not supplied.")
                    return
                mid = data["match_id"]
                if mid >= len(self.lobby.history.matches) or mid < 0:
                    self._sendErrorResponse("404 match not found.")
                    return
                self._sendSuccessResponse(message="Fuck yes.", match=self.lobby.history.matches[mid])
            elif data["type"] == "get_historic_match_list":
                if "by_user" in data:
                    user = data["by_user"]
                    if user not in self.lobby.user_db.keys():
                        self._sendErrorResponse("Unknown user.")
                        return
                    player_matches = self.lobby.history.player_matches
                    matches = []
                    if user in player_matches:
                        matches = player_matches[user]
                    self._sendSuccessResponse(message="Got it.", matches=matches)
                else:
                    matches = list(range(len(self.lobby.history.matches)))
                    self._sendSuccessResponse(message="Got it.", matches=matches)
            elif data["type"] == "get_users":
                users = {}
                disallowed_keys = ["password"]
                # no password :P
                for user, data in self.lobby.user_db.items():
                    users[user] = dict(
                        (key, val) for key, val in data.items() if key not in disallowed_keys
                    )
                self._sendSuccessResponse(message="Yessir.", users=users)
            elif data["type"] == "stream_game":
                self.lobby.addSpectator(self)
            else:
                self._sendErrorResponse("Unknown request.")
        except Exception as e:
            self._sendErrorResponse("Server Error :/")
            self.logger.error("Error while processing spectator request: {}".format(str(e)))

    def sendActiveMatch(self, match):
        pkg = { "type": "stream_turn" }
        pkg.update(match.history)
        pkg["turn"] = pkg["turns"][-1]
        del pkg["turns"]
        self._sendMessage(pkg)

    def _sendMessage(self, data):
        self.transport.write(json.dumps(data).encode("utf8")+b"\n")

    def _sendErrorResponse(self, message, **kwargs):
        pkg = {
            "type": "response",
            "status": "failure",
            "message": message
        }
        pkg.update(kwargs)
        self._sendMessage(pkg)

    def _sendSuccessResponse(self, message="Ok.", **kwargs):
        pkg = {
            "type": "response",
            "status": "success",
            "message": message
        }
        pkg.update(kwargs)
        self._sendMessage(pkg)


class SpectatorFactory(protocol.Factory):
    def __init__(self, lobby):
        self.lobby = lobby

    def buildProtocol(self, addr):
        return Spectator(self.lobby, addr)


if __name__ == '__main__':
    # create logger
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter("%(name)s - %(levelname)s - %(message)s")

    # create console handler and set level to debug
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    # create console handler and set level to debug
    ch = logging.FileHandler("blobs.log", mode="w")
    ch.setLevel(logging.INFO)
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    #b = Board(40)
    #l = Lobby()
    #u1 = User(1001, None, l)
    #u2 = User(1002, None, l)
    #m = Match([u1, u2], b)
    #b.values[20:30,20:30] = 10
    #b.owner[20:30,20:30] = u1.connection_id
    #b.owner[28:35,30:35] = u2.connection_id
    #b.values[28:35,30:35] = 1

    #t = Turn((20,20), (19,22), u1)
    #m.checkedTurn(t)
    #t = Turn((20,21), (28,30), u1)
    #m.checkedTurn(t)
    #plt.imshow(b.values.astype(np.float64), clim=(0, 10), interpolation="nearest", cmap="hot")
    #plt.show()

    l = Lobby()
    endpoints.serverFromString(reactor, "tcp:1234").listen(l)
    endpoints.serverFromString(reactor, "tcp:9001").listen(SpectatorFactory(l))
    reactor.run()




