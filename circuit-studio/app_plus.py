# Entry point: Physical Studio's Build helper (builder.py) is the first tab, the commit viewer the
# second, and the original Circuit Studio app (app.py, unchanged: photos + wiring notes -> 3D model)
# the third. builder.install() first routes app.py's Gemini calls through the key and model pool
# and makes its 3D viewer load without a CDN. Run: streamlit run app_plus.py
import runpy
from pathlib import Path
import streamlit as st
import builder

builder.install()
real_page_config=getattr(st,'_real_set_page_config',st.set_page_config);st._real_set_page_config=real_page_config
real_page_config(page_title='Physical Studio · Build helper',page_icon='🔧',layout='wide')
st.set_page_config=lambda *a,**k:None  # app.py sets its own page config; only the first call may run
st.title('Physical Studio')
helper,history,photos=st.tabs(['Build helper','Commits','Circuit model from photos'])
with photos:g=runpy.run_path(str(Path(__file__).with_name('app.py')))
with helper:builder.render(g)
with history:builder.render_commits(g)
