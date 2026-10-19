# Records Gemini tracking: Watch my bench with a simulated camera, then a photo check on the fresh build.
import os, subprocess, time
from playwright.sync_api import sync_playwright
EXE="/snap/chromium/current/usr/lib/chromium-browser/chrome"
GL=["--use-gl=angle","--use-angle=swiftshader","--enable-unsafe-swiftshader"]
SITE="https://physicalstudio.work"; VS={"width":1920,"height":1080}
BUILD=open("design_url.txt").read().split()[0]
with sync_playwright() as p:
    # 1. grab what step 1 should look like, as the simulated camera picture
    b=p.chromium.launch(executable_path=EXE, args=GL)
    pg=b.new_page(viewport={"width":1280,"height":720})
    pg.goto(SITE+"/guide?design=traffic-light", wait_until="networkidle"); pg.wait_for_timeout(5000)
    pg.add_style_tag(content="body *{visibility:hidden} canvas{visibility:visible}"); pg.wait_for_timeout(800); pg.locator(".stage canvas").first.screenshot(path="cam.png")
    # breadboard step-1 picture for the photo check
    pg.goto(BUILD, wait_until="networkidle"); pg.wait_for_timeout(3000)
    pg.get_by_role("button", name="Start step 1 →").click(); pg.wait_for_timeout(6000)
    pg.locator("canvas").last.screenshot(path="bench_step1.png")
    b.close()
    subprocess.run(["ffmpeg","-v","error","-y","-loop","1","-i","cam.png","-t","4","-vf","scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=0xe8e4df,format=yuv420p","-r","15","cam.y4m"],check=True)
    b=p.chromium.launch(executable_path=EXE, args=GL+["--use-fake-ui-for-media-stream","--use-fake-device-for-media-stream","--use-file-for-fake-video-capture="+os.path.abspath("cam.y4m")])
    # 2. Gemini Live watching the CAD guide
    ctx=b.new_context(viewport=VS, record_video_dir="clips/track2", record_video_size=VS, permissions=["camera","microphone"])
    pg=ctx.new_page(); pg.goto(SITE+"/guide?design=traffic-light", wait_until="networkidle"); pg.wait_for_timeout(4000)
    pg.get_by_text("Watch my bench").click()
    t0=time.time(); last=""
    while time.time()-t0<90:
        pg.wait_for_timeout(3000)
        txt=pg.inner_text("body")
        if txt!=last: last=txt
    pg.screenshot(path="shots/t_end.png"); open("track_text.txt","w").write(last)
    ctx.close()
    # 3. photo check on the freshly designed breadboard build
    ctx=b.new_context(viewport=VS, record_video_dir="clips/photo", record_video_size=VS)
    pg=ctx.new_page(); pg.goto(BUILD, wait_until="networkidle"); pg.wait_for_timeout(2500)
    pg.get_by_role("button", name="Start step 1 →").click(); pg.wait_for_timeout(4000)
    pg.get_by_role("button", name="Commit and check").scroll_into_view_if_needed(); pg.wait_for_timeout(1000)
    with pg.expect_file_chooser() as fc: pg.get_by_role("button", name="Upload photos").click()
    fc.value.set_files("bench_step1.png"); pg.wait_for_timeout(1500)
    pg.get_by_label("Commit message").press_sequentially("Is the red LED the right way round?", delay=40)
    pg.get_by_role("button", name="Commit and check").click()
    t0=time.time()
    while time.time()-t0<120:
        pg.wait_for_timeout(3000)
        if pg.get_by_role("button", name="Checking…").count()==0: break
    pg.wait_for_timeout(5000); pg.screenshot(path="shots/ph_end.png", full_page=False)
    ctx.close(); b.close()
