#!/usr/bin/env python3
"""玩梗版宣传片逐帧渲染（promo/fun/video.html）。

用法：
  python3 promo/fun/capture.py --stills 1200,3000,5500
  python3 promo/fun/capture.py --all --fps 30
"""
import argparse
import pathlib
import time

from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).resolve().parent
PAGE = (HERE / "video.html").as_uri() + "?still=1"
W, H = 1080, 1920


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stills", default="")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--out", default=str(HERE / "frames"))
    ap.add_argument("--q", type=int, default=95)
    args = ap.parse_args()

    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            args=["--force-color-profile=srgb", "--font-render-hinting=none"]
        )
        page = browser.new_page(
            viewport={"width": W, "height": H}, device_scale_factor=1
        )
        errs = []
        page.on("pageerror", lambda e: errs.append(str(e)))
        page.goto(PAGE)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(500)
        dur = page.evaluate("() => window.__DURATION")

        if args.stills:
            for ms in [int(x) for x in args.stills.split(",") if x.strip()]:
                page.evaluate("(t) => window.renderAt(t)", ms)
                page.wait_for_timeout(50)
                page.screenshot(path=str(out / f"still_{ms:05d}.png"))
            print("stills ->", out)
            if errs:
                print("PAGE ERROR:", errs[:3])
            browser.close()
            return

        if not args.all:
            ap.error("需要 --stills 或 --all")
            return

        total = int(dur / 1000 * args.fps)
        t0 = time.time()
        for i in range(total):
            page.evaluate("(t) => window.renderAt(t)", i * 1000.0 / args.fps)
            page.screenshot(
                path=str(out / f"f{i:05d}.jpg"), type="jpeg", quality=args.q
            )
            if i % 90 == 0:
                el = time.time() - t0
                eta = el / max(i, 1) * (total - i)
                print(f"  {i}/{total}  {el:.0f}s  eta {eta:.0f}s", flush=True)
        print(f"done {total} frames in {time.time() - t0:.0f}s")
        browser.close()


if __name__ == "__main__":
    main()
