#!/usr/bin/env python
# -*- coding: UTF-8 -*-

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

    def askTurn(self, match: Match):
        self.sendMessage(match.stateString())
        return self.receiveTurnCommand()

class Lobby:
    def __init__(self):
        self.users = []

    def joinUser(self, user: User):
        self.users.append(user)

    def _match(self) -> Match:
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
        pass

    def _ownedByPlayer(self, player):
        pass

if __name__ == '__main__':
    l = Lobby()
    l.waitForPlayers()



