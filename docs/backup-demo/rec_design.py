# Records the backup demo: describe -> live design. Run from an empty folder; see docs/demo-video.md.
import time, sys
from playwright.sync_api import sync_playwright
EXE="/snap/chromium/current/usr/lib/chromium-browser/chrome"
PROMPT=("Traffic light for an Arduino Uno: red, yellow and green LEDs in a column, "
        "a crosswalk button, and a buzzer that beeps while people can cross.")
STAGES=[  # build page stage labels (viewer/src/pages/BuildPage.tsx)
    'Looking at your bench photos','Choosing the parts you still need','Checking the circuit and fixing','Building a 3D model for every step']
with sync_playwright() as p:
    b=p.chromium.launch(executable_path=EXE, args=["--use-gl=angle","--use-angle=swiftshader","--enable-unsafe-swiftshader"])
    ctx=b.new_context(viewport={"width":1920,"height":1080}, record_video_dir="clips/design", record_video_size={"width":1920,"height":1080})
    pg=ctx.new_page()
    t0=time.time(); marks=[]
    pg.goto("https://physicalstudio.work", wait_until="networkidle"); pg.wait_for_timeout(2500)
    box=pg.locator("textarea").first; box.click(); pg.wait_for_timeout(500)
    box.press_sequentially(PROMPT, delay=35); pg.wait_for_timeout(1500)
    pg.get_by_role("button", name="Design it").click()
    marks.append(("submitted", time.time()-t0))
    pg.wait_for_url("**/build/**", timeout=60000); print("url", pg.url, flush=True)
    i=0
    while time.time()-t0 < 900:
        pg.wait_for_timeout(5000); i+=1
        txt=pg.inner_text("body")
        if i%4==0: pg.screenshot(path=f"shots/d{i:03d}.png"); print(int(time.time()-t0), [s for s in STAGES if s in txt], flush=True)
        if not any(s in txt for s in STAGES) or "went wrong" in txt.lower():
            break
    marks.append(("finished", time.time()-t0))
    pg.wait_for_timeout(4000); pg.screenshot(path="shots/d_final.png")
    print("final url", pg.url, marks, flush=True)
    open("design_url.txt","w").write(pg.url+"\n"+repr(marks))
    ctx.close(); b.close()
