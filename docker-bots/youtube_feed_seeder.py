"""
YouTube Zoom Meeting Participant Cropper & Video Feed Seeder
=============================================================
Automated pipeline to:
  1. Ingest YouTube videos or local Zoom meeting recordings.
  2. Automatically detect participant tiles in Gallery View or detect human faces.
  3. Extract 5–8 second high-quality active clips per participant.
  4. Apply seamless ping-pong / palindrome loop smoothing (A -> B -> A).
  5. Export both .y4m (ready for Playwright fake webcam) and .mp4 (dashboard preview).
  6. Populate the video pool for instant multi-bot deployment.

Usage:
  # Download from YouTube and auto-crop all participant feeds:
  python youtube_feed_seeder.py --url "https://www.youtube.com/watch?v=..." --duration 6 --max-bots 10

  # Process a local Zoom recording MP4:
  python youtube_feed_seeder.py --input-file meeting.mp4 --duration 6 --output-dir ./video_pool

  # Manual grid override (e.g. 3x3 grid):
  python youtube_feed_seeder.py --url "https://www.youtube.com/watch?v=..." --grid 3x3
"""

import argparse
import json
import math
import os
import random
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parent if SCRIPT_DIR.name == "docker-bots" else SCRIPT_DIR


def is_ffmpeg_available() -> bool:
    """Check if ffmpeg is accessible."""
    return shutil.which("ffmpeg") is not None


def is_ffprobe_available() -> bool:
    """Check if ffprobe is accessible."""
    return shutil.which("ffprobe") is not None


def is_ytdlp_available() -> bool:
    """Check if yt-dlp is installed."""
    try:
        import yt_dlp
        return True
    except ImportError:
        return shutil.which("yt-dlp") is not None


def download_youtube_video(url: str, output_dir: Path) -> Optional[Path]:
    """
    Download highest quality video stream (up to 1080p) from YouTube URL.
    Returns path to downloaded MP4 file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    temp_template = str(output_dir / "yt_meeting_%(id)s.%(ext)s")

    print(f"\n📥 Downloading YouTube video: {url}...")

    # Strategy 1: Use yt_dlp Python package
    try:
        import yt_dlp

        ydl_opts = {
            "format": "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "outtmpl": temp_template,
            "quiet": False,
            "no_warnings": True,
            "merge_output_format": "mp4",
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            if not filename.endswith(".mp4"):
                filename = Path(filename).with_suffix(".mp4")
            downloaded_file = Path(filename)
            if downloaded_file.exists():
                print(f"  ✓ Downloaded successfully: {downloaded_file.name} ({downloaded_file.stat().st_size / (1024*1024):.2f} MB)")
                return downloaded_file
    except ImportError:
        pass
    except Exception as e:
        print(f"  [Warning] yt_dlp python module failed: {e}")

    # Strategy 2: Use yt-dlp CLI if installed
    if shutil.which("yt-dlp"):
        try:
            cmd = [
                "yt-dlp",
                "-f", "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4]/best",
                "--merge-output-format", "mp4",
                "-o", temp_template,
                url
            ]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.returncode == 0:
                # Find matching file in output_dir
                for f in output_dir.glob("yt_meeting_*.mp4"):
                    if f.is_file() and f.stat().st_size > 10000:
                        print(f"  ✓ Downloaded CLI successfully: {f.name}")
                        return f
        except Exception as e:
            print(f"  [Warning] yt-dlp CLI failed: {e}")

    print(f"❌ Failed to download YouTube URL. Ensure 'yt-dlp' is installed: pip install yt-dlp")
    return None


def get_video_metadata(video_path: str) -> Dict[str, any]:
    """Retrieve resolution, duration, and FPS of a video."""
    meta = {"width": 1920, "height": 1080, "duration": 60.0, "fps": 30.0}

    try:
        import cv2
        cap = cv2.VideoCapture(video_path)
        if cap.isOpened():
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = float(cap.get(cv2.CAP_PROP_FPS)) or 30.0
            count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            dur = count / fps if fps > 0 else 60.0
            cap.release()
            return {"width": w, "height": h, "duration": dur, "fps": fps}
    except Exception:
        pass

    if is_ffprobe_available():
        try:
            cmd = [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height,r_frame_rate,duration",
                "-of", "json",
                video_path
            ]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            data = json.loads(res.stdout)
            stream = data.get("streams", [{}])[0]
            meta["width"] = int(stream.get("width", 1920))
            meta["height"] = int(stream.get("height", 1080))
            if "r_frame_rate" in stream and "/" in stream["r_frame_rate"]:
                n, d = stream["r_frame_rate"].split("/")
                meta["fps"] = float(n) / float(d) if float(d) > 0 else 30.0
            if "duration" in stream:
                meta["duration"] = float(stream["duration"])
        except Exception:
            pass

    return meta


def detect_zoom_grid_tiles(width: int, height: int, grid_spec: Optional[str] = None) -> List[Tuple[int, int, int, int]]:
    """
    Generate participant bounding box coordinates (x, y, w, h) for standard Zoom gallery grids.
    Supports auto-splitting or specific grid specifications like '2x2', '3x3', '4x4', '5x5'.
    """
    if grid_spec and "x" in grid_spec.lower():
        parts = grid_spec.lower().split("x")
        cols = max(1, int(parts[0]))
        rows = max(1, int(parts[1]))
    else:
        # Default typical Zoom gallery view is 3x3 (9 tiles) or 2x2 (4 tiles)
        cols, rows = 3, 3

    # Margins for Zoom top/bottom toolbar UI
    margin_top = int(height * 0.05)
    margin_bottom = int(height * 0.08)
    margin_left = int(width * 0.03)
    margin_right = int(width * 0.03)

    usable_w = width - (margin_left + margin_right)
    usable_h = height - (margin_top + margin_bottom)

    tile_w = usable_w // cols
    tile_h = usable_h // rows

    boxes = []
    # Inset slightly into each tile to avoid borders/names
    padding_x = int(tile_w * 0.04)
    padding_y = int(tile_h * 0.04)

    for r in range(rows):
        for c in range(cols):
            x = margin_left + (c * tile_w) + padding_x
            y = margin_top + (r * tile_h) + padding_y
            w = tile_w - (2 * padding_x)
            h = tile_h - (2 * padding_y)
            boxes.append((x, y, w, h))

    return boxes


def detect_active_participant_regions(
    video_path: str,
    max_regions: int = 9,
    grid_spec: Optional[str] = None,
    sample_time_sec: float = 10.0
) -> List[Tuple[int, int, int, int]]:
    """
    Scans video frame to detect active participants using face detection and/or Zoom gallery grid.
    Returns list of (x, y, w, h) bounding boxes.
    """
    try:
        import cv2
    except ImportError:
        print("[WARN] OpenCV not available. Using mathematical Zoom gallery layout.")
        meta = get_video_metadata(video_path)
        return detect_zoom_grid_tiles(meta["width"], meta["height"], grid_spec)[:max_regions]

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        meta = get_video_metadata(video_path)
        return detect_zoom_grid_tiles(meta["width"], meta["height"], grid_spec)[:max_regions]

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(sample_time_sec * fps))

    ret, frame = cap.read()
    if not ret or frame is None:
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        ret, frame = cap.read()

    cap.release()

    if not ret or frame is None:
        meta = get_video_metadata(video_path)
        return detect_zoom_grid_tiles(meta["width"], meta["height"], grid_spec)[:max_regions]

    h, w = frame.shape[:2]

    # Try Haar Cascades Face Detection
    face_cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    detected_boxes = []

    if os.path.exists(face_cascade_path):
        face_cascade = cv2.CascadeClassifier(face_cascade_path)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=4,
            minSize=(int(w * 0.05), int(h * 0.05)),
            maxSize=(int(w * 0.7), int(h * 0.7))
        )

        for (fx, fy, fw, fh) in faces:
            # Expand face box to webcam portrait (head + shoulders, 4:3 or 16:9 ratio)
            center_x = fx + fw // 2
            center_y = fy + fh // 2

            crop_w = int(fw * 2.8)
            crop_h = int(fh * 3.2)

            crop_x = max(0, center_x - crop_w // 2)
            crop_y = max(0, center_y - int(crop_h * 0.4))  # Keep headroom

            # Boundary clipping
            if crop_x + crop_w > w:
                crop_x = max(0, w - crop_w)
            if crop_y + crop_h > h:
                crop_y = max(0, h - crop_h)

            crop_w = min(crop_w, w - crop_x)
            crop_h = min(crop_h, h - crop_y)

            detected_boxes.append((crop_x, crop_y, crop_w, crop_h))

    # If face detector found participants, use them
    if len(detected_boxes) >= 1:
        print(f"  🔍 Detected {len(detected_boxes)} human face region(s) in Zoom recording.")
        return detected_boxes[:max_regions]

    # Otherwise fallback to grid layout
    print(f"  📐 Using smart Zoom gallery grid segmentation.")
    return detect_zoom_grid_tiles(w, h, grid_spec)[:max_regions]


def convert_rgb_to_yuv420(rgb_bytes: bytes, width: int, height: int) -> bytes:
    """Convert raw RGB24 bytes to YUV420 Planar bytes."""
    y_plane = bytearray(width * height)
    u_plane = bytearray((width // 2) * (height // 2))
    v_plane = bytearray((width // 2) * (height // 2))

    for r in range(height):
        for c in range(width):
            idx = (r * width + c) * 3
            R = rgb_bytes[idx]
            G = rgb_bytes[idx + 1]
            B = rgb_bytes[idx + 2]

            Y = int(0.299 * R + 0.587 * G + 0.114 * B)
            y_plane[r * width + c] = max(16, min(235, Y))

    for r in range(height // 2):
        for c in range(width // 2):
            sr, sc = r * 2, c * 2
            idx = (sr * width + sc) * 3
            R = rgb_bytes[idx]
            G = rgb_bytes[idx + 1]
            B = rgb_bytes[idx + 2]

            U = int(-0.168736 * R - 0.331264 * G + 0.5 * B + 128)
            V = int(0.5 * R - 0.418688 * G - 0.081312 * B + 128)

            uv_idx = r * (width // 2) + c
            u_plane[uv_idx] = max(16, min(240, U))
            v_plane[uv_idx] = max(16, min(240, V))

    return bytes(y_plane) + bytes(u_plane) + bytes(v_plane)


def extract_participant_clip(
    video_path: str,
    bbox: Tuple[int, int, int, int],
    start_sec: float,
    duration_sec: float,
    output_y4m: Path,
    output_mp4: Optional[Path] = None,
    output_thumb: Optional[Path] = None,
    out_width: int = 640,
    out_height: int = 480,
    out_fps: int = 15,
    ping_pong: bool = True
) -> bool:
    """
    Extracts a participant's bounding box over the given time window,
    applies seamless ping-pong palindrome smoothing, and writes .y4m and .mp4.
    """
    x, y, w, h = bbox
    output_y4m.parent.mkdir(parents=True, exist_ok=True)
    if output_mp4:
        output_mp4.parent.mkdir(parents=True, exist_ok=True)

    # Strategy 1: FFmpeg (Fast & Efficient)
    if is_ffmpeg_available():
        try:
            # Crop + Scale + Frame rate filter
            crop_filter = f"crop={w}:{h}:{x}:{y},scale={out_width}:{out_height}:force_original_aspect_ratio=increase,crop={out_width}:{out_height},fps={out_fps}"

            if ping_pong:
                filter_complex = f"{crop_filter},split=2[fwd][rev];[rev]reverse[rev2];[fwd][rev2]concat=n=2:v=1[v]"
                cmd_y4m = [
                    "ffmpeg", "-y",
                    "-ss", f"{start_sec:.2f}",
                    "-t", f"{duration_sec:.2f}",
                    "-i", str(video_path),
                    "-filter_complex", filter_complex,
                    "-map", "[v]",
                    "-pix_fmt", "yuv420p",
                    str(output_y4m)
                ]
            else:
                cmd_y4m = [
                    "ffmpeg", "-y",
                    "-ss", f"{start_sec:.2f}",
                    "-t", f"{duration_sec:.2f}",
                    "-i", str(video_path),
                    "-vf", crop_filter,
                    "-pix_fmt", "yuv420p",
                    str(output_y4m)
                ]

            res = subprocess.run(cmd_y4m, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.returncode == 0 and output_y4m.exists() and output_y4m.stat().st_size > 0:
                # Also generate MP4 preview if requested
                if output_mp4:
                    cmd_mp4 = [
                        "ffmpeg", "-y",
                        "-i", str(output_y4m),
                        "-c:v", "libx264",
                        "-pix_fmt", "yuv420p",
                        "-crf", "23",
                        "-preset", "veryfast",
                        str(output_mp4)
                    ]
                    subprocess.run(cmd_mp4, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

                # Generate thumbnail
                if output_thumb:
                    cmd_thumb = [
                        "ffmpeg", "-y",
                        "-i", str(output_y4m),
                        "-vframes", "1",
                        str(output_thumb)
                    ]
                    subprocess.run(cmd_thumb, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

                return True
        except Exception as e:
            print(f"  [FFmpeg Extract Warning]: {e}")

    # Strategy 2: OpenCV + PIL Fallback
    try:
        import cv2
        from PIL import Image
    except ImportError:
        print("❌ OpenCV and Pillow required for pure-Python fallback. pip install opencv-python Pillow")
        return False

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return False

    src_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    start_frame = int(start_sec * src_fps)
    num_frames = int(duration_sec * src_fps)

    cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, start_frame))

    raw_frames = []
    read_count = 0
    step = src_fps / out_fps if src_fps > 0 else 1.0
    accum = 0.0

    while read_count < num_frames:
        ret, frame_bgr = cap.read()
        if not ret or frame_bgr is None:
            break

        accum += 1.0
        if accum >= step:
            accum -= step
            # Crop bbox
            fh, fw = frame_bgr.shape[:2]
            cx1 = max(0, min(fw, x))
            cy1 = max(0, min(fh, y))
            cx2 = max(0, min(fw, x + w))
            cy2 = max(0, min(fh, y + h))

            crop_bgr = frame_bgr[cy1:cy2, cx1:cx2]
            if crop_bgr.size == 0:
                continue

            crop_rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(crop_rgb)

            # Aspect fit & resize
            img_ratio = img.width / img.height
            target_ratio = out_width / out_height

            if img_ratio > target_ratio:
                new_w = int(img.height * target_ratio)
                left = (img.width - new_w) // 2
                img = img.crop((left, 0, left + new_w, img.height))
            else:
                new_h = int(img.width / target_ratio)
                top = (img.height - new_h) // 2
                img = img.crop((0, top, img.width, top + new_h))

            img = img.resize((out_width, out_height), Image.Resampling.LANCZOS)
            raw_frames.append(img.tobytes())

            if read_count == 0 and output_thumb:
                img.save(str(output_thumb))

        read_count += 1

    cap.release()

    if not raw_frames:
        return False

    # Ping-pong mirror
    if ping_pong and len(raw_frames) > 2:
        output_frames = raw_frames + raw_frames[-2:0:-1]
    else:
        output_frames = raw_frames

    # Write Y4M
    with open(output_y4m, "wb") as f:
        header = f"YUV4MPEG2 W{out_width} H{out_height} F{out_fps}:1 Ip A1:1 C420\n"
        f.write(header.encode("ascii"))

        for rgb_bytes in output_frames:
            yuv_data = convert_rgb_to_yuv420(rgb_bytes, out_width, out_height)
            f.write(b"FRAME\n")
            f.write(yuv_data)

    return True


def seed_feeds_from_youtube(
    youtube_url: Optional[str] = None,
    input_file: Optional[str] = None,
    duration: float = 6.0,
    max_bots: int = 10,
    grid_spec: Optional[str] = None,
    output_pool_dir: Optional[str] = None,
    preview_dir: Optional[str] = None,
    out_width: int = 640,
    out_height: int = 480,
    out_fps: int = 15,
    ping_pong: bool = True
) -> List[Dict[str, any]]:
    """
    Main entry point: downloads/reads meeting video, crops participants into 5-8s looping feeds,
    and seeds both video_pool and previews.
    """
    pool_path = Path(output_pool_dir) if output_pool_dir else ROOT_DIR / "video_pool"
    docker_pool_path = ROOT_DIR / "docker-bots" / "video_pool"
    previews_path = Path(preview_dir) if preview_dir else ROOT_DIR / "data" / "feeds"

    pool_path.mkdir(parents=True, exist_ok=True)
    docker_pool_path.mkdir(parents=True, exist_ok=True)
    previews_path.mkdir(parents=True, exist_ok=True)

    # 1. Resolve source video file
    video_source: Optional[Path] = None
    if input_file and Path(input_file).exists():
        video_source = Path(input_file)
    elif youtube_url:
        temp_dl_dir = ROOT_DIR / "data" / "youtube_downloads"
        video_source = download_youtube_video(youtube_url, temp_dl_dir)

    if not video_source or not video_source.exists():
        print("❌ Error: No valid video source found.")
        return []

    print(f"\n🎬 Processing Zoom Meeting: {video_source.name}")
    meta = get_video_metadata(str(video_source))
    print(f"  Duration: {meta['duration']:.1f}s | Resolution: {meta['width']}x{meta['height']} | FPS: {meta['fps']:.1f}")

    # 2. Detect participant regions
    # Sample at 15% into the video to skip opening intro/waiting room
    sample_time = min(30.0, meta["duration"] * 0.15) if meta["duration"] > 10 else 1.0
    regions = detect_active_participant_regions(
        str(video_source),
        max_regions=max_bots,
        grid_spec=grid_spec,
        sample_time_sec=sample_time
    )

    if not regions:
        print("❌ Could not detect any participant regions.")
        return []

    print(f"✂️ Cropping {len(regions)} participant feed(s) ({duration:.1f}s snippets with palindrome loop)...")

    # 3. Determine start offset for clip extraction (e.g. 20s in or random active window)
    max_start = max(0.0, meta["duration"] - duration - 2.0)
    start_sec = min(20.0, max_start * 0.3) if max_start > 20.0 else (max_start * 0.5)

    catalog = []
    catalog_file = ROOT_DIR / "data" / "feeds_catalog.json"
    if catalog_file.exists():
        try:
            with open(catalog_file, "r", encoding="utf-8") as f:
                catalog = json.load(f)
        except Exception:
            catalog = []

    generated_feeds = []

    # Get existing feed index
    existing_count = len(list(pool_path.glob("bot_face_*.y4m")))

    for idx, bbox in enumerate(regions):
        feed_idx = existing_count + idx
        feed_id = f"bot_face_{feed_idx:02d}"
        out_y4m = pool_path / f"{feed_id}.y4m"
        out_docker_y4m = docker_pool_path / f"{feed_id}.y4m"
        out_mp4 = previews_path / f"{feed_id}.mp4"
        out_thumb = previews_path / f"{feed_id}.jpg"

        # Slight time offset per participant to make feeds desynchronized & natural
        participant_start = max(0.0, min(max_start, start_sec + (idx * 1.5)))

        ok = extract_participant_clip(
            video_path=str(video_source),
            bbox=bbox,
            start_sec=participant_start,
            duration_sec=duration,
            output_y4m=out_y4m,
            output_mp4=out_mp4,
            output_thumb=out_thumb,
            out_width=out_width,
            out_height=out_height,
            out_fps=out_fps,
            ping_pong=ping_pong
        )

        if ok and out_y4m.exists():
            # Copy to docker-bots video pool as well
            if pool_path.resolve() != docker_pool_path.resolve():
                shutil.copy2(out_y4m, out_docker_y4m)

            size_mb = out_y4m.stat().st_size / (1024 * 1024)
            print(f"  ✓ [{idx+1}/{len(regions)}] Feed Ready: {feed_id}.y4m ({size_mb:.2f} MB)")

            feed_meta = {
                "id": feed_id,
                "name": f"Zoom Participant #{feed_idx+1}",
                "y4m_path": str(out_y4m.resolve()),
                "mp4_path": str(out_mp4.resolve()) if out_mp4.exists() else None,
                "thumbnail": str(out_thumb.resolve()) if out_thumb.exists() else None,
                "duration_sec": duration,
                "resolution": f"{out_width}x{out_height}",
                "source": youtube_url or str(video_source.name),
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            catalog.append(feed_meta)
            generated_feeds.append(feed_meta)
        else:
            print(f"  ✗ Failed extracting participant #{idx+1}")

    # Save updated catalog
    try:
        with open(catalog_file, "w", encoding="utf-8") as f:
            json.dump(catalog, f, indent=2)
    except Exception as e:
        print(f"[Warning] Failed writing feeds catalog: {e}")

    print(f"\n🎉 Successfully created {len(generated_feeds)} bot video feed(s) in video_pool/!")
    return generated_feeds


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed Bot Video Feeds from YouTube Zoom Meeting Recordings")
    parser.add_argument("--url", type=str, default=None, help="YouTube video URL of Zoom meeting")
    parser.add_argument("--input-file", type=str, default=None, help="Local MP4 Zoom recording file")
    parser.add_argument("--duration", type=float, default=6.0, help="Snippet duration in seconds (5-8 recommended)")
    parser.add_argument("--max-bots", type=int, default=10, help="Maximum number of participant feeds to extract")
    parser.add_argument("--grid", type=str, default=None, help="Zoom gallery grid override (e.g. 2x2, 3x3, 4x4)")
    parser.add_argument("--output-dir", type=str, default=None, help="Custom output directory for Y4M feeds")
    parser.add_argument("--width", type=int, default=640, help="Output width (default: 640)")
    parser.add_argument("--height", type=int, default=480, help="Output height (default: 480)")
    parser.add_argument("--fps", type=int, default=15, help="Output framerate (default: 15)")
    parser.add_argument("--no-ping-pong", action="store_true", help="Disable seamless ping-pong forward-reverse loop")

    args = parser.parse_args()

    if not args.url and not args.input_file:
        print("Usage:")
        print("  python youtube_feed_seeder.py --url 'https://www.youtube.com/watch?v=...' --duration 6")
        print("  python youtube_feed_seeder.py --input-file meeting.mp4 --duration 6")
        sys.exit(1)

    seed_feeds_from_youtube(
        youtube_url=args.url,
        input_file=args.input_file,
        duration=args.duration,
        max_bots=args.max_bots,
        grid_spec=args.grid,
        output_pool_dir=args.output_dir,
        out_width=args.width,
        out_height=args.height,
        out_fps=args.fps,
        ping_pong=not args.no_ping_pong
    )
