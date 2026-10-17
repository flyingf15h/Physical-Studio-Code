# Entry point that runs the main Circuit Studio app (app.py, unchanged) and then adds the build
# helper section under it. builder.install() first routes app.py's Gemini calls through the key
# and model pool and makes its 3D viewer load without a CDN. Run: streamlit run app_plus.py
import runpy
from pathlib import Path
import builder

builder.install()
builder.render(runpy.run_path(str(Path(__file__).with_name('app.py'))))
