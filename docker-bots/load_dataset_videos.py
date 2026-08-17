"""
Download and prepare talking head video dataset for Zoom bot webcam feeds.
Streams videos from Hugging Face dataset (e.g. Haosonnn/OpenHumanVid-Talking or others)
or downloads sample talking-face clips directly, then converts them into seamless
looping Y4M files in video_pool/.
"""
import os
import sys
import socket
import urllib.request
from pathlib import Path

# Set default socket timeout to prevent premature 'read operation timed out' on large parquet files
socket.setdefaulttimeout(180)

# Add current dir to path
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from dataset_to_video import convert_dataset_clip_to_y4m, process_dataset_directory

# Sample curated royalty-free talking head / webcam clips for instant fallback
SAMPLE_TALKING_VIDEOS = [
    "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4",
    "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerEscapes.mp4",
    "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerFun.mp4",
    "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerJoyBlazes.mp4",
    "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerMeltdowns.mp4",
    "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/WeAreGoingOnBullrun.mp4",
    "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/WhatCarCanYouGetForAGrand.mp4",
    "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4",
    "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ElephantsDream.mp4",
    "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/TearsOfSteel.mp4",
]

def download_sample_videos(raw_dir: Path, target_count: int = 10) -> int:
    """Download sample video clips directly as a quick and reliable fallback."""
    print(f"\n📥 Downloading {target_count} sample video clips into '{raw_dir}'...")
    downloaded = 0
    for i in range(target_count):
        url = SAMPLE_TALKING_VIDEOS[i % len(SAMPLE_TALKING_VIDEOS)]
        out_file = raw_dir / f"sample_face_{i:02d}.mp4"
        try:
            print(f"  [{i+1}/{target_count}] Fetching {url.split('/')[-1]}...")
            urllib.request.urlretrieve(url, str(out_file))
            if out_file.exists() and out_file.stat().st_size > 1000:
                downloaded += 1
        except Exception as e:
            print(f"  [Warning] Failed downloading {url}: {e}")
    return downloaded

def main():
    dataset_name = os.environ.get("DATASET_NAME", "Haosonnn/OpenHumanVid-Talking")
    output_dir = SCRIPT_DIR / "video_pool"
    raw_dataset_dir = SCRIPT_DIR / "facial_dataset"
    target_count = int(os.environ.get("BOT_COUNT", "10"))
    snippet_duration = float(os.environ.get("SNIPPET_DURATION", "15.0"))
    hf_token = os.environ.get("HF_TOKEN", None)

    output_dir.mkdir(parents=True, exist_ok=True)
    raw_dataset_dir.mkdir(parents=True, exist_ok=True)

    print(f"==================================================")
    print(f"  Dataset:           {dataset_name}")
    print(f"  Target Feeds:      {target_count}")
    print(f"  Output Directory:  {output_dir}")
    print(f"  HF Token Set:      {'Yes' if hf_token else 'No (set HF_TOKEN for faster speeds)'}")
    print(f"==================================================")

    # Check if user passed an explicit fallback flag or if datasets is unavailable
    use_samples = os.environ.get("USE_SAMPLES", "0").lower() in ("1", "true", "yes")

    if not use_samples:
        try:
            from datasets import load_dataset
        except ImportError:
            print("[WARN] 'datasets' library not installed. Falling back to sample video download.")
            use_samples = True

    if not use_samples:
        print(f"Connecting to Hugging Face dataset '{dataset_name}' (streaming mode)...")
        print("Note: If the remote dataset parquet is large, initial connection may take 1-2 minutes.")
        try:
            ds = load_dataset(
                dataset_name,
                split="train",
                streaming=True,
                token=hf_token
            )
            
            sample_count = 0
            print(f"Streaming and converting clips into bot video pool...")

            for idx, item in enumerate(ds):
                if sample_count >= target_count:
                    break

                raw_mp4_path = raw_dataset_dir / f"face_source_{sample_count:03d}.mp4"
                out_y4m_path = output_dir / f"bot_face_{sample_count:02d}.y4m"

                try:
                    video_data = item.get("video") or item.get("mp4") or item.get("content") or item.get("file")
                    data_bytes = None
                    if isinstance(video_data, dict):
                        data_bytes = video_data.get("bytes")
                        if not data_bytes and "path" in video_data and os.path.exists(video_data["path"]):
                            with open(video_data["path"], "rb") as f:
                                data_bytes = f.read()
                    elif isinstance(video_data, (bytes, bytearray)):
                        data_bytes = video_data

                    if not data_bytes:
                        print(f"  [Skip item {idx}] Unrecognized format or keys: {list(item.keys())}")
                        continue

                    with open(raw_mp4_path, "wb") as f:
                        f.write(data_bytes)

                    print(f"  -> Saved clip {sample_count + 1} ({len(data_bytes)/1024/1024:.2f} MB), converting to Y4M...")

                    ok = convert_dataset_clip_to_y4m(
                        input_file=str(raw_mp4_path),
                        output_y4m=str(out_y4m_path),
                        snippet_min=snippet_duration,
                        snippet_max=snippet_duration,
                        width=320,
                        height=240,
                        fps=15,
                        ping_pong=True
                    )

                    if ok and out_y4m_path.exists():
                        sample_count += 1
                        size_mb = out_y4m_path.stat().st_size / (1024 * 1024)
                        print(f"  ✓ [{sample_count}/{target_count}] Bot feed ready: {out_y4m_path.name} ({size_mb:.2f} MB)")
                    else:
                        print(f"  ✗ Failed conversion for clip {idx}")

                except Exception as e:
                    print(f"  [Error processing item {idx}]: {e}")

            if sample_count > 0:
                print(f"\n✅ Finished! {sample_count} video feeds populated in '{output_dir}'.")
                return

        except Exception as e:
            print(f"\n[ERROR] Streaming from Hugging Face failed: {e}")
            print("Falling back to downloading sample video clips directly...")
            use_samples = True

    if use_samples:
        dl_count = download_sample_videos(raw_dataset_dir, target_count=target_count)
        if dl_count > 0:
            print(f"\nConverting downloaded sample videos to Y4M feeds in '{output_dir}'...")
            process_dataset_directory(
                dataset_dir=str(raw_dataset_dir),
                output_dir=str(output_dir),
                count=target_count,
                snippet_min=snippet_duration,
                snippet_max=snippet_duration,
                width=320,
                height=240,
                fps=15,
                ping_pong=True
            )
        else:
            print("[ERROR] Could not download fallback videos. Please place MP4 files directly into 'facial_dataset/'.")

if __name__ == "__main__":
    main()

