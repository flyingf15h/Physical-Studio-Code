"""Records the landing page's clips (media/pendulum.mp4, media/breadboard.mp4) from the real build page.

The page's clock (performance.now, Date.now, requestAnimationFrame) is virtual and moves 1/60 s per captured
frame, so every animation (parts dropping in, the camera easing between steps, wires drawing) comes out at a
smooth 60 fps however slow the capture is. Step changes are clean cuts: the clock is frozen while the next
step loads. Uses the real GPU (headless Chromium with Vulkan) so the 3D renders as it does for people.

  # viewer dev server + MCP server running (see PROJECT.md), then:
  python3 landing/record.py            # both clips
  python3 landing/record.py pendulum   # one clip
Needs playwright (pip install playwright; playwright install chromium) and ffmpeg.
"""
import os
import shutil
import subprocess
import sys
import tempfile

from playwright.sync_api import sync_playwright

BASE = os.environ.get("BASE", "http://localhost:5173")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "media")
FPS, W, H, DPR = 60, 1440, 810, 2  # 2880 x 1620 frames, encoded at 1920 x 1080

CLOCK = """(() => {
  let now = performance.now(); const d0 = Date.now() - now; const q = new Map(); let id = 0;
  performance.now = () => now; Date.now = () => d0 + now;
  window.requestAnimationFrame = (cb) => { q.set(++id, cb); return id };
  window.cancelAnimationFrame = (i) => { q.delete(i) };
  window.__tick = (ms) => { now += ms; const cbs = [...q.values()]; q.clear(); for (const cb of cbs) { try { cb(now) } catch (e) { console.error(e) } } };
})();"""

# guide id -> [(step, seconds on screen)]; skipped steps are passed through off camera.
CLIPS = {
    "pendulum": ("double-pendulum", [(1, 1.6), (2, 1.6), (3, 1.7), (5, 1.6), (6, 1.7), (7, 1.7), (12, 1.9), (18, 1.9), (25, 1.8), (28, 1.8), (32, 2.2)], "Drawing"),
    "breadboard": ("traffic-light", [(3, 1.7), (4, 1.7), (5, 1.6), (6, 1.6), (9, 1.8), (11, 1.9), (13, 1.9), (17, 2.4)], None),
}


def record(name, guide, shots, finale):
    frames = tempfile.mkdtemp(prefix=f"clip-{name}-")
    n = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--enable-gpu", "--use-angle=vulkan", "--ignore-gpu-blocklist", "--hide-scrollbars"])
        ctx = browser.new_context(viewport={"width": W, "height": H}, device_scale_factor=DPR)
        ctx.add_init_script(CLOCK)
        pg = ctx.new_page()

        def tick(ms=1000 / FPS):
            pg.evaluate(f"window.__tick({ms})")

        def rec(seconds):
            nonlocal n
            for _ in range(int(seconds * FPS)):
                tick()
                pg.screenshot(path=os.path.join(frames, f"{n:05d}.jpg"), type="jpeg", quality=93)
                n += 1

        def click(name):
            pg.get_by_role("button", name=name).first.click()
            pg.wait_for_load_state("networkidle")
            for _ in range(20):  # React commits and the step's GLB loads with the clock frozen
                pg.wait_for_timeout(50)
                tick(0)

        pg.goto(f"{BASE}/build/{guide}")
        pg.wait_for_load_state("networkidle")
        pg.add_style_tag(content="*{caret-color:transparent!important} ::-webkit-scrollbar{display:none}")
        for _ in range(40):
            for _ in range(6):
                tick()
            pg.wait_for_timeout(100)
        click("Start step 1")
        at = 1
        for step, seconds in shots:
            while at < step:
                click("Next step")
                at += 1
            rec(seconds)
        if finale:
            click(finale)
            rec(2.0)
        browser.close()

    out = os.path.join(OUT, f"{name}.mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(FPS), "-i", os.path.join(frames, "%05d.jpg"),
                    "-vf", "scale=1920:-2:flags=lanczos", "-c:v", "libx264", "-preset", "slow", "-crf", "20",
                    "-pix_fmt", "yuv420p", "-movflags", "+faststart", out], check=True)
    shutil.rmtree(frames)
    print(f"{out}: {n} frames, {os.path.getsize(out) // 1024} KB")


if __name__ == "__main__":
    for name in sys.argv[1:] or CLIPS:
        record(name, *CLIPS[name])
