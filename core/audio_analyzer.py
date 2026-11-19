import asyncio
from pathlib import Path
from typing import List, Dict, Any
import subprocess
from config import FFMPEG_PATH

class AudioAnalyzer:
    @staticmethod
    async def detect_silence(video_path: Path, noise_threshold_db: int = -30, min_silence_sec: float = 0.5) -> List[Dict[str, float]]:
        """
        Использует ffmpeg silencedetect для поиска немых пауз в речи,
        чтобы автоматически вырезать их для динамичного темпа.
        """
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
