# ZOffsetPlugin

This plugin adds a setting named "Z Offset" to the Build Plate Adhesion settings in the Custom print setup of Cura. Entering a positive value to in field will result in the head printing everything that amount further away from the build plate.

The Z Offset setting can be found in the Custom print setup by using the Search field on top of the settings. If you want to make the setting permanently visible in the sidebar, right click and select "Keep this setting visible".

The plugin works by inserting a snippet of gcode before the first layer. If the Z Offset value is set to 0.1, the gcode snippet may look like this:
```
...
;Put printing message on LCD screen
M117 Printing...
;LAYER_COUNT:399
G0 Z0.100000 ;go to Z Offset
G92 Z0 ;Z Offset is now considered 0
;LAYER:0
M107
...
```