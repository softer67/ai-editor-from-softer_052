import asyncio
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional
from config import FFMPEG_PATH, TEMP_DIR, BASE_DIR
from core.music_selector import MusicSelector

ASSETS_DIR = BASE_DIR / "assets"
SFX_WHOOSH = ASSETS_DIR / "sfx" / "whoosh.wav"

class VideoProcessor:
    @staticmethod
    async def cut_silences_and_render(
        input_video: Path,
        silences: List[Dict[str, float]],
        output_name: str = "edited_result.mp4",
        mode: str = "edit_tiktok",             # "edit_tiktok" | "youtube_long" | "clean_silence"
        custom_music_path: Optional[Path] = None,
        use_ai_music: bool = False,
        prompt: Optional[str] = None,
        add_sfx_whoosh: bool = True
    ) -> Path:
        """
        Универсальный видеопроцессор с тремя режимами монтажа:
        1. edit_tiktok: Клиповый эдит под 9:16 (или мобильный), частые зумы 1.15x, Whoosh, драйвовая музыка.
        2. youtube_long: Горизонтальный 16:9, мягкая чистка пауз, редкие легкие зумы 1.05x, тихий Lo-Fi фон.
        3. clean_silence: Исходный ракурс (без зумов), чистое удаление неловких пауз и шумов.
        """
        output_path = TEMP_DIR / output_name

        def _get_duration(path: Path) -> float:
            cmd = [FFMPEG_PATH, "-i", str(path), "-hide_banner"]
            proc = subprocess.Popen(cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, text=True)
            _, err = proc.communicate()
            for line in err.splitlines():
                if "Duration:" in line:
                    time_str = line.split("Duration:")[1].split(",")[0].strip()
                    h, m, s = time_str.split(":")
                    return int(h) * 3600 + int(m) * 60 + float(s)
            return 60.0

        total_duration = await asyncio.to_thread(_get_duration, input_video)

        # Буфер краев речи в зависимости от режима
        padding = 0.06 if mode == "edit_tiktok" else 0.12

        active_intervals = []
        last_end = 0.0

        for s in silences:
            start_sil = max(0.0, s["start"] + padding)
            end_sil = max(0.0, s["end"] - padding)
            if start_sil > last_end:
                active_intervals.append((last_end, start_sil))
            last_end = max(last_end, end_sil)

        if last_end < total_duration:
            active_intervals.append((last_end, total_duration))

        if not active_intervals:
            active_intervals = [(0.0, total_duration)]

        # Определяем музыку
        music_file: Optional[Path] = None
        if custom_music_path and custom_music_path.exists():
            music_file = custom_music_path
        elif use_ai_music:
            music_file = MusicSelector.ai_select_track(prompt, mode)

        has_music = music_file is not None and music_file.exists() and mode != "clean_silence"
        has_whoosh = add_sfx_whoosh and SFX_WHOOSH.exists() and mode == "edit_tiktok"

        # Параметры видео под режим
        if mode == "edit_tiktok":
            zoom_factor = 1.15
            music_vol = 0.12
            scale_filter = "scale=-2:720"
        elif mode == "youtube_long":
            zoom_factor = 1.05
            music_vol = 0.06
            scale_filter = "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2"
        else: # clean_silence
            zoom_factor = 1.0
            music_vol = 0.0
            scale_filter = "scale=-2:720"

        def _render():
            filter_chunks = []
            concat_inputs = []

            for idx, (st, en) in enumerate(active_intervals):
                v_label = f"v{idx}"
                a_label = f"a{idx}"
                chunk_dur = en - st

                # В режиме clean_silence зумов нет вообще
                # В edit_tiktok зум на каждой 2-й склейке
                # В youtube_long редкий зум на каждой 4-й склейке
                if mode == "edit_tiktok":
                    is_zoom = (idx % 2 == 1)
                elif mode == "youtube_long":
                    is_zoom = (idx % 4 == 2)
                else:
                    is_zoom = False

                if is_zoom:
                    v_filter = f"[0:v]trim=start={st:.2f}:end={en:.2f},setpts=PTS-STARTPTS,scale={zoom_factor}*iw:-1,crop=iw/{zoom_factor}:ih/{zoom_factor},{scale_filter}[{v_label}];"
                else:
                    v_filter = f"[0:v]trim=start={st:.2f}:end={en:.2f},setpts=PTS-STARTPTS,{scale_filter}[{v_label}];"

                # Нарезка аудио
                if is_zoom and has_whoosh:
                    v_raw_a = f"a_raw_{idx}"
                    sfx_raw = f"sfx_{idx}"
                    a_filter = (
                        f"[0:a]atrim=start={st:.2f}:end={en:.2f},asetpts=PTS-STARTPTS[{v_raw_a}];"
                        f"[1:a]atrim=0:{chunk_dur:.2f},asetpts=PTS-STARTPTS,volume=0.35[{sfx_raw}];"
                        f"[{v_raw_a}][{sfx_raw}]amix=inputs=2:duration=first[{a_label}];"
                    )
                else:
                    a_filter = f"[0:a]atrim=start={st:.2f}:end={en:.2f},asetpts=PTS-STARTPTS[{a_label}];"

                filter_chunks.append(v_filter)
                filter_chunks.append(a_filter)
                concat_inputs.append(f"[{v_label}][{a_label}]")

            concat_filter = f"{''.join(concat_inputs)}concat=n={len(active_intervals)}:v=1:a=1[concat_v][concat_a]"
            
            # Подмешивание фоновой музыки
            music_input_idx = 2 if has_whoosh else 1
            if has_music:
                mix_music_filter = (
                    f";[{music_input_idx}:a]volume={music_vol}[music_low];"
                    f"[concat_a][music_low]amix=inputs=2:duration=first:dropout_transition=2[outa]"
                )
                final_filter = "".join(filter_chunks) + concat_filter + mix_music_filter
                map_audio = "[outa]"
            else:
                final_filter = "".join(filter_chunks) + concat_filter
                map_audio = "[concat_a]"

            cmd = [
                FFMPEG_PATH,
                "-y",
                "-i", str(input_video),
            ]

            if has_whoosh:
                cmd.extend(["-i", str(SFX_WHOOSH)])

            if has_music:
                cmd.extend(["-stream_loop", "-1", "-i", str(music_file)])

            cmd.extend([
                "-filter_complex", final_filter,
                "-map", "[concat_v]",
                "-map", map_audio,
                "-c:v", "libx264",
                "-preset", "faster",
                "-crf", "26",
                "-maxrate", "1800k",
                "-bufsize", "3600k",
                "-c:a", "aac",
                "-b:a", "128k",
                str(output_path)
            ])

            process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if process.returncode != 0:
                fallback_cmd = [
                    FFMPEG_PATH, "-y", "-i", str(input_video),
                    "-vf", "scale=-2:720",
                    "-c:v", "libx264", "-crf", "26", "-c:a", "aac", str(output_path)
                ]
                subprocess.run(fallback_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            return output_path

        return await asyncio.to_thread(_render)
