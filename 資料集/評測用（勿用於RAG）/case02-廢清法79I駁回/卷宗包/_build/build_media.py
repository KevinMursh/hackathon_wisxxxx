"""採證照片後製、影像放大標註、行車紀錄器影片合成。"""
import os, subprocess, random, math
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

SP = os.path.dirname(os.path.abspath(__file__))
OUT = "/Users/caizhengyu/testtcowork/AI智慧城市黑客松/資料集/評測用（勿用於RAG）/case02-廢清法79I駁回/卷宗包/03-卷證"
PHOTO_DIR = f"{OUT}/05-採證照片"
VIDEO_DIR = f"{OUT}/13-採證影片"
FONT_MONO = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"
FONT_KAI = "/System/Library/AssetsV2/com_apple_MobileAsset_Font7/584ea2a48d14147049c2f9eaee147fe5a1f279ac.asset/AssetData/BiauKai.ttc"

random.seed(20250627)

# (原始檔, 秒數, 檔名)
FRAMES = [("raw1.png", 9, "01"), ("raw2.png", 14, "02"), ("raw3.png", 19, "03")]


def dashcam_overlay(img, sec, speed=0):
    """行車紀錄器風格：左下時間戳、右上 REC、右下車速；整體降質。"""
    w, h = img.size
    img = img.convert("RGB")
    # 降解析度再放大 → 壓縮感
    img = img.resize((w // 2, h // 2), Image.BILINEAR).resize((w, h), Image.BILINEAR)
    img = ImageEnhance.Color(img).enhance(0.85)
    d = ImageDraw.Draw(img)
    f = ImageFont.truetype(FONT_MONO, int(h * 0.036))
    ts = f"2025/06/27  12:40:{sec:02d}"
    # 陰影
    d.text((22, h - 62), ts, font=f, fill=(0, 0, 0))
    d.text((20, h - 64), ts, font=f, fill=(255, 255, 255))
    d.text((w - 172, h - 62), f"{speed:>3} km/h", font=f, fill=(0, 0, 0))
    d.text((w - 174, h - 64), f"{speed:>3} km/h", font=f, fill=(255, 255, 255))
    f2 = ImageFont.truetype(FONT_MONO, int(h * 0.032))
    d.ellipse((w - 118, 22, w - 98, 42), fill=(220, 30, 30))
    d.text((w - 90, 18), "REC", font=f2, fill=(255, 255, 255))
    # 暗角
    vig = Image.new("L", (w, h), 0)
    vd = ImageDraw.Draw(vig)
    vd.ellipse((-w * 0.25, -h * 0.35, w * 1.25, h * 1.35), fill=255)
    vig = vig.filter(ImageFilter.GaussianBlur(w * 0.18))
    dark = Image.new("RGB", (w, h), (0, 0, 0))
    img = Image.composite(img, dark, vig.point(lambda p: 90 + p * 165 // 255))
    return img


def build_photos():
    os.makedirs(PHOTO_DIR, exist_ok=True)
    outs = []
    for raw, sec, no in FRAMES:
        img = Image.open(f"{SP}/photos/{raw}")
        img = dashcam_overlay(img, sec)
        p = f"{PHOTO_DIR}/採證照片-{no}_20250627-1240{sec:02d}.jpg"
        img.save(p, "JPEG", quality=72)
        outs.append(p)
    return outs


def build_zoom(photo2):
    """影像放大標註版：裁切手部＋水溝蓋區域，放大 3 倍，紅框＋箭頭＋文字。"""
    img = Image.open(photo2)
    w, h = img.size
    # raw2 中手與煙蒂約在 (830,430)~(870,500)；水溝蓋在 (780,610)~(950,700)
    box = (620, 340, 1000, 720)
    crop = img.crop(box)
    z = crop.resize((crop.width * 3, crop.height * 3), Image.BICUBIC)
    z = z.filter(ImageFilter.GaussianBlur(0.6))
    d = ImageDraw.Draw(z)
    # 煙蒂位置（放大後座標）
    bx = ((840 - 620) * 3, (470 - 340) * 3)
    d.rectangle((bx[0] - 60, bx[1] - 50, bx[0] + 60, bx[1] + 70), outline=(230, 30, 30), width=6)
    d.line((bx[0] - 60, bx[1] - 40, bx[0] - 250, bx[1] - 150), fill=(230, 30, 30), width=6)
    f = ImageFont.truetype(FONT_KAI, 54)
    d.text((bx[0] - 640, bx[1] - 215), "煙蒂（拋擲中）", font=f, fill=(230, 30, 30))
    gx = ((865 - 620) * 3, (655 - 340) * 3)
    d.rectangle((gx[0] - 260, gx[1] - 120, gx[0] + 260, gx[1] + 130), outline=(30, 90, 230), width=6)
    d.text((gx[0] - 250, gx[1] - 190), "路邊水溝蓋", font=f, fill=(30, 90, 230))
    # 標題列
    bar = Image.new("RGB", (z.width, 130), (255, 255, 255))
    bd = ImageDraw.Draw(bar)
    f3 = ImageFont.truetype(FONT_KAI, 38)
    bd.text((24, 16), "影像放大版（放大 300%）", font=f3, fill=(0, 0, 0))
    bd.text((24, 70), "原檔：採證照片-02　攝於 2025/06/27 12:40:14", font=f3, fill=(60, 60, 60))
    canvas = Image.new("RGB", (z.width, z.height + bar.height), (255, 255, 255))
    canvas.paste(bar, (0, 0))
    canvas.paste(z, (0, bar.height))
    p = f"{OUT}/06-影像放大標註.jpg"
    canvas.save(p, "JPEG", quality=80)
    return p


def build_video():
    """15fps × 12s；三張照片各約 4 秒，加輕微鏡頭抖動與時間戳逐秒跳動。"""
    os.makedirs(VIDEO_DIR, exist_ok=True)
    fdir = f"{SP}/frames"
    os.makedirs(fdir, exist_ok=True)
    for f_ in os.listdir(fdir):
        os.remove(f"{fdir}/{f_}")
    fps, total = 15, 12
    raws = [Image.open(f"{SP}/photos/{r}").convert("RGB") for r, _, _ in FRAMES]
    W, H = 1280, 720
    idx = 0
    start_sec = 8
    for t in range(fps * total):
        seg = min(2, t // (fps * 4))
        base = raws[seg]
        # 輕微抖動與緩慢推近
        prog = (t % (fps * 4)) / (fps * 4)
        zoom = 1.0 + 0.04 * prog
        jx, jy = random.uniform(-3, 3), random.uniform(-2, 2)
        cw, ch = int(base.width / zoom), int(base.height / zoom)
        cx, cy = (base.width - cw) // 2 + int(jx), (base.height - ch) // 2 + int(jy)
        fr = base.crop((cx, cy, cx + cw, cy + ch)).resize((W, H), Image.BILINEAR)
        fr = dashcam_overlay(fr, start_sec + t // fps)
        fr.save(f"{fdir}/f{idx:04d}.jpg", "JPEG", quality=70)
        idx += 1
    out = f"{VIDEO_DIR}/違規採證影片_20250627-1240.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-framerate", str(fps), "-i", f"{fdir}/f%04d.jpg",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "28", "-preset", "fast", out,
    ], check=True)
    # 影片截圖（供截圖頁）
    shots = []
    for i, sec in enumerate([9, 12, 14, 17]):
        t = (sec - start_sec) * fps
        src = f"{fdir}/f{t:04d}.jpg"
        dst = f"{SP}/png/vshot{i+1}.jpg"
        Image.open(src).resize((640, 360)).save(dst, "JPEG", quality=80)
        shots.append(dst)
    return out, shots


if __name__ == "__main__":
    ps = build_photos()
    print("photos:", ps)
    print("zoom:", build_zoom(f"{SP}/photos/raw2.png"))
    v, s = build_video()
    print("video:", v, s)
