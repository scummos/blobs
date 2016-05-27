#!/usr/bin/env python
# -*- coding: UTF-8 -*-
import sys

import numpy as np

from PyQt5.QtWidgets import QGraphicsScene, QGraphicsView, QGraphicsRectItem, QGraphicsScene
from PyQt5.QtGui import QBrush, QColor, QPen
from PyQt5.QtCore import Qt
from PyQt5 import QtWidgets, QtCore, QtGui

colors = [(0, 0, 0), (255, 0, 0), (100, 255, 100), (100, 100, 255), (255, 0, 177)]

class GameField:
    def __init__(self, size, owners, values, scene: QGraphicsScene):
        self.rectItems = []
        pen = QPen()
        pen.setStyle(Qt.NoPen)
        own = list(np.unique(owners))
        for index, (owner, value) in enumerate(zip(owners.flat, values.flat)):
            item = QGraphicsRectItem()
            item.setRect(int(index/size), int(index%size), 0.9, 0.9)
            color = QtGui.QColor(*colors[own.index(owner)], value*8 if owner >= 1000 else 255)
            brush = QBrush(color)
            item.setBrush(brush)
            item.setPen(pen)
            scene.addItem(item)
            self.rectItems.append(item)

if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    w = QtWidgets.QWidget()
    v = QGraphicsView()

    scene = QGraphicsScene(v)
    v.setRenderHints(QtGui.QPainter.HighQualityAntialiasing)
    v.setScene(scene)

    size = 100
    v.fitInView(0, 0, size, size)
    field = GameField(size,
                      np.random.randint(999, 1003, (size, size)),
                      np.random.poisson(3, (size, size)),
                      scene)

    w.setLayout(QtWidgets.QHBoxLayout())
    w.resize(800, 600)
    w.layout().addWidget(v)
    w.show()
    app.exec_()
