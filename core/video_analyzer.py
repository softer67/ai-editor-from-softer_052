import asyncio
from pathlib import Path
from typing import List, Dict, Any
from scenedetect import open_video, SceneManager, ContentDetector

class VideoAnalyzer:
    @staticmethod
    async def analyze_cuts(video_path: Path) -> Dict[str, Any]:
        """Анализирует темп монтажа референса (частота склеек и длительность сцен)"""
        def _detect():
            video = open_video(str(video_path))
            scene_manager = SceneManager()
            scene_manager.add_detector(ContentDetector(threshold=27.0))
            scene_manager.detect_scenes(video)
            scene_list = scene_manager.get_scene_list()

            scenes_data = []
            durations = []
            for start, end in scene_list:
                dur = (end.get_seconds() - start.get_seconds())
                durations.append(dur)
                scenes_data.append({
                    "start": start.get_seconds(),
                    "end": end.get_seconds(),
                    "duration": dur
                })

            avg_dur = sum(durations) / len(durations) if durations else 3.0
            
            # Определение темпа
            if avg_dur < 1.8:
                pace = "ultra_fast"  # TikTok / клиповый монтаж
            elif avg_dur < 3.0:
                pace = "dynamic"     # Динамичный Reels / Shorts
            elif avg_dur < 5.0:
                pace = "medium"      # Стандартный блогерский
            else:
                pace = "calm"        # Спокойный разговорный

            return {
                "scenes_count": len(scenes_data),
                "avg_scene_duration": round(avg_dur, 2),
                "pace": pace,
                "scenes": scenes_data
            }

        return await asyncio.to_thread(_detect)
