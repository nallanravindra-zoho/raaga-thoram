"""Cut the AAA emblem out of the logo picture so it can sit on a dark title.

    .venv/bin/python tools/make_logo_cutout.py [content/brand/aaa_logo_original.jpg] [content/brand/aaa_logo.png]

The flat background around the emblem and the wording under it are removed (the title writes the name itself).
The window inside the middle A keeps its light background so the line drawing in it stays visible.
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage

HERE = Path(__file__).resolve().parent.parent
src = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "content" / "brand" / "aaa_logo_original.jpg"
dst = Path(sys.argv[2]) if len(sys.argv) > 2 else HERE / "content" / "brand" / "aaa_logo.png"

im = Image.open(src).convert("RGB")
a = np.asarray(im).astype(np.int32)
h, w, _ = a.shape
bg = np.median(a[int(h * 0.1):int(h * 0.2), int(w * 0.05):int(w * 0.2)].reshape(-1, 3), axis=0)   # the flat background colour
red = (a[..., 0] > a[..., 1] + 40) & (a[..., 0] > a[..., 2] + 40)                                 # the emblem itself
rows = np.where(red.sum(axis=1) > 3)[0]
cols = np.where(red.sum(axis=0) > 3)[0]
pad = int(h * 0.012)
y0, y1, x0, x1 = max(0, rows[0] - pad), min(h, rows[-1] + pad), max(0, cols[0] - pad), min(w, cols[-1] + pad)
a, red = a[y0:y1, x0:x1], red[y0:y1, x0:x1]
H, W = red.shape

# everything that is not the emblem, split into connected areas: the outside, the middle window, the small gaps in the side letters
lab, n = ndimage.label(~ndimage.binary_dilation(red, iterations=1))
edge = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))) - {0}
keep = np.zeros((H, W), bool)
for i in range(1, n + 1):
    if i in edge:
        continue
    ys, xs = np.where(lab == i)
    if abs(xs.mean() - W / 2) < W * 0.17:        # inside the middle A: the window with the drawing
        keep |= lab == i
window = ndimage.binary_fill_holes(ndimage.binary_dilation(keep, iterations=2))
alpha = (red | window).astype(np.uint8) * 255
out = np.dstack([a.astype(np.uint8), alpha])
# lift the window's flat colour to a warm parchment so the drawing reads on a dark title
wn = window & ~red
rgb = out[..., :3].astype(np.float32)
rgb[wn] = np.clip(rgb[wn] / bg * np.array([236, 222, 196]), 0, 255)
out[..., :3] = rgb.astype(np.uint8)
res = Image.fromarray(out, "RGBA")
res.putalpha(res.getchannel("A").filter(ImageFilter.GaussianBlur(0.8)))
dst.parent.mkdir(parents=True, exist_ok=True)
res.save(dst)
print("wrote", dst, res.size)
