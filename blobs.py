#!/usr/bin/env python
# -*- coding: UTF-8 -*-
import sys

import matplotlib.pyplot as plt
import numpy as np

NO_OWNER = 0
FOOD_OWNER = 1
MIN_PID = 1000

class User:
    def __init__(self, userid, connection):
        self.connection = connection
        self.userid = userid

    @staticmethod
    def login(username, password):
        return User()

    @staticmethod
    def register(username, password):
        pass

    def sendMessage(self, message):
        pass

    def receiveTurnCommand(self):
        pass

    def askTurn(self, match):
        self.sendMessage(match.stateString())
        return self.receiveTurnCommand()

class Lobby:
    def __init__(self):
        self.users = []

    def joinUser(self, user: User):
        self.users.append(user)

    def _match(self):
        pass

    def waitForPlayers(self):
        pass

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
            if c == full:
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

        assert self.board.playerContiguous(turn.player)

    def checkTurn(self, turn: Turn):
        if self.board.owner[turn.source] != turn.player.playerid:
            return False
        if (0 > turn.dest[0] >= self.board.size) or (0 > turn.dest[1] >= self.board.size):
            return False
        adj = self.board.adjacent(turn.source)
        if not (self.board.owner[adj] == turn.player.playerid).any():
            return False

        destOwner = self.board.owner[turn.dest]
        isEnemy = destOwner > MIN_PID and destOwner != turn.player.playerid
        if isEnemy and self.board.values[turn.dest] > self.board.values[turn.source] + 1:
            return False

        if len(self.splitCreatedByTurn(turn.source, turn.player.playerid)) > 0:
            return False

    def turn(self):
        for user in self.users:
            turn = user.askTurn(self)
            if self.checkTurn(turn):
                self.execTurn(turn)
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
        return np.array([(d[0], d[1]+1), (d[0], d[1]-1), (d[0]+1, d[1]), (d[0]-1, d[1])])

    def connected(self, pos):
        owner = self.owner[pos]
        component = np.zeros_like(self.owner, dtype=np.bool)
        component[pos] = True
        interesting = self.owner == owner
        value = -1
        while True:
            previous_value = value
            value = np.sum(component)
            if previous_value == value:
                break
            component[:,:-1] |= interesting[:,:-1] & component[:,1:]
            component[:,1:] |= interesting[:,1:] & component[:,:-1]
            component[:-1,:] |= interesting[:-1,:] & component[1:,:]
            component[1:,:] |= interesting[1:,:] & component[:-1,:]
        return np.where(component)

    def playerContiguous(self, player: User):
        return self.ownedByPlayer(player) == self.connected(np.where(self.owner == player)[0])

    def ownedByPlayer(self, player: User):
        return np.where(self.owner == player.userid)

if __name__ == '__main__':
    b = Board(40)
    u1 = User(1001, None)
    u2 = User(1002, None)
    b.values[20:30,20:30] = 1
    b.owner[20:30,20:30] = u1.userid
    t = Turn((20,22), (19,22))
    m = Match([u1, u2], b)
    m.execTurn(t)
    plt.imshow(b.owner.astype(np.float64)/10, clim=(0, 1005), interpolation="nearest", cmap="hot")
    plt.show()

    #l = Lobby()
    #l.waitForPlayers()



