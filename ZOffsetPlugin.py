# Copyright (c) 2022 Aldo Hoeben / fieldOfView
# The ZOffsetPlugin is released under the terms of the AGPLv3 or higher.

import re
import json
import os.path
import collections

from UM.Extension import Extension
from UM.Application import Application
from UM.Settings.SettingDefinition import SettingDefinition
from UM.Settings.DefinitionContainer import DefinitionContainer
from UM.Settings.ContainerRegistry import ContainerRegistry
from UM.Logger import Logger
from UM.Resources import Resources
from UM.i18n import i18nCatalog

from typing import List, Any, Dict


class ZOffsetPlugin(Extension):
    def __init__(self):
        super().__init__()

        self._application = Application.getInstance()
        plugin_folder = os.path.abspath(os.path.dirname(__file__))
        Resources.addSearchPath(plugin_folder)  # Plugin translation file import
        self._i18n_catalog = i18nCatalog("zoffsetplugin")

        self._settings_dict = {}  # type: Dict[str, Any]
        self._expanded_categories = []  # type: List[str]  # temporary list used while creating nested settings

        settings_definition_path = os.path.join(plugin_folder, "zoffset.def.json")

        try:
            with open(settings_definition_path, "r", encoding="utf-8") as f:
                self._settings_dict = json.load(
                    f, object_pairs_hook=collections.OrderedDict
                )["settings"]
        except Exception:
            Logger.logException("e", "Could not load z offset settings definition")
            return

        if self._i18n_catalog.hasTranslationLoaded():
            # Apply translation to loaded dict, because the setting definition model
            # does not deal well with translations from plugins
            self._translateSettings(self._settings_dict)

        ContainerRegistry.getInstance().containerLoadComplete.connect(self._onContainerLoadComplete)
        self._application.getOutputDeviceManager().writeStarted.connect(self._filterGcode)

    def _translateSettings(self, json_root: Dict[str, Any]) -> None:
        for key in json_root:
            json_root[key]["label"] = self._i18n_catalog.i18nc(
                key + " label", json_root[key]["label"]
            )
            json_root[key]["description"] = self._i18n_catalog.i18nc(
                key + " description", json_root[key]["description"]
            )

            # TODO: handle options from comboboxes (not that this plugin has any)

            if "children" in json_root[key]:
                self._translateSettings(json_root[key]["children"])

    def _onContainerLoadComplete(self, container_id: str) -> None:
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

        try:
            adhesion_category = container.findDefinitions(key="platform_adhesion")[0]
        except IndexError:
            Logger.log("e", "Could not find parent category setting to add settings to")
            return

        for setting_key in self._settings_dict.keys():
            setting_definition = SettingDefinition(
                setting_key, container, adhesion_category, self._i18n_catalog
            )
            setting_definition.deserialize(self._settings_dict[setting_key])

            # add the setting to the already existing platform_adhesion settingdefinition
            # private member access is naughty, but the alternative is to serialise, nix and deserialise the whole thing,
            # which breaks stuff
            adhesion_category._children.append(setting_definition)
            container._definition_cache[setting_key] = setting_definition

            self._expanded_categories = self._application.expandedCategories.copy()
            self._updateAddedChildren(container, setting_definition)
            self._application.setExpandedCategories(self._expanded_categories)
            self._expanded_categories = []  # type: List[str]
            container._updateRelations(setting_definition)

    def _updateAddedChildren(self, container: DefinitionContainer, setting_definition: SettingDefinition) -> None:
        children = setting_definition.children
        if not children or not setting_definition.parent:
            return

        # make sure this setting is expanded so its children show up in setting views
        if setting_definition.parent.key in self._expanded_categories:
            self._expanded_categories.append(setting_definition.key)

        for child in children:
            container._definition_cache[child.key] = child
            self._updateAddedChildren(container, child)

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
