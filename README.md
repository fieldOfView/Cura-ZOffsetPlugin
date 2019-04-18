# ZOffsetPlugin

This plugin adds a setting named `Z Offset` to the Build Plate Adhesion settings in the Custom print setup of Cura. Entering a positive value to in field will result in the head printing everything that amount further away from the build plate.

The Z Offset setting can be found in the Custom print setup by using the Search field on top of the settings. If you want to make the setting permanently visible in the sidebar, right click and select "Keep this setting visible".

## Installation

### Windows
Clone this repository into `C:\Users\USERNAME\AppData\Roaming\cura\4.0\plugins`

## How it works

The plugin adjusts the first move on the Z axis in the first layer by adding the Z offset value, and then instructs the printer to consider this the original first layer height. For example, layer 1 of a print with a first layer height of 0.25, and a Z Offset value of 0.05 may look like this:
```
...
;LAYER:0
M107
G0 F4320 X135.625 Y125.625 Z0.3 ;adjusted by z offset
G92 Z0.25 ;consider this the original z before offset
;TYPE:WALL-INNER
...
```
