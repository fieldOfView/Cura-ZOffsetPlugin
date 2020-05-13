# Copyright (c) 2018 fieldOfView
# The ZOffsetPlugin is released under the terms of the AGPLv3 or higher.

import re
from collections import OrderedDict

from UM.Extension import Extension
from UM.Application import Application
from UM.Settings.SettingDefinition import SettingDefinition
from UM.Settings.DefinitionContainer import DefinitionContainer
from UM.Settings.ContainerRegistry import ContainerRegistry
from UM.Logger import Logger

class ZOffsetPlugin(Extension):
    def __init__(self):
        super().__init__()

        self._application = Application.getInstance()

        self._i18n_catalog = None

        self._settings_dict = OrderedDict()
        self._settings_dict["adhesion_z_offset"] = {
            "label": "Z Offset",
            "description": "An additional offset of the build platform in relation to the nozzle. A negative value 'squishes' the print into the buildplate, a positive value will result in a bigger distance between the buildplate and the print.",
            "type": "float",
            "unit": "mm",
            "default_value": 0,
            "minimum_value": "-(layer_height_0 + 0.15)",
            "maximum_value_warning": "layer_height_0",
            "resolve": "extruderValue(adhesion_extruder_nr, 'adhesion_z_offset') if resolveOrValue('adhesion_type') != 'none' else min(extruderValues('adhesion_z_offset'))",
            "settable_per_mesh": False,
            "settable_per_extruder": False,
            "settable_per_meshgroup": False
        }
        self._settings_dict["adhesion_z_offset_extensive_processing"] = {
            "label": "Extensive Z Offset Processing",
            "description": "Apply the Z Offset throughout the Gcode file instead of affecting the coordinate system. Turning this option on will increae the processing time so it is recommended to leave it off.",
            "type": "bool",
            "default_value": False,
            "value": "True if machine_gcode_flavor == \"Griffin\" else False",
            "settable_per_mesh": False,
            "settable_per_extruder": False,
            "settable_per_meshgroup": False
        }

        ContainerRegistry.getInstance().containerLoadComplete.connect(self._onContainerLoadComplete)

        self._application.getOutputDeviceManager().writeStarted.connect(self._filterGcode)


    def _onContainerLoadComplete(self, container_id):
        if not ContainerRegistry.getInstance().isLoaded(container_id):
            # skip containers that could not be loaded, or subsequent findContainers() will cause an infinite loop
            return

        try:
            container = ContainerRegistry.getInstance().findContainers(id = container_id)[0]
        except IndexError:
            # the container no longer exists
            return

        if not isinstance(container, DefinitionContainer):
            # skip containers that are not definitions
            return
        if container.getMetaDataEntry("type") == "extruder":
            # skip extruder definitions
            return

        platform_adhesion_category = container.findDefinitions(key="platform_adhesion")
        zoffset_setting = container.findDefinitions(key=list(self._settings_dict.keys())[0])
        if platform_adhesion_category and not zoffset_setting:
            # this machine doesn't have a zoffset setting yet
            platform_adhesion_category = platform_adhesion_category[0]
            for setting_key, setting_dict in self._settings_dict.items():

                definition = SettingDefinition(setting_key, container, platform_adhesion_category, self._i18n_catalog)
                definition.deserialize(setting_dict)

                # add the setting to the already existing platform adhesion settingdefinition
                # private member access is naughty, but the alternative is to serialise, nix and deserialise the whole thing,
                # which breaks stuff
                platform_adhesion_category._children.append(definition)
                container._definition_cache[setting_key] = definition
                container._updateRelations(definition)


    def _filterGcode(self, output_device):
        scene = self._application.getController().getScene()

        global_container_stack = self._application.getGlobalContainerStack()
        if not global_container_stack:
            return

        # get setting from Cura
        z_offset_value = global_container_stack.getProperty("adhesion_z_offset", "value")
        if z_offset_value == 0:
            return

        use_extensive_offset = global_container_stack.getProperty("adhesion_z_offset_extensive_processing", "value")

        gcode_dict = getattr(scene, "gcode_dict", {})
        if not gcode_dict: # this also checks for an empty dict
            Logger.log("w", "Scene has no gcode to process")
            return

        dict_changed = False
        z_move_regex = re.compile(r"(G[01]\s.*Z)([-\+]?\d*\.?\d*)(.*)")

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

                relative_mode = False

                if not use_extensive_offset:
                    # find the first vertical G0/G1, adjust it and reset the internal coordinate to apply offset to all subsequent moves
                    lines = gcode_list[2].split("\n")
                    for (line_nr, line) in enumerate(lines):
                        if line.startswith("G91"):
                            relative_mode = True
                            continue
                        elif line.startswith("G90"):
                            relative_mode = False
                            continue
                        if relative_mode:
                            continue

                        result = z_move_regex.fullmatch(line)
                        if result:
                            try:
                                adjusted_z = round(float(result.group(2)) + z_offset_value, 5)
                            except ValueError:
                                Logger.log("e", "Unable to process Z coordinate in line %s", line)
                                continue
                            lines[line_nr] = result.group(1) + str(adjusted_z) + result.group(3) + " ;adjusted by z offset"
                            lines[line_nr] += "\n" + "G92 Z" + result.group(2) + " ;consider this the original z before offset"
                            gcode_list[2] = "\n".join(lines)
                            break

                else:
                    # process all G0/G1 lines and adjust the Z value
                    for n in range(2, len(gcode_list)): # all gcode lists / layers, start at layer 1 = gcode list 2
                        lines = gcode_list[n].split("\n")
                        for (line_nr, line) in enumerate(lines):
                            if line.startswith("G91"):
                                relative_mode = True
                                continue
                            elif line.startswith("G90"):
                                relative_mode = False
                                continue
                            if relative_mode:
                                continue

                            result = z_move_regex.fullmatch(line)
                            if result:
                                try:
                                    adjusted_z = round(float(result.group(2)) + z_offset_value, 5)
                                except ValueError:
                                    Logger.log("e", "Unable to process Z coordinate in line %s", line)
                                    continue
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
