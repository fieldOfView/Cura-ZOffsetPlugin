# Copyright (c) 2018 fieldOfView
# The ZOffsetPlugin is released under the terms of the AGPLv3 or higher.

import os, json

from UM.Extension import Extension
from UM.Application import Application
from UM.Settings.SettingDefinition import SettingDefinition
from UM.Settings.DefinitionContainer import DefinitionContainer
from UM.Settings.ContainerRegistry import ContainerRegistry
from UM.Logger import Logger

from UM.i18n import i18nCatalog
i18n_catalog = i18nCatalog("ZOffsetPlugin")

class ZOffsetPlugin(Extension):
    def __init__(self):
        super().__init__()

        self._application = Application.getInstance()

        self._i18n_catalog = None
        self._setting_key = "adhesion_z_offset"
        self._setting_dict = {
            "label": "Z Offset",
            "description": "An additional distance between the nozzle and the build platform.",
            "type": "float",
            "unit": "mm",
            "default_value": 0,
            "minimum_value": "-layer_height_0",
            "maximum_value_warning": "layer_height_0",
            "settable_per_mesh": False,
            "settable_per_extruder": False,
            "settable_per_meshgroup": False
        }

        ContainerRegistry.getInstance().containerLoadComplete.connect(self._onContainerLoadComplete)

        self._application.globalContainerStackChanged.connect(self._onGlobalContainerStackChanged)
        self._onGlobalContainerStackChanged()

        self._application.getOutputDeviceManager().writeStarted.connect(self._filterGcode)


    def _onContainerLoadComplete(self, container_id):
        container = ContainerRegistry.getInstance().findContainers(id = container_id)[0]
        if not isinstance(container, DefinitionContainer):
            return

        platform_adhesion_category = container.findDefinitions(key="platform_adhesion")
        zoffset_setting = container.findDefinitions(key=self._setting_key)
        if platform_adhesion_category and not zoffset_setting:
            # this machine doesn't have a zoffset setting yet
            platform_adhesion_category = platform_adhesion_category[0]
            zoffset_definition = SettingDefinition(self._setting_key, container, platform_adhesion_category, self._i18n_catalog)
            zoffset_definition.deserialize(self._setting_dict)

            platform_adhesion_category._children.append(zoffset_definition) # this is naughty, but the alternative is to serialise and deserialise the whole thing

            container.addDefinition(zoffset_definition)


    def _onGlobalContainerStackChanged(self):
        self._global_container_stack = self._application.getGlobalContainerStack()


    def _filterGcode(self, output_device):
        scene = self._application.getController().getScene()

        # get setting from Cura
        z_offset_value = self._global_container_stack.getProperty(self._setting_key, "value")
        if z_offset_value == 0:
            return

        if hasattr(scene, "gcode_dict"):
            gcode_dict = getattr(scene, "gcode_dict")
            dict_changed = False

            for plate_id in gcode_dict:
                gcode_list = gcode_dict[plate_id]
                if ";ZOFFSETPROCESSED" not in gcode_list[0]:
                    gcode_list[1] += "G0 Z%f ;go to Z Offset\nG92 Z0 ;Z Offset is now considered 0\n" % z_offset_value

                    gcode_list[0] += ";ZOFFSETPROCESSED\n"
                    gcode_dict[plate_id] = gcode_list
                    dict_changed = True

            if dict_changed:
                setattr(scene, "gcode_list", gcode_list)
            else:
                Logger.log("e", "Already post processed")
