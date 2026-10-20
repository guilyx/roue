#!/bin/bash
# Generates the demo's sample files and wallpaper. Usage: make_samples.sh PICTURES_DIR WALLPAPER_PNG
set -euo pipefail
pics=$1 wallpaper=$2
mkdir -p "$pics"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

convert -size 1600x1200 gradient:'#1d2b64'-'#f8a65f' \
  \( -size 2000x2000 radial-gradient:'#ffd98a'-'#ffd98a00' -geometry -200-240 \) -compose over -composite \
  -fill '#fff6d6' -draw "circle 800,760 800,665" \
  -fill '#4a3460' -draw "polygon 0,1200 0,820 220,700 420,860 640,640 900,880 1120,690 1360,860 1600,720 1600,1200" \
  -fill '#2a1c42' -draw "polygon 0,1200 0,960 300,860 560,980 860,880 1180,1000 1460,900 1600,960 1600,1200" \
  -attenuate 0.2 +noise Gaussian "$tmp/sunset.png"
convert -size 1600x1200 gradient:'#0f766e'-'#a7f3d0' \
  -fill '#fefce8' -draw "rectangle 0,820 1600,1200" -fill '#38bdf8' -draw "polygon 0,820 1600,760 1600,900 0,960" \
  -fill '#fde68a' -draw "circle 1240,300 1240,210" -attenuate 0.2 +noise Gaussian "$tmp/beach.png"
vips copy "$tmp/sunset.png" "$pics/IMG_2041.HEIC[Q=70]"
vips copy "$tmp/beach.png" "$pics/IMG_2047.HEIC[Q=70]"
ffmpeg -v error -y -f lavfi -i "gradients=s=1280x720:speed=0.015:n=4:duration=8:rate=30" \
  -f lavfi -i "sine=frequency=220:duration=8" -shortest -c:v libx264 -pix_fmt yuv420p -b:v 6M \
  -c:a aac "$pics/Screen recording.mov"
printf '# Q3 report\n\nRevenue is **up 12%%**.\n\n- Shipped Roue 0.1\n- 27 presets\n' > "$tmp/notes.md"
pandoc "$tmp/notes.md" -o "$pics/Quarterly report.docx"

convert -size 1280x720 gradient:'#1b1640'-'#0b1020' \
  \( -size 1280x720 xc:none -fill '#33d17a55' -draw "circle 160,560 160,280" \
     -fill '#ed333b44' -draw "circle 1120,140 1120,-120" -fill '#c061cb44' -draw "circle 1050,640 1050,420" \
     -fill '#3584e444' -draw "circle 420,80 420,-140" -blur 0x90 \) -composite "$wallpaper"
