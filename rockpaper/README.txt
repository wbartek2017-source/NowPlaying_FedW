ROCKPAPER - MOTHERBOARD now-playing wallpaper for GNOME

Install
  sudo apt install playerctl python3-pil      (or your distro's equivalent)
  mkdir -p ~/.local/share/rockpaper
  cp -r rockpaper.py assets ~/.local/share/rockpaper/
  cp rockpaper.desktop ~/.config/autostart/
  python3 ~/.local/share/rockpaper/rockpaper.py &      # start now

Test without touching your wallpaper
  python3 rockpaper.py --demo      -> writes demo.png

Config: edit the block at the top of rockpaper.py
  SCREEN   your monitor resolution
  BG_COLOR theme colour (default 25C253 green, same as the theme's cfg)
  MODE     "fit" (crisp 4x, textured surround) or "cover"
  REFRESH  seconds between progress-bar redraws (0 = only on track/state change)

Fonts: the theme's Terminus fonts are Rockbox-only, so the script looks for a
Terminus TTF (system fonts, or drop one in assets/fonts/) and falls back to
DejaVu Sans Mono. Terminus gives the most authentic look.

Credit: MOTHERBOARD theme by Monica G., CC-BY-SA 3.0 (artwork in assets/).
Code derived from her theme layout; share under the same licence.
