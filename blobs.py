#!/usr/bin/env python
# -*- coding: UTF-8 -*-
import sys

import matplotlib.pyplot as plt
import numpy as np

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
    def __init__(self, source, dest):
        self.dest = dest
        self.source = source

class Match:
    def __init__(self, users, board):
        self.board = board
        self.users = users

    def execTurn(self, turn):
        pass

    def turn(self):
        for user in self.users:
            turn = user.askTurn(self)
            self.execTurn(turn)
            self.checkConnectivity(turn, user)
            self.checkMatchFinished()

    def checkConnectivity(self, turn, user):
        pass

    def checkMatchFinished(self):
        pass

class Board:
    def __init__(self, size):
        self.values = np.zeros((size, size), dtype=np.uint16)
        self.owner = np.zeros_like(self.values)

    def _connected(self, pos):
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

    def _playerContiguous(self, player: User):
        return self._ownedByPlayer(player) == self._connected(np.where(self.owner == player)[0])

    def _ownedByPlayer(self, player: User):
        return np.where(self.owner == player.userid)

if __name__ == '__main__':
    b = Board(40)
    b.values[20:30,20:30] = 7
    b.owner[20:30,20:30] = 5
    b.owner[20:32,27] = 0
    connected = b._connected((22,22))
    b.owner[connected] = 10
    plt.imshow(b.owner.astype(np.float64)/10, clim=(0, 10), interpolation="nearest", cmap="hot")
    plt.show()

    #l = Lobby()
    #l.waitForPlayers()



