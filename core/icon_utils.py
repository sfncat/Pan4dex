# -*- coding: utf-8 -*-
"""应用图标工具。

统一从单张 icon.png 生成多尺寸 QIcon。
Windows 任务栏/标题栏/Alt-Tab 提取窗口图标时会按目标尺寸取帧，
若 QIcon 只有单个 1024×1024 源，Windows 需做 1024→32 的大缩放，
缩放异常会表现为任务栏图标缺失/变默认。生成 16~256 多尺寸帧可避免该问题。
"""
from __future__ import annotations


def load_app_icon(icon_path: str):
    """从单张 PNG 生成多尺寸 QIcon（16/24/32/48/64/128/256）。

    任一尺寸缩放失败时跳过该尺寸；全部失败则回退为直接加载原图。
    """
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QIcon, QPixmap

    sizes = (16, 24, 32, 48, 64, 128, 256)
    icon = QIcon()
    for s in sizes:
        pm = QPixmap(icon_path)
        if pm.isNull():
            continue
        scaled = pm.scaled(
            s, s,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        icon.addPixmap(scaled)
    if icon.isNull():
        icon = QIcon(icon_path)  # 兜底：直接加载原图
    return icon
