"""
Learn Router - YouTube videos from Girish Gupta's channel
"""

from fastapi import APIRouter, Query
import httpx
import os
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
CHANNEL_ID = "UCx9iSqzfMMw7JVo0P2H45Pw"  # @GirishGuptaOfficial
YT_API_BASE = "https://www.googleapis.com/youtube/v3"


@router.get("/videos")
async def get_videos(
    page_token: str = Query("", description="Page token for pagination"),
    max_results: int = Query(10, le=20, description="Max results per page"),
):
    """Fetch latest videos from Girish Gupta's channel"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Search for channel uploads
            params = {
                "part": "snippet",
                "channelId": CHANNEL_ID,
                "order": "date",
                "type": "video",
                "maxResults": max_results,
                "key": YOUTUBE_API_KEY,
            }
            if page_token:
                params["pageToken"] = page_token

            resp = await client.get(f"{YT_API_BASE}/search", params=params)
            if resp.status_code != 200:
                logger.error(f"YouTube API error: {resp.status_code} {resp.text[:200]}")
                return {"videos": [], "error": "YouTube API error"}

            data = resp.json()
            video_ids = [
                item["id"]["videoId"]
                for item in data.get("items", [])
                if item.get("id", {}).get("videoId")
            ]

            # Get video statistics (view counts)
            videos = []
            stats_map = {}
            if video_ids:
                stats_resp = await client.get(
                    f"{YT_API_BASE}/videos",
                    params={
                        "part": "statistics,contentDetails",
                        "id": ",".join(video_ids),
                        "key": YOUTUBE_API_KEY,
                    },
                )
                if stats_resp.status_code == 200:
                    for item in stats_resp.json().get("items", []):
                        stats_map[item["id"]] = {
                            "views": int(item.get("statistics", {}).get("viewCount", 0)),
                            "likes": int(item.get("statistics", {}).get("likeCount", 0)),
                            "duration": item.get("contentDetails", {}).get("duration", ""),
                        }

            for item in data.get("items", []):
                vid_id = item.get("id", {}).get("videoId")
                if not vid_id:
                    continue
                snippet = item.get("snippet", {})
                stats = stats_map.get(vid_id, {})
                videos.append({
                    "videoId": vid_id,
                    "title": snippet.get("title", ""),
                    "description": snippet.get("description", ""),
                    "thumbnail": snippet.get("thumbnails", {}).get("high", {}).get("url", ""),
                    "publishedAt": snippet.get("publishedAt", ""),
                    "channelTitle": snippet.get("channelTitle", ""),
                    "views": stats.get("views", 0),
                    "likes": stats.get("likes", 0),
                    "duration": stats.get("duration", ""),
                })

            return {
                "videos": videos,
                "nextPageToken": data.get("nextPageToken", ""),
                "totalResults": data.get("pageInfo", {}).get("totalResults", 0),
            }
    except Exception as e:
        logger.error(f"Error fetching videos: {e}")
        return {"videos": [], "error": str(e)}


@router.get("/search")
async def search_videos(
    q: str = Query(..., min_length=1, description="Search query"),
    page_token: str = Query("", description="Page token for pagination"),
    max_results: int = Query(10, le=20, description="Max results per page"),
):
    """Search videos within Girish Gupta's channel"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            params = {
                "part": "snippet",
                "channelId": CHANNEL_ID,
                "q": q,
                "order": "relevance",
                "type": "video",
                "maxResults": max_results,
                "key": YOUTUBE_API_KEY,
            }
            if page_token:
                params["pageToken"] = page_token

            resp = await client.get(f"{YT_API_BASE}/search", params=params)
            if resp.status_code != 200:
                return {"videos": [], "error": "YouTube API error"}

            data = resp.json()
            video_ids = [
                item["id"]["videoId"]
                for item in data.get("items", [])
                if item.get("id", {}).get("videoId")
            ]

            stats_map = {}
            if video_ids:
                stats_resp = await client.get(
                    f"{YT_API_BASE}/videos",
                    params={
                        "part": "statistics,contentDetails",
                        "id": ",".join(video_ids),
                        "key": YOUTUBE_API_KEY,
                    },
                )
                if stats_resp.status_code == 200:
                    for item in stats_resp.json().get("items", []):
                        stats_map[item["id"]] = {
                            "views": int(item.get("statistics", {}).get("viewCount", 0)),
                            "likes": int(item.get("statistics", {}).get("likeCount", 0)),
                            "duration": item.get("contentDetails", {}).get("duration", ""),
                        }

            videos = []
            for item in data.get("items", []):
                vid_id = item.get("id", {}).get("videoId")
                if not vid_id:
                    continue
                snippet = item.get("snippet", {})
                stats = stats_map.get(vid_id, {})
                videos.append({
                    "videoId": vid_id,
                    "title": snippet.get("title", ""),
                    "description": snippet.get("description", ""),
                    "thumbnail": snippet.get("thumbnails", {}).get("high", {}).get("url", ""),
                    "publishedAt": snippet.get("publishedAt", ""),
                    "channelTitle": snippet.get("channelTitle", ""),
                    "views": stats.get("views", 0),
                    "likes": stats.get("likes", 0),
                    "duration": stats.get("duration", ""),
                })

            return {
                "videos": videos,
                "nextPageToken": data.get("nextPageToken", ""),
                "totalResults": data.get("pageInfo", {}).get("totalResults", 0),
            }
    except Exception as e:
        logger.error(f"Error searching videos: {e}")
        return {"videos": [], "error": str(e)}
