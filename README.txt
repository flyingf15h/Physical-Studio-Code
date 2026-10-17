CIRCUIT MODEL STUDIO V7 — BASED ON YOUR UPLOADED WORKING V5 FILES

Full standalone project, not a patch. Same Python geometry -> GLB -> GLTFLoader viewer
pipeline as the supplied working app. No browser-side geometry generation/export rewrite.

MAC SETUP: stop previous Streamlit with Control+C; extract this ZIP, open its folder in
VS Code and run:
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py

Your supplied config.py is preserved. This ZIP contains your key: keep private, do not
commit/share config.py. Replace the previously exposed key before public deployment.

REQUESTED CHANGES
1. Fixed muted palette used in geometry/GLB, not merely prompted: dusty rose, warm yellow,
   mint green, dusty blue, lavender, taupe, cream, slate and pale metal. Saturated input
   colors are mapped into these fixed colors. Structural colors are fixed too.
2. Medium warm grey background #aaa6a3 (neither white nor almost black).
3. One uniform cyan #26c6da highlight. Uses a separate untextured material with vertex
   colors DISABLED, preventing base colors from multiplying the selection color.
   Original materials restore on deselection. GLB export never includes highlights.
4. Breadboard has wider 1.16mm square recessed wells, actual 1.8mm depth, contrasting
   wall and floor colors. These are real recessed surfaces, not a flat square marker.
   Not through-holes, not print-ready CAD. Full-size 63-row template, not measured scan.
5. Optional saved scene.json rebuild without any new Gemini request (compatible V5 schema).
6. Visible viewer errors at startup, without opening browser developer tools.

PRESERVED
10 images <=30MB total, additional instructions, backend key/no key field in UI,
clickable part names/model, existing named terminal endpoint/wire logic and GLB export.
No prewired circuit/GPIO network; input instructions determine intended connections.
Colors and geometric templates are fixed, not your electrical circuit.

LIMITS
Physical pin mappings still symbolic unless verified; no electrical validation.
Photo-informed labels are semantic model labels, not independent finished-mesh detection.
Generic ESP32-like template, approximate placements, possible part overlaps. Resistor
bands are decorative. Revised JSON or instructions may be needed for a bad layout.
Gemini quota/cost/data terms apply. Images are resized/re-encoded before submission.
The viewer uses Three.js from jsDelivr and requires internet/WebGL; no NVIDIA needed.
Not production security-hardened: use locally.

TESTS PERFORMED
- Python syntax for app, geometry and config.
- JavaScript syntax checked with Node on the actual viewer module.
- Executed isolated recessed-well generation: mesh dimensions, nonzero triangle areas,
  depth and separate top/wall/floor colors checked.
- Executed actual selection logic with Node test objects: red/green selections use the
  SAME material, vertex colors disabled, original materials restore on clear.
- ZIP integrity checked.
Not performed: full trimesh rendering, live Gemini request or Safari/WebGL visual run.
