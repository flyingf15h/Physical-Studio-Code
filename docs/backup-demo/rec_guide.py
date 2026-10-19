# Records the guide walkthroughs (fresh build + ready-made enclosure guide). Needs design_url.txt from rec_design.py.
import sys, subprocess
from playwright.sync_api import sync_playwright
EXE="/snap/chromium/current/usr/lib/chromium-browser/chrome"
GL=["--use-gl=angle","--use-angle=swiftshader","--enable-unsafe-swiftshader"]
SITE="https://physicalstudio.work"
BUILD=open("design_url.txt").read().split()[0]
VS={"width":1920,"height":1080}
which=sys.argv[1:] or ["build","cad"]

def drag(pg, x, y, dx, dy, steps=40):
    pg.mouse.move(x,y); pg.mouse.down(); pg.mouse.move(x+dx,y+dy,steps=steps); pg.mouse.up()

with sync_playwright() as p:
    b=p.chromium.launch(executable_path=EXE, args=GL)
    if "build" in which:
        ctx=b.new_context(viewport=VS, record_video_dir="clips/build", record_video_size=VS)
        pg=ctx.new_page(); pg.goto(BUILD, wait_until="networkidle"); pg.wait_for_timeout(3000)
        pg.mouse.wheel(0,500); pg.wait_for_timeout(1500); pg.mouse.wheel(0,-500); pg.wait_for_timeout(800)
        pg.get_by_role("button", name="Start step 1 →").click(); pg.wait_for_timeout(5000)
        for _ in range(3):
            pg.get_by_role("button", name="Next step →").click(); pg.wait_for_timeout(4500)
        side=pg.locator("button").filter(has_text="Connect the Red LED Signal Wire").first
        side.click(); pg.wait_for_timeout(5000)
        pg.mouse.wheel(0,450); pg.wait_for_timeout(2000)
        c=pg.locator("canvas").last.bounding_box()
        if c:
            cx,cy=c["x"]+c["width"]/2, c["y"]+c["height"]/2
            drag(pg,cx,cy,250,40); pg.wait_for_timeout(1200); drag(pg,cx,cy,-400,-30); pg.wait_for_timeout(1500)
        pg.screenshot(path="shots/b_end.png")
        ctx.close()
    if "cad" in which:
        ctx=b.new_context(viewport=VS, record_video_dir="clips/cad", record_video_size=VS)
        pg=ctx.new_page(); pg.goto(SITE+"/guide?design=traffic-light", wait_until="networkidle"); pg.wait_for_timeout(4000)
        pg.get_by_role("button", name="Next step").click(); pg.wait_for_timeout(4000)
        pg.get_by_role("button", name="Next step").click(); pg.wait_for_timeout(4000)
        drag(pg,1100,600,300,60); pg.wait_for_timeout(1200)
        pg.mouse.move(1100,600); pg.mouse.wheel(0,-300); pg.wait_for_timeout(1500)
        pg.get_by_text("Exploded").click(); pg.wait_for_timeout(3500)
        drag(pg,1100,600,-350,-40); pg.wait_for_timeout(1500)
        pg.get_by_text("Exploded").click(); pg.wait_for_timeout(3000)
        pg.get_by_text("Wire the red LED").first.click(); pg.wait_for_timeout(5000)
        pg.get_by_text("Close the lid").first.click(); pg.wait_for_timeout(5000)
        pg.get_by_role("button", name="Reset view").click(); pg.wait_for_timeout(2000)
        pg.screenshot(path="shots/c_end.png")
        ctx.close()
    b.close()
