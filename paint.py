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
    def __init__(self, size, owners, values, scene: QGraphicsScene):
        self.rectItems = []
        self.pixmap = QPixmap(QSize(820,820))
        self.painter = QPainter(self.pixmap)
        self.scene = scene
        pen = QPen()
        pen.setStyle(Qt.NoPen)
        for index in range(size**2):
            item = QGraphicsRectItem()
            item.setRect(int(index/size), int(index%size), 0.9, 0.9)
            k = colors[own.index(owner)]
            color = QtGui.QColor(k[0], k[1], k[2], 255./np.amax(values.flat)*value if owner >= 1000 else 255)
            brush = QBrush(color)
            item.setBrush(brush)
            item.setPen(pen)
            scene.addItem(item)
            self.rectItems.append(item)
            
    def outputPng(self):
        view = scene.views()[0]
        self.pixmap.fill(Qt.white)
        self.painter.setBackground(Qt.white)
        self.painter.setRenderHints(QtGui.QPainter.HighQualityAntialiasing)
        scene.render(self.painter, QRectF(10,10,800,800), QRectF(0,0,size,size))
        self.pixmap.save("/var/www/html/state.png")
        
    def outputScorePage(self, owners, values, names, ids):
        with open('/var/www/html/index.html', 'w') as f:
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


    def update(self, owners, values):
        own = list(np.unique(owners))
        for index, (owner, value) in enumerate(zip(owners.flat, values.flat)):
            color = QtGui.QColor(*colors[own.index(owner)], value*8 if owner >= 1000 else 255)
            brush = QBrush(color)
            item.setBrush(brush)

class NetworkInterface(QtCore.QObject):
    dataReceived = pyqtSignal(np.ndarray, np.ndarray)

    def __init__(self):
        HOST = 'localhost'
        PORT = 9001
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((HOST, PORT))
        self.sock.send('{"type": "stream_game"}')

    def run(self):
        while True:
            self.loop()

    def loop(self):
        buf = b""
        while len(buf) == 0 or buf[-1] != ord('}'):
            data = self.sock.recv(1024)
            if len(data) == 0:
                print("Connection closed")
                exit(1)
            buf += data
        data = json.loads(data.decode("utf8"))
        values, owner = blobs.MatchHistory.decodeState(data["board_size"], data["turn"])
        self.dataReceived.emit(values, owner)

if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    w = QtWidgets.QWidget()
    v = QGraphicsView()

    iface = NetworkInterface()

    scene = QGraphicsScene(v)
    v.setRenderHints(QtGui.QPainter.HighQualityAntialiasing)
    v.setScene(scene)

    size = 100
    v.fitInView(0, 0, size, size)
    owners = np.random.randint(999, 1003, (size, size))
    values = np.random.poisson(3, (size, size))
    names = ["1000","1001","1002","1003"]
    ids = [1000, 1001, 1002, 1003]
    field = GameField(size,
                      owners,
                      values,
                      scene)
    field.outputPng()
    field.outputScorePage(owners,values, names, ids)
    iface.dataReceived.connect(field.update)

    w.setLayout(QtWidgets.QHBoxLayout())
    w.resize(800, 600)
    w.layout().addWidget(v)
    w.show()
    
    app.exec_()
