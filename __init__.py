# Copyright (c) 2018 fieldOfView
# The ZOffsetPlugin is released under the terms of the AGPLv3 or higher.

from . import ZOffsetPlugin
from UM.i18n import i18nCatalog
i18n_catalog = i18nCatalog("ZOffsetPlugin")

def getMetaData():
    return {}

def register(app):
    return {"extension": ZOffsetPlugin.ZOffsetPlugin()}
