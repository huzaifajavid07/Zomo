"""
Engine YouTube Seeder Module
Provides programmatic and async API for downloading Zoom meeting videos from YouTube
and generating looping .y4m feeds for bot video pool.
"""

import asyncio
import json
import logging
import os
import shutil
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger("Zomo.YouTubeSeeder")

BASE_DIR = Path(__file__).resolve().parent.parent
FEED_CATALOG_FILE = BASE_DIR / "data" / "feeds_catalog.json"
VIDEO_POOL_DIR = BASE_DIR / "video_pool"
DOCKER_VIDEO_POOL_DIR = BASE_DIR / "docker-bots" / "video_pool"
PREVIEWS_DIR = BASE_DIR / "data" / "feeds"


def get_feeds_catalog() -> List[Dict[str, any]]:
    """Return all cataloged video feeds."""
    if FEED_CATALOG_FILE.exists():
        try:
            with open(FEED_CATALOG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error reading feeds catalog: {e}")
            return []
    return []


def delete_feed(feed_id: str) -> bool:
    """Delete a video feed from pool and catalog."""
    catalog = get_feeds_catalog()
    new_catalog = [item for item in catalog if item.get("id") != feed_id]

    # Delete files
    for pool_dir in (VIDEO_POOL_DIR, DOCKER_VIDEO_POOL_DIR):
        y4m_path = pool_dir / f"{feed_id}.y4m"
        if y4m_path.exists():
            try:
                y4m_path.unlink()
            except Exception:
                pass

    mp4_path = PREVIEWS_DIR / f"{feed_id}.mp4"
    if mp4_path.exists():
        try:
            mp4_path.unlink()
        except Exception:
            pass

    thumb_path = PREVIEWS_DIR / f"{feed_id}.jpg"
    if thumb_path.exists():
        try:
            thumb_path.unlink()
        except Exception:
            pass

    try:
        FEED_CATALOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(FEED_CATALOG_FILE, "w", encoding="utf-8") as f:
            json.dump(new_catalog, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error saving updated catalog: {e}")
        return False


async def run_youtube_seeder_task(
    youtube_url: Optional[str] = None,
    input_file: Optional[str] = None,
    duration: float = 6.0,
    max_bots: int = 10,
    grid: Optional[str] = None,
    no_ping_pong: bool = False
) -> List[Dict[str, any]]:
    """Run feed extraction in a background thread executor."""
    from youtube_feed_seeder import seed_feeds_from_youtube

    loop = asyncio.get_running_loop()
    feeds = await loop.run_in_executor(
        None,
        lambda: seed_feeds_from_youtube(
            youtube_url=youtube_url,
            input_file=input_file,
            duration=duration,
            max_bots=max_bots,
            grid_spec=grid,
            output_pool_dir=str(VIDEO_POOL_DIR),
            preview_dir=str(PREVIEWS_DIR),
            ping_pong=not no_ping_pong
        )
    )
    return feeds
