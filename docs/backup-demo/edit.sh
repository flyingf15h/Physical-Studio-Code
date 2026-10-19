set -e
# Cuts clips/ into physical-studio-backup-demo.mp4 (title cards, captions, 3x on the waits).
F=/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf
R=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf
V="-c:v libx264 -preset medium -crf 20 -pix_fmt yuv420p -r 30 -an"
D=$(ls clips/design/*.webm); B=$(ls clips/build/*.webm); C=$(ls clips/cad/*.webm); T=$(ls clips/track2/*.webm); P=$(ls clips/photo/*.webm)
card(){ # out, big, small, secs
  printf '%s' "$2" > seg/$1a.txt; printf '%s' "$3" > seg/$1b.txt
  ffmpeg -v error -y -f lavfi -i color=c=0x0e7c86:s=1920x1080:d=$4:r=30 -vf "drawtext=fontfile=$F:textfile=seg/$1a.txt:fontsize=84:fontcolor=white:x=(w-tw)/2:y=(h-th)/2-50,drawtext=fontfile=$R:textfile=seg/$1b.txt:fontsize=40:fontcolor=white@0.9:x=(w-tw)/2:y=(h/2)+60" $V seg/$1.mp4; }
cut(){ # out, src, start, end, speed, caption
  printf '%s' "$6" > seg/$1.txt
  ffmpeg -v error -y -ss $3 -to $4 -i "$2" -vf "setpts=(PTS-STARTPTS)/$5,fps=30,drawbox=x=0:y=ih-64:w=iw:h=64:color=black@0.55:t=fill,drawtext=fontfile=$R:textfile=seg/$1.txt:fontsize=32:fontcolor=white:x=40:y=h-48" $V seg/$1.mp4; }
card 00 'Physical Studio' 'Describe a hardware project. Get a guide anyone can follow.' 4
cut 01 "$D" 0 14 1 'You describe it (live on physicalstudio.work)'
cut 02 "$D" 14 84 3 'The AI picks real, measured parts, checks the circuit and builds a 3D model per step  (3x speed)'
cut 03 "$D" 84 92 1 'Done: the parts list, with real sizes'
cut 04 "$B" 0 43 1 'One part per step, an animated picture and a 3D model of your bench after each step'
cut 05 "$C" 0 43 1 'Enclosure builds: a 3D-printed case, assembled step by step (ready-made traffic light)'
card 06 'Tracking your build' 'Gemini checks your work against each step' 3
cut 07 "$T" 0 35 1 'Watch my bench: Gemini Live sees the camera and talks you through the step (simulated camera feed)'
cut 08 "$P" 4 8 1 'Or check a step with a photo'
cut 09 "$P" 8 36 3 'Gemini compares the photo with the step  (3x speed)'
cut 10 "$P" 36 41.8 1 'Looks right: the LED is where the step says'
card 11 'physicalstudio.work' 'github.com/notkelly1/Physical-Studio-Code' 5
ls seg/*.mp4 | sed "s/.*/file '&'/" > list.txt
ffmpeg -v error -y -f concat -safe 0 -i list.txt -c copy physical-studio-backup-demo.mp4
