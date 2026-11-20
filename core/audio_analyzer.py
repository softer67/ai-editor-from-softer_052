import asyncio
from pathlib import Path
from typing import List, Dict, Any
import subprocess
from config import FFMPEG_PATH

class AudioAnalyzer:
    @staticmethod
    async def detect_silence(
        video_path: Path,
        mode: str = "edit_tiktok"
    ) -> List[Dict[str, float]]:
        """
        Ищет паузы и моменты тишины в зависимости от выбранного режима:
        - edit_tiktok: вырезает даже микро-паузы (> 0.35s) для клиповой динамики.
        - youtube_long: убирает только долгие заминки (> 0.9s), не нарушая дыхание и темп речи.
        - clean_silence: стандартное удаление неловких пауз (> 0.6s).
        """
        if mode == "edit_tiktok":
            noise_threshold_db = -28
            min_silence_sec = 0.35
        elif mode == "youtube_long":
            noise_threshold_db = -32
            min_silence_sec = 0.90
        else: # clean_silence
            noise_threshold_db = -30
            min_silence_sec = 0.60

        cmd = [
            FFMPEG_PATH,
            "-i", str(video_path),
            "-af", f"silencedetect=n={noise_threshold_db}dB:d={min_silence_sec}",
            "-f", "null",
            "-"
        ]

        def _run_silence_detect():
            process = subprocess.Popen(cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, text=True)
            _, stderr = process.communicate()
            
            silences = []
            cur_start = None
            
            for line in stderr.splitlines():
                if "silence_start:" in line:
                    parts = line.split("silence_start:")
                    cur_start = float(parts[1].strip().split()[0])
                elif "silence_end:" in line and cur_start is not None:
                    parts = line.split("silence_end:")
                    end_str = parts[1].strip().split()[0]
                    cur_end = float(end_str)
                    silences.append({"start": cur_start, "end": cur_end, "duration": cur_end - cur_start})
                    cur_start = None
            return silences

        return await asyncio.to_thread(_run_silence_detect)
