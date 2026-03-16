"""
Video conversion utilities for PCCooler GT360 display.

Handles conversion of GIF and other video formats to display-compatible MP4
using FFmpeg with H.264 encoding.
"""

import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Tuple


class VideoConverter:
    """Convert GIF and other formats to display-compatible MP4 using FFmpeg."""

    # FFmpeg encoding parameters optimized for the display
    DEFAULT_FFMPEG_ARGS = [
        '-c:v', 'libx264',         # H.264 codec
        '-pix_fmt', 'yuv420p',     # Compatible pixel format
        '-movflags', '+faststart', # Web-optimized
        '-tune', 'fastdecode',     # Optimize for decoding speed
        '-profile:v', 'baseline',  # Maximum compatibility
        '-level', '3.0',           # Baseline profile level 3.0
        '-preset', 'fast',         # Balance between speed and compression
        '-crf', '23',              # Quality setting (lower = better quality)
    ]

    def __init__(self, ffmpeg_path: str = 'ffmpeg'):
        """Initialize converter with path to FFmpeg binary."""
        self.ffmpeg_path = ffmpeg_path
        self._ffmpeg_checked = False
        self._ffmpeg_available = False

    def is_available(self) -> bool:
        """Check if FFmpeg is available and working."""
        if self._ffmpeg_checked:
            return self._ffmpeg_available

        try:
            result = subprocess.run(
                [self.ffmpeg_path, '-version'],
                capture_output=True,
                timeout=5,
                check=False
            )
            self._ffmpeg_available = result.returncode == 0
        except (subprocess.SubprocessError, FileNotFoundError, OSError):
            self._ffmpeg_available = False

        self._ffmpeg_checked = True
        return self._ffmpeg_available

    def get_gif_info(self, input_path: str) -> dict:
        """Extract GIF metadata (frames, fps, duration).
        
        Args:
            input_path: Path to the GIF file
            
        Returns:
            Dictionary with 'frames', 'fps', 'duration', 'width', 'height'
        """
        if not self.is_available():
            raise RuntimeError("FFmpeg not available")

        # Use ffprobe if available, otherwise parse ffmpeg output
        ffprobe_path = self.ffmpeg_path.replace('ffmpeg', 'ffprobe')
        
        try:
            # Try ffprobe first for accurate info
            cmd = [
                ffprobe_path,
                '-v', 'error',
                '-select_streams', 'v:0',
                '-show_entries', 'stream=nb_frames,r_frame_rate,width,height',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1',
                input_path
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10,
                check=False
            )
            
            info = {'frames': 0, 'fps': 0.0, 'duration': 0.0, 'width': 0, 'height': 0}
            
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if '=' in line:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip()
                        
                        if key == 'nb_frames':
                            info['frames'] = int(value) if value.isdigit() else 0
                        elif key == 'r_frame_rate' and '/' in value:
                            num, den = value.split('/')
                            info['fps'] = float(num) / float(den) if float(den) != 0 else 0
                        elif key == 'width':
                            info['width'] = int(value) if value.isdigit() else 0
                        elif key == 'height':
                            info['height'] = int(value) if value.isdigit() else 0
                        elif key == 'duration':
                            try:
                                info['duration'] = float(value)
                            except ValueError:
                                pass
            
            return info
            
        except (subprocess.SubprocessError, FileNotFoundError):
            # Fallback: use PIL to get basic info
            try:
                from PIL import Image
                with Image.open(input_path) as gif:
                    info = {
                        'width': gif.width,
                        'height': gif.height,
                        'frames': 0,
                        'fps': 10.0,  # Default GIF fps
                        'duration': 0.0
                    }
                    
                    # Count frames
                    frame_count = 0
                    total_duration = 0
                    try:
                        while True:
                            frame_count += 1
                            # GIF duration is in milliseconds per frame
                            frame_duration = gif.info.get('duration', 100)
                            total_duration += frame_duration
                            gif.seek(gif.tell() + 1)
                    except EOFError:
                        pass
                    
                    info['frames'] = frame_count
                    info['duration'] = total_duration / 1000.0  # Convert to seconds
                    if frame_count > 1 and total_duration > 0:
                        info['fps'] = frame_count / info['duration']
                    
                    return info
            except ImportError:
                raise RuntimeError("Cannot get GIF info: neither ffprobe nor PIL available")

    def gif_to_mp4(
        self,
        input_path: str,
        output_path: str,
        width: int = 640,
        height: int = 480,
        fps: Optional[int] = None,
        maintain_aspect: bool = True
    ) -> None:
        """Convert GIF to H.264 MP4 optimized for display.
        
        Uses nearest neighbor scaling (flags=neighbor) for sharp pixel-perfect
        upscaling of pixel art and low-resolution GIFs.
        
        Args:
            input_path: Path to input GIF file
            output_path: Path for output MP4 file
            width: Target width (default 640)
            height: Target height (default 480)
            fps: Target FPS (None = auto from source, capped at 30)
            maintain_aspect: If True, pad with black to maintain aspect ratio
            
        Raises:
            RuntimeError: If FFmpeg not available or conversion fails
        """
        if not self.is_available():
            raise RuntimeError(
                f"FFmpeg not found at '{self.ffmpeg_path}'. "
                "Install FFmpeg to convert GIF files."
            )

        input_path = Path(input_path)
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")

        # Get GIF info to determine FPS
        gif_info = self.get_gif_info(str(input_path))
        source_fps = gif_info.get('fps', 10.0)
        
        # Cap FPS at 30 for display performance
        if fps is None:
            fps = min(int(source_fps) if source_fps > 0 else 10, 30)
        fps = min(fps, 30)

        # Build filter complex with nearest neighbor scaling
        # Use iw/ih expressions for flexible scaling
        # force_original_aspect_ratio=decrease ensures the image fits within bounds
        # flags=neighbor ensures pixel-perfect sharp scaling
        if maintain_aspect:
            # Scale to fit within dimensions while preserving aspect ratio, then pad
            # Using w/h expressions: min(iw*4,640) would limit to 4x scale or display width
            filter_complex = (
                f"scale={width}:{height}:force_original_aspect_ratio=decrease:flags=neighbor,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,"
                f"fps={fps}"
            )
        else:
            # Stretch to fill
            filter_complex = f"scale={width}:{height}:flags=neighbor,fps={fps}"

        # Build FFmpeg command
        cmd = [
            self.ffmpeg_path,
            '-y',  # Overwrite output
            '-i', str(input_path),
            '-vf', filter_complex,
        ] + self.DEFAULT_FFMPEG_ARGS + [str(output_path)]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,  # Timeout for large GIFs
                check=False
            )
            
            if result.returncode != 0:
                error_msg = result.stderr[-500:] if result.stderr else "Unknown error"
                raise RuntimeError(f"FFmpeg conversion failed: {error_msg}")
                
            # Verify output was created
            output_file = Path(output_path)
            if not output_file.exists() or output_file.stat().st_size == 0:
                raise RuntimeError("FFmpeg produced empty output file")
                
        except subprocess.TimeoutExpired:
            raise RuntimeError("FFmpeg conversion timed out (GIF may be too large)")
        except subprocess.SubprocessError as e:
            raise RuntimeError(f"FFmpeg execution failed: {e}")

    def gif_to_mp4_integer_scale(
        self,
        input_path: str,
        output_path: str,
        scale_factor: int = 4,
        fps: Optional[int] = None,
        max_width: int = 640,
        max_height: int = 480
    ) -> None:
        """Convert GIF to MP4 using exact integer scaling.
        
        Uses iw*scale_factor:ih*scale_factor for pixel-perfect upscaling.
        Result is cropped or padded to fit within max_width x max_height.
        
        Args:
            input_path: Path to input GIF file
            output_path: Path for output MP4 file
            scale_factor: Integer scale multiplier (e.g., 4 for 4x scaling)
            fps: Target FPS (None = auto from source, capped at 30)
            max_width: Maximum output width
            max_height: Maximum output height
            
        Raises:
            RuntimeError: If FFmpeg not available or conversion fails
        """
        if not self.is_available():
            raise RuntimeError(
                f"FFmpeg not found at '{self.ffmpeg_path}'. "
                "Install FFmpeg to convert GIF files."
            )

        input_path = Path(input_path)
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")

        # Get GIF info to determine FPS
        gif_info = self.get_gif_info(str(input_path))
        source_fps = gif_info.get('fps', 10.0)
        
        if fps is None:
            fps = min(int(source_fps) if source_fps > 0 else 10, 30)
        fps = min(fps, 30)

        # Build filter with integer scaling: iw*4:ih*4
        # Then crop or pad to fit within display bounds
        # Note: In FFmpeg expressions, commas must be escaped with \
        filter_complex = (
            f"scale=iw*{scale_factor}:ih*{scale_factor}:flags=neighbor,"
            f"crop=min(iw\\,{max_width}):min(ih\\,{max_height}):"
            f"(iw-min(iw\\,{max_width}))/2:(ih-min(ih\\,{max_height}))/2,"
            f"pad={max_width}:{max_height}:(ow-iw)/2:(oh-ih)/2:black,"
            f"fps={fps}"
        )

        cmd = [
            self.ffmpeg_path,
            '-y',
            '-i', str(input_path),
            '-vf', filter_complex,
        ] + self.DEFAULT_FFMPEG_ARGS + [str(output_path)]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
                check=False
            )
            
            if result.returncode != 0:
                error_msg = result.stderr[-500:] if result.stderr else "Unknown error"
                raise RuntimeError(f"FFmpeg conversion failed: {error_msg}")
                
            output_file = Path(output_path)
            if not output_file.exists() or output_file.stat().st_size == 0:
                raise RuntimeError("FFmpeg produced empty output file")
                
        except subprocess.TimeoutExpired:
            raise RuntimeError("FFmpeg conversion timed out")
        except subprocess.SubprocessError as e:
            raise RuntimeError(f"FFmpeg execution failed: {e}")

    def convert_to_bytes(
        self,
        input_path: str,
        width: int = 640,
        height: int = 480,
        fps: Optional[int] = None
    ) -> bytes:
        """Convert GIF to MP4 and return as bytes.
        
        Uses nearest neighbor scaling for pixel-perfect upscaling.
        
        Args:
            input_path: Path to input GIF file
            width: Target width
            height: Target height
            fps: Target FPS
            
        Returns:
            MP4 file contents as bytes
        """
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmp:
            tmp_path = tmp.name
            
        try:
            self.gif_to_mp4(input_path, tmp_path, width, height, fps)
            with open(tmp_path, 'rb') as f:
                return f.read()
        finally:
            # Cleanup temp file
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    def validate_mp4(self, file_path: str) -> Tuple[bool, str]:
        """Verify MP4 is display-compatible.
        
        Args:
            file_path: Path to MP4 file
            
        Returns:
            Tuple of (is_valid, message)
        """
        if not self.is_available():
            return False, "FFmpeg not available for validation"

        try:
            cmd = [
                self.ffmpeg_path,
                '-v', 'error',
                '-i', file_path,
                '-c', 'copy',
                '-f', 'null',
                '-'
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10,
                check=False
            )
            
            if result.returncode != 0:
                return False, f"Invalid MP4: {result.stderr[:200]}"
                
            # Check codec
            ffprobe_path = self.ffmpeg_path.replace('ffmpeg', 'ffprobe')
            codec_cmd = [
                ffprobe_path,
                '-v', 'error',
                '-select_streams', 'v:0',
                '-show_entries', 'stream=codec_name',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                file_path
            ]
            
            codec_result = subprocess.run(
                codec_cmd,
                capture_output=True,
                text=True,
                timeout=5,
                check=False
            )
            
            codec = codec_result.stdout.strip().lower()
            if codec != 'h264':
                return False, f"Codec is {codec}, expected h264"
                
            return True, "Valid H.264 MP4"
            
        except subprocess.SubprocessError as e:
            return False, f"Validation failed: {e}"


def is_ffmpeg_available(ffmpeg_path: str = 'ffmpeg') -> bool:
    """Quick check if FFmpeg is available.
    
    Args:
        ffmpeg_path: Path to FFmpeg binary (default: 'ffmpeg')
        
    Returns:
        True if FFmpeg is available and working
    """
    try:
        result = subprocess.run(
            [ffmpeg_path, '-version'],
            capture_output=True,
            timeout=5,
            check=False
        )
        return result.returncode == 0
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return False
