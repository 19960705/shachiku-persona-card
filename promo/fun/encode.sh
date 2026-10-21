#!/bin/bash
# 玩梗版宣传片合成。用法：bash promo/fun/encode.sh
set -e
cd "$(dirname "$0")/../.."

OUT=promo/fun/out
mkdir -p "$OUT"
MP4="$OUT/社畜人设卡_18点59_1080x1920.mp4"

# JPEG 帧是 full range，必须显式转 BT.709 limited range，否则奶油底会发灰
ffmpeg -y -hide_banner -loglevel warning \
  -framerate 30 -i promo/fun/frames/f%05d.jpg \
  -i promo/fun/audio.wav \
  -vf "scale=in_range=full:out_range=tv,format=yuv420p" \
  -c:v libx264 -preset slow -crf 16 -profile:v high -level 4.1 \
  -color_range tv -colorspace bt709 -color_primaries bt709 -color_trc bt709 \
  -x264-params "keyint=48:min-keyint=24:scenecut=0:aq-mode=3" \
  -movflags +faststart \
  -c:a aac -b:a 192k -ar 48000 \
  -shortest \
  "$MP4"

# 封面：卡片落定、三枚印章都盖完之后
ffmpeg -y -hide_banner -loglevel warning \
  -i "$MP4" -ss 15.20 -frames:v 1 -update 1 -q:v 2 \
  "$OUT/封面_cover.jpg"

ls -lh "$OUT"
ffprobe -v error -show_entries format=duration,size,bit_rate \
  -show_entries stream=codec_name,width,height,pix_fmt,color_range,r_frame_rate \
  -of default=noprint_wrappers=1 "$MP4"
