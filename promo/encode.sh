#!/bin/bash
# 把 promo/frames 里的逐帧图 + audio.wav 合成成片。
# 用法：bash promo/encode.sh
set -e
cd "$(dirname "$0")/.."

OUT_DIR=promo/out
mkdir -p "$OUT_DIR"
MP4="$OUT_DIR/社畜人设卡_宣传片_1080x1920.mp4"

# JPEG 帧是 full range，必须先转成标准 BT.709 limited range，
# 否则部分播放器会把奶油底渲染成灰白。
ffmpeg -y -hide_banner -loglevel warning \
  -framerate 30 -i promo/frames/f%05d.jpg \
  -i promo/audio.wav \
  -vf "scale=in_range=full:out_range=tv,format=yuv420p" \
  -c:v libx264 -preset slow -crf 15 -profile:v high -level 4.1 \
  -color_range tv -colorspace bt709 -color_primaries bt709 -color_trc bt709 \
  -x264-params "keyint=60:min-keyint=30:scenecut=0:aq-mode=3" \
  -movflags +faststart \
  -c:a aac -b:a 192k -ar 48000 \
  -shortest \
  "$MP4"

# 封面：核价那一帧
ffmpeg -y -hide_banner -loglevel warning \
  -i "$MP4" -ss 17.60 -frames:v 1 -update 1 -q:v 2 \
  "$OUT_DIR/封面_cover.jpg"

ls -lh "$OUT_DIR"
/opt/homebrew/bin/ffprobe -v error -show_entries stream=codec_name,width,height,pix_fmt,color_range -of default=noprint_wrappers=1 "$MP4"
