"""
Generate a synthetic Y4M (YUV4MPEG2) mock video file.
Creates a simple animated gradient pattern that looks like a person-shaped
silhouette on a neutral background. Good enough for Zoom's video feed.

Usage:
  python generate_mock_video.py [--output mock_face.y4m] [--frames 300] [--width 640] [--height 480]
"""

import argparse
import struct
import math
import os


def generate_frame(width, height, frame_num, total_frames):
    """Generate a single YUV420 frame with a subtle animated gradient."""
    y_plane = bytearray(width * height)
    u_plane = bytearray((width // 2) * (height // 2))
    v_plane = bytearray((width // 2) * (height // 2))

    # Animated phase for subtle movement
    phase = (frame_num / total_frames) * 2 * math.pi

    cx, cy = width // 2, height // 2
    head_r = min(width, height) // 6
    body_w = min(width, height) // 4
    body_h = min(width, height) // 3

    for row in range(height):
        for col in range(width):
            # Distance from center
            dx = col - cx
            dy = row - cy

            # Head (circle at top)
            head_cy = cy - head_r * 2
            head_dist = math.sqrt(dx**2 + (row - head_cy)**2)

            # Body (ellipse below head)
            body_cy = cy + head_r
            body_dx = dx / body_w
            body_dy = (row - body_cy) / body_h
            body_dist = math.sqrt(body_dx**2 + body_dy**2)

            # Subtle animation offset
            anim_offset = int(3 * math.sin(phase + row * 0.01))

            if head_dist < head_r or body_dist < 1.0:
                # "Person" silhouette — warm skin-ish tone in Y
                y_val = 160 + int(15 * math.sin(phase * 0.5)) + anim_offset
            else:
                # Background — neutral gray-blue
                y_val = 80 + int(10 * math.sin(row * 0.02 + phase))

            y_plane[row * width + col] = max(16, min(235, y_val))

    # UV planes (downsampled 2x2) — give skin area warm tint
    for row in range(height // 2):
        for col in range(width // 2):
            src_row, src_col = row * 2, col * 2
            dx = src_col - cx
            dy = src_row - cy

            head_cy = cy - head_r * 2
            head_dist = math.sqrt(dx**2 + (src_row - head_cy)**2)
            body_cy = cy + head_r
            body_dist = math.sqrt((dx / body_w)**2 + ((src_row - body_cy) / body_h)**2)

            idx = row * (width // 2) + col

            if head_dist < head_r or body_dist < 1.0:
                u_plane[idx] = 110  # slight warm tint
                v_plane[idx] = 145
            else:
                u_plane[idx] = 128  # neutral
                v_plane[idx] = 128

    return bytes(y_plane) + bytes(u_plane) + bytes(v_plane)


def create_y4m(output_path, width=640, height=480, fps=15, duration_sec=20):
    """Create a Y4M video file with animated frames."""
    total_frames = fps * duration_sec

    print(f"Generating {output_path}: {width}x{height} @ {fps}fps, {total_frames} frames ({duration_sec}s)")

    with open(output_path, "wb") as f:
        # Y4M header
        header = f"YUV4MPEG2 W{width} H{height} F{fps}:1 Ip A1:1 C420\n"
        f.write(header.encode("ascii"))

        for i in range(total_frames):
            # Frame header
            f.write(b"FRAME\n")
            # Frame data
            frame = generate_frame(width, height, i, total_frames)
            f.write(frame)

            if (i + 1) % 50 == 0:
                print(f"  Frame {i + 1}/{total_frames}")

    file_size = os.path.getsize(output_path)
    print(f"Done! File size: {file_size / (1024 * 1024):.1f} MB")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate mock Y4M video for fake webcam")
    parser.add_argument("--output", default="mock_face.y4m", help="Output file path")
    parser.add_argument("--width", type=int, default=640, help="Video width")
    parser.add_argument("--height", type=int, default=480, help="Video height")
    parser.add_argument("--fps", type=int, default=15, help="Frames per second")
    parser.add_argument("--duration", type=int, default=20, help="Duration in seconds")

    args = parser.parse_args()
    create_y4m(args.output, args.width, args.height, args.fps, args.duration)
