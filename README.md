A now playing background for Fedora Workstation (GNOME) based on the rockbox theme MOTHERBOARD by mgingras-png

## Dependancies

 - playerctl
 - python3
 - pillow
 - Jetbrains Mono font.

## Installation and usage

To test without touching your wallpaper
  python3 rockpaper.py --demo      -> writes demo.png

Config: edit the block at the top of rockpaper.py
  - SCREEN   your monitor resolution
  - BG_COLOR theme colour (default 25C253 green, same as the theme's cfg)
  - IDLE_IMAGE - The image you want as your background while no media is playing
  - MODE     "fit" (crisp 4x, textured surround) or "cover"
  - REFRESH  seconds between progress-bar redraws (0 = only on track/state change)
  - 15s is lowest i can go before it starts flashing, due to limitiations with GNOME

Credit: MOTHERBOARD theme by Monica G.
* Visual assets and bitmap layouts were adapted from the [MOTHERBOARD](https://github.com/mgingras-png/MOTHERBOARD) theme by [mgingras-png](https://github.com/mgingras-png). * The original assets are dedicated to the public domain under the **[Creative Commons Zero v1.0 Universal (CC0 1.0)](https://creativecommons.org)** license. I appreciate the author's decision to share their work freely!

