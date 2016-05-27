#!/usr/bin/env python
import socket
# -*- coding: UTF-8 -*-
import sys

import numpy as np

from PyQt5.QtWidgets import QGraphicsScene, QGraphicsView, QGraphicsRectItem, QGraphicsScene
from PyQt5.QtGui import QBrush, QColor, QPen, QPixmap, QGuiApplication, QPainter
from PyQt5.QtCore import Qt, QSize, QRectF, pyqtSignal, pyqtSlot
from PyQt5 import QtWidgets, QtCore, QtGui

import json
import blobs

colors = [(0, 0, 0), (255, 0, 0), (100, 255, 100), (100, 100, 255), (255, 0, 177)]

class GameField:
    def __init__(self, size, scene: QGraphicsScene):
        self.rectItems = []
        self.pixmap = QPixmap(QSize(820,820))
        self.painter = QPainter(self.pixmap)
        self.scene = scene
        pen = QPen()
        pen.setStyle(Qt.NoPen)
        for index in range(size**2):
            item = QGraphicsRectItem()
            item.setRect(int(index/size), int(index%size), 0.9, 0.9)
            item.setPen(pen)
            scene.addItem(item)
            self.rectItems.append(item)

    @pyqtSlot(int, np.ndarray, np.ndarray)
    def update(self, size, owners, values):
        print("update called")
        own = list(np.unique(owners))[1:]
        print(owners, own)
        noBrush = QBrush(Qt.NoBrush)
        for index, owner, value in zip(range(size**2), owners.flat, values.flat):
            if owner == 0:
                brush = noBrush
            else:
                k = colors[own.index(owner)]
                color = QtGui.QColor(k[0], k[1], k[2], int(255./np.max(values)*value) if owner >= 1000 else 255)
                brush = QBrush(color)
            item = self.rectItems[index]
            item.setBrush(brush)
        self.scene.update(self.scene.sceneRect())

    def outputPng(self):
        view = scene.views()[0]
        self.pixmap.fill(Qt.white)
        self.painter.setBackground(Qt.white)
        self.painter.setRenderHints(QtGui.QPainter.HighQualityAntialiasing)
        scene.render(self.painter, QRectF(10,10,800,800), QRectF(0,0,size,size))
        self.pixmap.save("out/state.png")

    def outputScorePage(self, owners, values, names, ids):
        with open('out/index.html', 'w') as f:
            f.write("""<!DOCTYPE HTML PUBLIC \"-//W3C//DTD HTML 4.01//EN\" \"http://www.w3.org/TR/html4/strict.dtd\">\n
                <html>\n
                \t<head>\n
                \t\t<title>GPN16: Blobs</title>\n
                \t\t<style>\n
                \t\t\ttable\n
                \t\t\t{\n
                \t\t\t\tborder-collapse:collapse;\n
                \t\t\t\twidth:100%;\n
                \t\t\t}\n
                \t\t\tth,td\n
                \t\t\t{\n
                \t\t\t\ttext-align:left;\n
                \t\t\t\tpadding:8px;\n
                \t\t\t}\n
                \t\t\ttr:nth-child(even)\n
                \t\t\t{\n
                \t\t\t\tbackground-color:#f2f2f2;\n
                \t\t\t}\n
                \t\t\tth\n
                \t\t\t{\n
                \t\t\t\tbackground-color:#600000;\n
                \t\t\t\tcolor:white\n
                \t\t\t}\n
                \t\t</style>\n
                \t</head>\n
                \t<body>\n
                \t\t<h2><a href=\"http://www.gulas.ch\">GPN16</a>: <a href=\"http://www.github.com/scummos/blobs\">Blobs</a>$ Lobby</h2>\n
                \t\t<center>\n
                \t\t\t<img src=logo.svg /><br />\n
                \t\t\t<img src=state.png /><br />\n
                \t\t</center>\n
                \t\t<table>\n
                \t\t\t<tr>\n
                \t\t\t\t<th>Rank</th>\n
                \t\t\t\t<th>Bot name</th>\n
                \t\t\t\t<th>Score</th>\n
                \t\t\t</tr>\n""");
            #TODO: output ramsh here
            f.write("""\t\t</table>\n
                \t</body>\n
                </html>\n""")
            f.close()


class NetworkInterface(QtCore.QObject):
    dataReceived = pyqtSignal(int, np.ndarray, np.ndarray)

    def __init__(self):
        QtCore.QObject.__init__(self)
        HOST = 'localhost'
        PORT = 9001
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((HOST, PORT))
        self.sock.send(b'{"type": "stream_game"}')

    @pyqtSlot()
    def run(self):
        for l in self.sock.makefile("rb"):
            print(l)
            self.loop(l)

    def loop(self, data):
        data = json.loads(data.decode("utf8"))
        if data["type"] == "stream_turn":
            values, owners = blobs.MatchHistory.decodeState(data["board_size"], data["turn"])
            print("Got data packet, emitting signal")
            self.dataReceived.emit(data["board_size"], owners, values)

if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    w = QtWidgets.QWidget()
    v = QGraphicsView()

    iface = NetworkInterface()
    t = QtCore.QThread()
    iface.moveToThread(t)
    t.start()
    QtCore.QMetaObject.invokeMethod(iface, "run", Qt.QueuedConnection)

    scene = QGraphicsScene(v)
    v.setRenderHints(QtGui.QPainter.HighQualityAntialiasing)
    v.setScene(scene)

    size = blobs.BOARD_SIZE
    v.fitInView(0, 0, size, size)
    field = GameField(size, scene)
    iface.dataReceived.connect(field.update, Qt.QueuedConnection)

    w.setLayout(QtWidgets.QHBoxLayout())
    w.resize(800, 600)
    w.layout().addWidget(v)
    w.setWindowFlags(Qt.Dialog)
    w.show()
    
    app.exec_()
