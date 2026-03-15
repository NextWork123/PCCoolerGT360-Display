"""
Overlay rendering system for PCCooler GT360 display.
Provides dynamic CPU/GPU statistics overlay on base images.
"""

import sys
import time
import io
from typing import Optional, Tuple
from dataclasses import dataclass
from enum import Enum

# PIL imports
from PIL import Image, ImageDraw, ImageFont

from .stats_collector import SystemStatsCollector, CPUStats, GPUStats
from .constants import DISPLAY_WIDTH, DISPLAY_HEIGHT


class OverlayPosition(Enum):
    """Position options for overlay"""
    TOP_LEFT = "top-left"
    TOP_RIGHT = "top-right"
    BOTTOM_LEFT = "bottom-left"
    BOTTOM_RIGHT = "bottom-right"
    TOP_CENTER = "top-center"
    BOTTOM_CENTER = "bottom-center"


@dataclass
class OverlayConfig:
    """Configuration for overlay rendering"""
    position: OverlayPosition = OverlayPosition.TOP_RIGHT
    background_color: Tuple[int, int, int, int] = (0, 0, 0, 160)  # Semi-transparent black
    text_color: Tuple[int, int, int] = (255, 255, 255)  # White
    accent_color: Tuple[int, int, int] = (0, 255, 128)  # Green accent
    warning_color: Tuple[int, int, int] = (255, 165, 0)  # Orange warning
    danger_color: Tuple[int, int, int] = (255, 64, 64)  # Red danger
    font_size: int = 16
    padding: int = 10
    line_spacing: int = 4
    show_cpu: bool = True
    show_gpu: bool = True
    show_labels: bool = True
    show_temperature: bool = True
    show_memory: bool = True
    min_width: int = 120


class OverlayRenderer:
    """
    Renders dynamic overlays with CPU/GPU statistics on base images.
    
    Usage:
        renderer = OverlayRenderer(base_image, config)
        final_image = renderer.render(cpu_stats, gpu_stats)
    """
    
    def __init__(
        self,
        base_image: Image.Image,
        config: Optional[OverlayConfig] = None,
        verbose: bool = False
    ):
        """
        Initialize overlay renderer.
        
        Args:
            base_image: PIL Image to use as base (will be cached)
            config: Overlay configuration (uses defaults if None)
            verbose: Enable verbose output
        """
        self.verbose = verbose
        self.config = config or OverlayConfig()
        
        # Cache the base image
        self.base_image = base_image.convert("RGBA")
        self.width, self.height = self.base_image.size
        
        # Initialize fonts
        self._init_fonts()
        
        # Stats collector (optional - can pass stats directly)
        self._stats_collector: Optional[SystemStatsCollector] = None
        
        # Cache for overlay layer
        self._overlay_layer: Optional[Image.Image] = None
        self._last_stats_hash: Optional[str] = None
        
        # Pre-heat stats collector to get baseline CPU reading
        self._preheat_stats()
    
    def _preheat_stats(self) -> None:
        """Initialize stats collector and get baseline reading"""
        import time
        try:
            self._stats_collector = SystemStatsCollector(verbose=self.verbose)
            # First call to cpu_percent returns 0 (needs baseline), second call gives real value
            self._stats_collector.get_cpu_stats()
            time.sleep(0.1)  # Short delay for baseline
            self._stats_collector.get_cpu_stats()
            if self.verbose:
                print("Stats collector pre-heated")
        except Exception as e:
            if self.verbose:
                print(f"Stats pre-heat failed: {e}")
    
    def _init_fonts(self) -> None:
        """Initialize fonts for rendering"""
        from .utils import load_system_fonts
        
        font_size = self.config.font_size
        fonts = load_system_fonts([font_size, font_size])
        
        self.font = fonts[0]
        self.font_bold = fonts[1] if len(fonts) > 1 else fonts[0]
        
        # If we only got one font, use it for both
        if self.font_bold is None:
            self.font_bold = self.font
    
    def _get_color_for_usage(self, usage: float) -> Tuple[int, int, int]:
        """Get color based on usage percentage"""
        if usage >= 90:
            return self.config.danger_color
        elif usage >= 70:
            return self.config.warning_color
        return self.config.accent_color
    
    def _format_stat_line(
        self,
        label: str,
        usage: float,
        temp: Optional[float],
        mem_used: Optional[int] = None,
        mem_total: Optional[int] = None
    ) -> str:
        """Format a stat line for display"""
        parts = [label]
        
        if self.config.show_labels:
            parts.append(f"{usage:.0f}%")
        else:
            parts.append(f"{usage:.0f}")
        
        if self.config.show_temperature and temp is not None:
            parts.append(f"{temp:.0f}°")
        
        if self.config.show_memory and mem_used is not None and mem_total is not None:
            mem_pct = (mem_used / mem_total) * 100
            parts.append(f"{mem_pct:.0f}M")
        
        return " ".join(parts)
    
    def _calculate_overlay_size(self, cpu: CPUStats, gpu: GPUStats) -> Tuple[int, int]:
        """Calculate the size needed for the overlay box"""
        dummy_draw = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
        max_width = 0
        line_count = 0
        
        # CPU line estimation
        if self.config.show_cpu:
            # Estimate: "CPU: 100% 100°" (worst case)
            text = "CPU: 100% 100°"
            bbox = dummy_draw.textbbox((0, 0), text, font=self.font)
            max_width = max(max_width, bbox[2] - bbox[0])
            line_count += 1
        
        # GPU line estimation
        if self.config.show_gpu:
            # Estimate: "GPU: 100% 100° 100M" (worst case)
            text = "GPU: 100% 100° 100M"
            bbox = dummy_draw.textbbox((0, 0), text, font=self.font)
            max_width = max(max_width, bbox[2] - bbox[0])
            line_count += 1
        
        if line_count == 0:
            return 0, 0
        
        # Calculate total height
        line_height = self.config.font_size
        total_height = line_count * (line_height + self.config.line_spacing) + self.config.padding * 2 - self.config.line_spacing
        
        # Add padding to width
        max_width += self.config.padding * 2
        
        # Enforce minimum width
        max_width = max(max_width, self.config.min_width)
        
        return max_width, total_height
    
    def _get_position_coordinates(
        self,
        overlay_width: int,
        overlay_height: int
    ) -> Tuple[int, int]:
        """Calculate overlay position based on configuration"""
        padding = self.config.padding
        pos = self.config.position
        
        if pos == OverlayPosition.TOP_LEFT:
            return padding, padding
        elif pos == OverlayPosition.TOP_RIGHT:
            return self.width - overlay_width - padding, padding
        elif pos == OverlayPosition.BOTTOM_LEFT:
            return padding, self.height - overlay_height - padding
        elif pos == OverlayPosition.BOTTOM_RIGHT:
            return (
                self.width - overlay_width - padding,
                self.height - overlay_height - padding
            )
        elif pos == OverlayPosition.TOP_CENTER:
            return (self.width - overlay_width) // 2, padding
        elif pos == OverlayPosition.BOTTOM_CENTER:
            return (self.width - overlay_width) // 2, self.height - overlay_height - padding
        
        return padding, padding  # Default
    
    def render(
        self,
        cpu_stats: Optional[CPUStats] = None,
        gpu_stats: Optional[GPUStats] = None
    ) -> Image.Image:
        """
        Render the final image with overlay.
        
        Args:
            cpu_stats: CPU statistics (will collect if None)
            gpu_stats: GPU statistics (will collect if None)
        
        Returns:
            PIL Image with overlay rendered
        """
        # Collect stats if not provided
        if cpu_stats is None or gpu_stats is None:
            if self._stats_collector is None:
                self._stats_collector = SystemStatsCollector(verbose=self.verbose)
            
            if cpu_stats is None:
                cpu_stats = self._stats_collector.get_cpu_stats()
                if self.verbose:
                    print(f"  CPU: {cpu_stats.usage_percent:.1f}%, Temp: {cpu_stats.temperature}")
            if gpu_stats is None:
                gpu_stats = self._stats_collector.get_gpu_stats()
                if self.verbose:
                    print(f"  GPU: {gpu_stats.usage_percent:.1f}%, Temp: {gpu_stats.temperature}")
        
        # Start with base image copy
        result = self.base_image.copy()
        
        # Calculate overlay size
        overlay_width, overlay_height = self._calculate_overlay_size(cpu_stats, gpu_stats)
        
        if overlay_width == 0 or overlay_height == 0:
            return result
        
        # Create overlay layer
        overlay = Image.new("RGBA", (overlay_width, overlay_height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        
        # Draw background
        bg_color = self.config.background_color
        draw.rectangle(
            [(0, 0), (overlay_width - 1, overlay_height - 1)],
            fill=bg_color,
            outline=(255, 255, 255, 64),
            width=1
        )
        
        # Draw text lines
        x = self.config.padding
        y = self.config.padding
        
        # Helper to draw label + value with different colors
        def draw_stat_line(label, value, temp=None, mem_used=None, mem_total=None):
            nonlocal y
            
            # Draw label
            draw.text((x, y), label, font=self.font, fill=self.config.text_color)
            label_bbox = draw.textbbox((x, y), label, font=self.font)
            value_x = label_bbox[2] + 4  # Small gap
            
            # Draw value in color based on usage
            color = self._get_color_for_usage(value)
            value_text = f"{value:.0f}%"
            draw.text((value_x, y), value_text, font=self.font, fill=color)
            value_bbox = draw.textbbox((value_x, y), value_text, font=self.font)
            
            # Draw temperature if available
            next_x = value_bbox[2] + 8  # Gap
            if self.config.show_temperature and temp is not None:
                temp_text = f" {temp:.0f}°"
                draw.text((next_x, y), temp_text, font=self.font, fill=self.config.text_color)
                next_x = draw.textbbox((next_x, y), temp_text, font=self.font)[2] + 8
            
            # Draw memory if available
            if self.config.show_memory and mem_used is not None and mem_total is not None:
                mem_pct = (mem_used / mem_total) * 100
                mem_text = f" {mem_pct:.0f}M"
                draw.text((next_x, y), mem_text, font=self.font, fill=self.config.text_color)
            
            y += self.config.font_size + self.config.line_spacing
        
        # Draw CPU line (show even if 0%, but mark as N/A if truly unavailable)
        if self.config.show_cpu and cpu_stats:
            usage = cpu_stats.usage_percent
            # If usage is 0 and we have no temperature, likely psutil isn't working
            if usage == 0 and cpu_stats.temperature is None and cpu_stats.core_count == 0:
                # Draw N/A
                draw.text((x, y), "CPU: N/A", font=self.font, fill=self.config.text_color)
                y += self.config.font_size + self.config.line_spacing
            else:
                draw_stat_line("CPU:", usage, cpu_stats.temperature)
        
        # Draw GPU line
        if self.config.show_gpu and gpu_stats:
            usage = gpu_stats.usage_percent
            # Check if GPU monitoring is actually working
            if usage == 0 and gpu_stats.temperature is None and gpu_stats.name in ("No GPU", "GPU Error"):
                draw.text((x, y), "GPU: N/A", font=self.font, fill=self.config.text_color)
                y += self.config.font_size + self.config.line_spacing
            else:
                draw_stat_line(
                    "GPU:",
                    usage,
                    gpu_stats.temperature,
                    gpu_stats.memory_used_mb,
                    gpu_stats.memory_total_mb
                )
        
        # Calculate position and composite
        pos_x, pos_y = self._get_position_coordinates(overlay_width, overlay_height)
        result.paste(overlay, (pos_x, pos_y), overlay)
        
        return result
    
    def render_to_bytes(
        self,
        cpu_stats: Optional[CPUStats] = None,
        gpu_stats: Optional[GPUStats] = None,
        format: str = "JPEG",
        quality: int = 85
    ) -> bytes:
        """
        Render and encode to bytes for direct transfer.
        
        Args:
            cpu_stats: CPU statistics
            gpu_stats: GPU statistics
            format: Output format (JPEG, PNG)
            quality: JPEG quality (1-100)
        
        Returns:
            Encoded image bytes
        """
        img = self.render(cpu_stats, gpu_stats)
        

        buf = io.BytesIO()
        
        if format.upper() == "JPEG":
            img.convert("RGB").save(buf, format="JPEG", quality=quality, optimize=True)
        elif format.upper() == "PNG":
            img.save(buf, format="PNG", optimize=True)
        else:
            img.convert("RGB").save(buf, format=format)
        
        return buf.getvalue()
    
    def update_base_image(self, new_base_image: Image.Image) -> None:
        """Update the cached base image"""
        self.base_image = new_base_image.convert("RGBA")
        self.width, self.height = self.base_image.size


def create_overlay_renderer(
    base_image_path: Optional[str] = None,
    width: int = DISPLAY_WIDTH,
    height: int = DISPLAY_HEIGHT,
    position: str = "top-right",
    show_cpu: bool = True,
    show_gpu: bool = True,
    verbose: bool = False
) -> OverlayRenderer:
    """
    Convenience function to create an OverlayRenderer.
    
    Args:
        base_image_path: Path to base image (creates black background if None)
        width: Image width if no base image
        height: Image height if no base image
        position: Overlay position (top-left, top-right, bottom-left, bottom-right)
        show_cpu: Show CPU stats
        show_gpu: Show GPU stats
        verbose: Enable verbose output
    
    Returns:
        Configured OverlayRenderer instance
    """
    # Load or create base image
    if base_image_path:
        from .image_processor import ImageProcessor
        base_img = ImageProcessor.load_image(base_image_path, width, height)
    else:
        base_img = Image.new("RGBA", (width, height), (20, 20, 40, 255))
    
    # Parse position
    pos_map = {
        "top-left": OverlayPosition.TOP_LEFT,
        "top-right": OverlayPosition.TOP_RIGHT,
        "bottom-left": OverlayPosition.BOTTOM_LEFT,
        "bottom-right": OverlayPosition.BOTTOM_RIGHT,
        "top-center": OverlayPosition.TOP_CENTER,
        "bottom-center": OverlayPosition.BOTTOM_CENTER,
    }
    position_enum = pos_map.get(position, OverlayPosition.TOP_RIGHT)
    
    config = OverlayConfig(
        position=position_enum,
        show_cpu=show_cpu,
        show_gpu=show_gpu
    )
    
    return OverlayRenderer(base_img, config, verbose=verbose)
