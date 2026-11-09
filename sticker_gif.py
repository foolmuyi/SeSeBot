import asyncio
import gzip
import logging
import math
import shutil
import sys
import tempfile
from pathlib import Path


MAX_STICKER_BYTES = 8 * 1024 * 1024
MAX_GIF_BYTES = 40 * 1024 * 1024
CONVERSION_TIMEOUT = 45
GIF_FPS = 25
logger = logging.getLogger(__name__)


async def sticker_to_gif(data, sticker_format):
    if sticker_format not in {"webp", "tgs", "webm"}:
        raise ValueError("Unsupported sticker format")
    if not data or len(data) > MAX_STICKER_BYTES:
        raise ValueError("Sticker must be non-empty and no larger than 8 MB")

    with tempfile.TemporaryDirectory(prefix="sesebot-sticker-") as directory:
        source = Path(directory) / f"sticker.{sticker_format}"
        output = Path(directory) / "sticker.gif"
        source.write_bytes(data)
        if sticker_format == "webm":
            ffmpeg = shutil.which("ffmpeg")
            if not ffmpeg:
                raise RuntimeError("Video stickers require FFmpeg; install it on the bot server")
            command = [
                ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                "-threads", "1", "-c:v", "libvpx-vp9", "-i", str(source),
                "-t", "10", "-an", "-filter_complex_threads", "1", "-filter_complex",
                f"fps={GIF_FPS},scale=w='min(512,iw)':h='min(512,ih)':"
                "force_original_aspect_ratio=decrease:flags=lanczos,"
                "split[a][b];[a]palettegen=reserve_transparent=1[p];"
                "[b][p]paletteuse=dither=sierra2_4a:alpha_threshold=128",
                "-loop", "0", str(output),
            ]
        else:
            command = [sys.executable, str(Path(__file__).resolve()), sticker_format, str(source), str(output)]

        process = await asyncio.create_subprocess_exec(
            *command, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
        )
        communication = asyncio.create_task(process.communicate())
        try:
            _, stderr = await asyncio.wait_for(asyncio.shield(communication), CONVERSION_TIMEOUT)
        except (asyncio.TimeoutError, asyncio.CancelledError) as exc:
            if process.returncode is None:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
            await communication
            if isinstance(exc, asyncio.CancelledError):
                raise
            raise RuntimeError("Sticker conversion timed out; please try a different sticker") from exc
        if process.returncode:
            details = stderr.decode("utf-8", errors="replace").strip()
            logger.error("Sticker conversion failed (%s): %s", sticker_format, details[-2000:])
            if "No module named 'rlottie_python'" in details:
                raise RuntimeError("Animated stickers require rlottie-python; install the updated requirements")
            raise RuntimeError("Could not convert this sticker to GIF")
        if not output.is_file() or not 0 < output.stat().st_size <= MAX_GIF_BYTES:
            raise ValueError("Converted GIF is empty or exceeds 40 MB")
        result = output.read_bytes()
        if not result.startswith((b"GIF87a", b"GIF89a")):
            raise ValueError("Converter did not produce a GIF")
        return result


def _render_image(source, output, sticker_format):
    from PIL import Image

    if sticker_format == "webp":
        with Image.open(source) as image:
            image = image.convert("RGBA")
            image.thumbnail((512, 512), Image.Resampling.LANCZOS)
            image.save(output, format="GIF", disposal=2)
        return

    from rlottie_python import LottieAnimation

    with gzip.open(source, "rb") as compressed:
        raw = compressed.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024:
        raise ValueError("TGS animation data is too large")
    with LottieAnimation.from_data(raw.decode("utf-8")) as animation:
        width, height = animation.lottie_animation_get_size()
        duration = animation.lottie_animation_get_duration()
        fps = animation.lottie_animation_get_framerate()
        if not width or not height or not math.isfinite(duration) or not 0 < duration <= 10:
            raise ValueError("Invalid sticker dimensions or duration")
        if not math.isfinite(fps) or fps <= 0:
            raise ValueError("Invalid sticker frame rate")
        scale = min(1, 512 / max(width, height))
        animation.save_animation(
            str(output), fps=min(GIF_FPS, fps),
            width=max(1, round(width * scale)), height=max(1, round(height * scale)),
        )


if __name__ == "__main__":
    _render_image(Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[1])
