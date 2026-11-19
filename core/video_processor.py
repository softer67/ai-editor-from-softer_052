import asyncio
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional
from config import FFMPEG_PATH, TEMP_DIR

class VideoProcessor:
    @staticmethod
    async def cut_silences_and_render(
        input_video: Path,
        silences: List[Dict[str, float]],
        output_name: str = "edited_result.mp4",
        apply_dynamic_zoom: bool = True,
        target_aspect_9_16: bool = True
    ) -> Path:
        """
        Вырезает длинные паузы из видео с помощью FFmpeg complex filter,
        добавляет динамический зум (punch-in) для удержания внимания зрителя.
        """
        output_path = TEMP_DIR / output_name

        def _get_duration(path: Path) -> float:
            cmd = [
                FFMPEG_PATH,
                "-i", str(path),
                "-hide_banner"
            ]
            proc = subprocess.Popen(cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, text=True)
            _, err = proc.communicate()
            for line in err.splitlines():
                if "Duration:" in line:
                    time_str = line.split("Duration:")[1].split(",")[0].strip()
                    h, m, s = time_str.split(":")
                    return int(h) * 3600 + int(m) * 60 + float(s)
            return 60.0

        total_duration = await asyncio.to_thread(_get_duration, input_video)

        # Вычисляем активные интервалы речи (не паузы)
        active_intervals = []
        last_end = 0.0
        # Добавляем небольшой буфер (padding) по краям речи, чтобы не обрезать слова
        padding = 0.08

        for s in silences:
            start_sil = max(0.0, s["start"] + padding)
            end_sil = max(0.0, s["end"] - padding)
            if start_sil > last_end:
                active_intervals.append((last_end, start_sil))
            last_end = max(last_end, end_sil)

        if last_end < total_duration:
            active_intervals.append((last_end, total_duration))

        # Если пауз не найдено или видео короткое, просто копируем/конвертируем
        if not active_intervals:
            active_intervals = [(0.0, total_duration)]

        def _render():
            filter_chunks = []
            concat_inputs = []

            for idx, (st, en) in enumerate(active_intervals):
                v_label = f"v{idx}"
                a_label = f"a{idx}"
                
                # Чередуем легкий зум 1.1x на четных склейках для эффекта динамики (punch-in)
                if apply_dynamic_zoom and (idx % 2 == 1):
                    # crop/scale punch-in
                    v_filter = f"[0:v]trim=start={st:.2f}:end={en:.2f},setpts=PTS-STARTPTS,scale=1.1*iw:-1,crop=iw/1.1:ih/1.1[{v_label}];"
                else:
                    v_filter = f"[0:v]trim=start={st:.2f}:end={en:.2f},setpts=PTS-STARTPTS[{v_label}];"
                
                a_filter = f"[0:a]atrim=start={st:.2f}:end={en:.2f},asetpts=PTS-STARTPTS[{a_label}];"
                
                filter_chunks.append(v_filter)
                filter_chunks.append(a_filter)
                concat_inputs.append(f"[{v_label}][{a_label}]")

            concat_filter = f"{''.join(concat_inputs)}concat=n={len(active_intervals)}:v=1:a=1[outv][outa]"
            filter_complex = "".join(filter_chunks) + concat_filter

            cmd = [
                FFMPEG_PATH,
                "-y",
                "-i", str(input_video),
                "-filter_complex", filter_complex,
                "-map", "[outv]",
                "-map", "[outa]",
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "22",
                "-c:a", "aac",
                "-b:a", "192k",
                str(output_path)
            ]

            process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if process.returncode != 0:
                # В случае ошибки fallback на прямое кодирование
                fallback_cmd = [
                    FFMPEG_PATH, "-y", "-i", str(input_video),
                    "-c:v", "libx264", "-c:a", "aac", str(output_path)
                ]
                subprocess.run(fallback_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            return output_path

        return await asyncio.to_thread(_render)
