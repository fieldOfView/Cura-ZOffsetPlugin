# Copyright (c) 2020 Aldo Hoeben / fieldOfView
# The ZOffsetPlugin is released under the terms of the AGPLv3 or higher.

from . import ZOffsetPlugin


def getMetaData():
    return {}

def register(app):
    return {"extension": ZOffsetPlugin.ZOffsetPlugin()}
