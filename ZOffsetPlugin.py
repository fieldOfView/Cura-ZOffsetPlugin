# Copyright (c) 2018 fieldOfView
# The ZOffsetPlugin is released under the terms of the AGPLv3 or higher.

import os, json, re

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
            "settable_per_extruder": True,
            "settable_per_meshgroup": False
        }

        ContainerRegistry.getInstance().containerLoadComplete.connect(self._onContainerLoadComplete)

        self._application.getOutputDeviceManager().writeStarted.connect(self._filterGcode)


    def _onContainerLoadComplete(self, container_id):
        container = ContainerRegistry.getInstance().findContainers(id = container_id)[0]
        if not isinstance(container, DefinitionContainer):
            # skip containers that are not definitions
            return
        if container.getMetaDataEntry("type") == "extruder":
            # skip extruder definitions
            return

        platform_adhesion_category = container.findDefinitions(key="platform_adhesion")
        zoffset_setting = container.findDefinitions(key=self._setting_key)
        if platform_adhesion_category and not zoffset_setting:
            # this machine doesn't have a zoffset setting yet
            platform_adhesion_category = platform_adhesion_category[0]
            zoffset_definition = SettingDefinition(self._setting_key, container, platform_adhesion_category, self._i18n_catalog)
            zoffset_definition.deserialize(self._setting_dict)

            # add the setting to the already existing platform adhesion settingdefinition
            # private member access is naughty, but the alternative is to serialise, nix and deserialise the whole thing,
            # which breaks stuff
            platform_adhesion_category._children.append(zoffset_definition)
            container._definition_cache[self._setting_key] = zoffset_definition
            container._updateRelations(zoffset_definition)


    def _filterGcode(self, output_device):
        scene = self._application.getController().getScene()

        global_container_stack = self._application.getGlobalContainerStack()
        initial_extruder_stack = self._application.getExtruderManager().getUsedExtruderStacks()[0]
        if not global_container_stack or not initial_extruder_stack:
            return

        # get setting from Cura
        z_offset_value = initial_extruder_stack.getProperty(self._setting_key, "value")
        if z_offset_value == 0:
            return

        # the default offset method does not work on Ultimaker S5 and Ultimaker 3 models, which use the "Griffin" gcode flavor
        gcode_flavor = global_container_stack.getProperty("machine_gcode_flavor", "value")
        use_extensive_offset = True if gcode_flavor == "Griffin" else False

        gcode_dict = getattr(scene, "gcode_dict", {})
        if not gcode_dict: # this also checks for an empty dict
            Logger.log("w", "Scene has no gcode to process")
            return

        dict_changed = False
        z_move_regex = re.compile("(G[0|1]\s.*Z)(\d*\.?\d*)(.*)")

        for plate_id in gcode_dict:
            gcode_list = gcode_dict[plate_id]
            if len(gcode_list) < 2:
                Logger.log("w", "Plate %s does not contain any layers", plate_id)
                continue

            if ";ZOFFSETPROCESSED\n" not in gcode_list[0]:
                # look for the first line that contains a G0 or G1 move on the Z axis
                # gcode_list[2] is the first layer, after the preamble and the start gcode

                if ";LAYER:0\n" in gcode_list[1]:
                    # layer 0 somehow got appended to the start gcode chunk
                    chunks = gcode_list[1].split(";LAYER:0\n")
                    gcode_list[1] = chunks[0]
                    gcode_list.insert(2, ";LAYER:0\n" + chunks[1])

                if not use_extensive_offset:
                    # find the first vertical G0/G1, adjust it and reset the internal coordinate to apply offset to all subsequent moves
                    lines = gcode_list[2].split("\n")
                    for (line_nr, line) in enumerate(lines):
                        result = z_move_regex.fullmatch(line)
                        if result:
                            adjusted_z = round(float(result.group(2)) + z_offset_value, 5)
                            lines[line_nr] = result.group(1) + str(adjusted_z) + result.group(3) + " ;adjusted by z offset"
                            lines[line_nr] += "\n" + "G92 Z" + result.group(2) + " ;consider this the original z before offset"
                            gcode_list[2] = "\n".join(lines)
                            break

                else:
                    # process all G0/G1 lines and adjust the Z value
                    for n in range(2, len(gcode_list)): # all gcode lists / layers, start at layer 1 = gcode list 2
                        lines = gcode_list[n].split("\n")
                        for (line_nr, line) in enumerate(lines):
                            result = z_move_regex.fullmatch(line)
                            if result:
                                adjusted_z = round(float(result.group(2)) + z_offset_value, 5)
                                lines[line_nr] = result.group(1) + str(adjusted_z) + result.group(3) + " ;adjusted by z offset"
                                gcode_list[n] = "\n".join(lines)

                gcode_list[0] += ";ZOFFSETPROCESSED\n"
                gcode_dict[plate_id] = gcode_list
                dict_changed = True
            else:
                Logger.log("d", "Plate %s has already been processed", plate_id)
                continue

        if dict_changed:
            setattr(scene, "gcode_dict", gcode_dict)