# Entry point: Physical Studio's Build helper (builder.py) is the first tab, the commit viewer the
# second. Only app.py's definitions are loaded (Spec, validate, build, the key list), not its page: the
# Build helper's photo scan replaces app.py's own photos -> 3D model page. builder.install() first routes
# Gemini calls through the key and model pool and makes the 3D viewer load without a CDN.
# Run: streamlit run app_plus.py
from pathlib import Path
import streamlit as st
import builder

builder.install()
st.set_page_config(page_title='Physical Studio · Build helper',page_icon='🔧',layout='wide')
st.title('Physical Studio')
APP=Path(__file__).with_name('app.py')
source=APP.read_text()
if '\nst.set_page_config(' not in source:st.error('app.py changed shape: its definitions could not be loaded.');st.stop()
g={'__file__':str(APP),'__name__':'circuit_app'}
exec(compile(source.split('\nst.set_page_config(')[0],str(APP),'exec'),g)  # everything above app.py's page
helper,history=st.tabs(['Build helper','Commits'])
with helper:builder.render(g)
with history:builder.render_commits(g)
