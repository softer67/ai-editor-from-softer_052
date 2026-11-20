import asyncio
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional
from config import FFMPEG_PATH, TEMP_DIR, BASE_DIR

ASSETS_DIR = BASE_DIR / "assets"
SFX_WHOOSH = ASSETS_DIR / "sfx" / "whoosh.wav"
MUSIC_BG = ASSETS_DIR / "music" / "lofi_beat.wav"

class VideoProcessor:
    @staticmethod
    async def cut_silences_and_render(
        input_video: Path,
        silences: List[Dict[str, float]],
        output_name: str = "edited_result.mp4",
        apply_dynamic_zoom: bool = True,
        add_sfx_whoosh: bool = True,
        add_bg_music: bool = False,
        bg_music_volume: float = 0.08
    ) -> Path:
        """
        Монтаж видео:
        1. Вырезает немые паузы речи.
        2. Добавляет динамический зум 1.1x (punch-in) для удержания внимания.
        3. Накладывает звуковой эффект Whoosh на переходах и зумах.
        4. Опционально добавляет мягкую фоновую музыку (Lo-Fi) с авто-балансом громкости.
        5. Оптимизирует под HD 720p для лимита Telegram.
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

        # Вычисляем активные интервалы речи
        active_intervals = []
        last_end = 0.0
        padding = 0.08  # буфер краев речи (чтобы не обрезать согласные)

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

        def _render():
            filter_chunks = []
            concat_inputs = []

            has_whoosh = add_sfx_whoosh and SFX_WHOOSH.exists()
            has_music = add_bg_music and MUSIC_BG.exists()

            # Формируем цепочку фильтров для каждого активного интервала
            for idx, (st, en) in enumerate(active_intervals):
                v_label = f"v{idx}"
                a_label = f"a{idx}"
                chunk_dur = en - st

                # Чередуем зум (каждая вторая склейка)
                is_zoom_cut = apply_dynamic_zoom and (idx % 2 == 1)

                if is_zoom_cut:
                    # Динамический зум 1.1x по центру
                    v_filter = f"[0:v]trim=start={st:.2f}:end={en:.2f},setpts=PTS-STARTPTS,scale=1.1*iw:-1,crop=iw/1.1:ih/1.1,scale=-2:720[{v_label}];"
                else:
                    v_filter = f"[0:v]trim=start={st:.2f}:end={en:.2f},setpts=PTS-STARTPTS,scale=-2:720[{v_label}];"

                # Нарезка аудио
                if is_zoom_cut and has_whoosh:
                    # Подмешиваем звуковой эффект Whoosh в начало склейки
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

            # Склейка всех видео и аудио фрагментов
            concat_filter = f"{''.join(concat_inputs)}concat=n={len(active_intervals)}:v=1:a=1[concat_v][concat_a]"
            
            # Если включена фоновая музыка, подмешиваем ее
            music_input_idx = 2 if has_whoosh else 1
            if has_music:
                mix_music_filter = (
                    f";[{music_input_idx}:a]volume={bg_music_volume}[music_low];"
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
                cmd.extend(["-stream_loop", "-1", "-i", str(MUSIC_BG)])

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
                # Fallback в случае нестандартного аудиоформата
                fallback_cmd = [
                    FFMPEG_PATH, "-y", "-i", str(input_video),
                    "-vf", "scale=-2:720",
                    "-c:v", "libx264", "-crf", "26", "-c:a", "aac", str(output_path)
                ]
                subprocess.run(fallback_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            return output_path

        return await asyncio.to_thread(_render)
