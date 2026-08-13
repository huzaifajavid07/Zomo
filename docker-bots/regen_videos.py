"""
Regenerate bot video pool — 5 min each, 320x240 @ 10fps.
Run ONCE before launching bots:
    python regen_videos.py
"""
import math
import sys
from pathlib import Path

POOL_DIR = Path(__file__).parent / "video_pool"
POOL_DIR.mkdir(exist_ok=True)

_BOT_SKIN_TONES = [
    (0.06, 0.30, 0.90),
    (0.05, 0.25, 0.80),
    (0.04, 0.20, 0.70),
    (0.08, 0.35, 0.95),
    (0.07, 0.22, 0.60),
]

def _hsv_to_yuv(h, s, v):
    hi = int(h * 6) % 6
    f  = h * 6 - int(h * 6)
    p  = v * (1 - s);  q = v * (1 - f * s);  t = v * (1 - (1 - f) * s)
    rgb_map = [(v,t,p),(q,v,p),(p,v,t),(p,q,v),(t,p,v),(v,p,q)]
    r, g, b = rgb_map[hi]
    Y =  16 + int(65.481*r + 128.553*g + 24.966*b)
    U = 128 + int(-37.797*r - 74.203*g + 112.0*b)
    V = 128 + int(112.0*r - 93.786*g - 18.214*b)
    return (max(16,min(235,Y)), max(16,min(240,U)), max(16,min(240,V)))

def gen(path, bot_idx, W=320, H=240, FPS=10, DUR=300):
    tone = _BOT_SKIN_TONES[bot_idx % len(_BOT_SKIN_TONES)]
    sY, sU, sV = _hsv_to_yuv(*tone)
    total = FPS * DUR
    cx, cy = W // 2, H // 2
    hr = min(W, H) // 6
    bw = min(W, H) // 4;  bh = min(W, H) // 3
    hcy = cy - hr * 2;    bcy = cy + hr

    print(f"  Generating {path.name} ({total} frames, ~{DUR}s)...")
    sys.stdout.flush()

    # Precompute masks
    face_mask = bytearray(W * H)
    uv_mask   = bytearray((W//2) * (H//2))
    for row in range(H):
        for col in range(W):
            dx = col - cx
            if math.sqrt(dx**2 + (row-hcy)**2) < hr or \
               math.sqrt((dx/bw)**2 + ((row-bcy)/bh)**2) < 1.0:
                face_mask[row*W+col] = 1
    for row in range(H//2):
        for col in range(W//2):
            dx = col*2 - cx
            if math.sqrt(dx**2 + (row*2-hcy)**2) < hr or \
               math.sqrt((dx/bw)**2 + ((row*2-bcy)/bh)**2) < 1.0:
                uv_mask[row*(W//2)+col] = 1

    with open(path, "wb") as f:
        f.write(f"YUV4MPEG2 W{W} H{H} F{FPS}:1 Ip A1:1 C420\n".encode())
        for fn in range(total):
            phase = fn / FPS * 0.5
            anim = int(4 * math.sin(phase))
            y = bytearray(W * H)
            for i in range(W * H):
                if face_mask[i]:
                    y[i] = max(16, min(235, sY + anim))
                else:
                    bg = 70 + int(8 * math.sin((i // W) * 0.04 + phase))
                    y[i] = max(16, min(235, bg))
            u = bytearray((W//2)*(H//2))
            v = bytearray((W//2)*(H//2))
            for i in range(len(uv_mask)):
                u[i] = sU if uv_mask[i] else 128
                v[i] = sV if uv_mask[i] else 128
            f.write(b"FRAME\n")
            f.write(bytes(y) + bytes(u) + bytes(v))
            if fn % 50 == 0:
                pct = fn * 100 // total
                print(f"    {pct}%...", end="\r", flush=True)
    print(f"  ✓ {path.name} done.")

if __name__ == "__main__":
    # Remove old short files
    for p in POOL_DIR.glob("*.y4m"):
        try:
            p.unlink()
            print(f"Removed old: {p.name}")
        except Exception as e:
            print(f"Could not remove {p.name}: {e} — close any programs using it first.")

    print(f"\nGenerating 5 bot video feeds in {POOL_DIR}/")
    for i in range(5):
        gen(POOL_DIR / f"bot_face_{i:02d}.y4m", i)

    print(f"\n✅ All done! {len(list(POOL_DIR.glob('*.y4m')))} video files ready.")
