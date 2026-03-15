"""Configuration management for PCCooler GT360 display.

Provides centralized configuration with validation and defaults.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, asdict
from typing import Optional, List


@dataclass
class DisplayConfig:
    """Display hardware settings."""
    resolution: str = "640x480"
    brightness: int = 100
    orientation: int = 0
    timeout: Optional[int] = None
    
    def __post_init__(self) -> None:
        self.validate()
    
    def validate(self) -> None:
        """Validate display settings."""
        if self.resolution not in ("640x480", "480x320"):
            raise ValueError(f"Invalid resolution: {self.resolution}")
        if not 0 <= self.brightness <= 100:
            raise ValueError(f"Brightness must be 0-100: {self.brightness}")
        if self.orientation not in (0, 90, 180, 270):
            raise ValueError(f"Orientation must be 0/90/180/270: {self.orientation}")


@dataclass
class TransferConfig:
    """USB/Serial transfer settings."""
    chunk_delay: float = 0.001
    chunk_size: int = 0  # 0 = adaptive/device default
    max_retries: int = 10
    compress: bool = False
    compress_level: int = 6
    adaptive: bool = True
    fast_mode: bool = False
    
    def __post_init__(self) -> None:
        self.validate()
    
    def validate(self) -> None:
        """Validate transfer settings."""
        if self.chunk_delay < 0:
            raise ValueError(f"chunk_delay must be >= 0: {self.chunk_delay}")
        if not 0 <= self.compress_level <= 9:
            raise ValueError(f"compress_level must be 0-9: {self.compress_level}")
        if self.max_retries < 1:
            raise ValueError(f"max_retries must be >= 1: {self.max_retries}")


@dataclass
class ScreensaverConfig:
    """Screensaver animation settings."""
    type: str = "bounce"
    quality: int = 60
    scale: float = 1.0
    fps: float = 0.0  # 0 = uncapped
    max_failures: int = 5
    
    VALID_TYPES: List[str] = field(default_factory=lambda: [
        "bounce", "mystify", "starfield", "pipes", "catpipes"
    ])
    
    def __post_init__(self) -> None:
        self.validate()
    
    def validate(self) -> None:
        """Validate screensaver settings."""
        if self.type not in self.VALID_TYPES:
            raise ValueError(f"Invalid screensaver type: {self.type}. "
                           f"Valid: {', '.join(self.VALID_TYPES)}")
        if not 1 <= self.quality <= 95:
            raise ValueError(f"quality must be 1-95: {self.quality}")
        if not 0.25 <= self.scale <= 1.0:
            raise ValueError(f"scale must be 0.25-1.0: {self.scale}")
        if self.fps < 0:
            raise ValueError(f"fps must be >= 0: {self.fps}")


@dataclass
class LoggingConfig:
    """Logging configuration."""
    verbose: bool = False
    level: str = "INFO"
    file: Optional[str] = None
    max_bytes: int = 10 * 1024 * 1024  # 10MB
    backup_count: int = 3
    
    VALID_LEVELS: List[str] = field(default_factory=lambda: [
        "DEBUG", "INFO", "WARN", "ERROR"
    ])
    
    def __post_init__(self) -> None:
        self.validate()
    
    def validate(self) -> None:
        """Validate logging settings."""
        if self.level not in self.VALID_LEVELS:
            raise ValueError(f"Invalid log level: {self.level}")


@dataclass
class Config:
    """Main configuration container."""
    display: DisplayConfig = field(default_factory=DisplayConfig)
    transfer: TransferConfig = field(default_factory=TransferConfig)
    screensaver: ScreensaverConfig = field(default_factory=ScreensaverConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    
    @classmethod
    def from_env(cls) -> Config:
        """Create configuration from environment variables.
        
        Environment variables:
            PCCOOLER_RESOLUTION - Display resolution (640x480 or 480x320)
            PCCOOLER_BRIGHTNESS - Default brightness (0-100)
            PCCOOLER_CHUNK_DELAY - Transfer chunk delay in seconds
            PCCOOLER_VERBOSE - Enable verbose logging (1/true/yes)
            PCCOOLER_LOG_FILE - Log file path
        """
        display = DisplayConfig(
            resolution=os.getenv("PCCOOLER_RESOLUTION", "640x480"),
            brightness=int(os.getenv("PCCOOLER_BRIGHTNESS", "100")),
        )
        
        transfer = TransferConfig(
            chunk_delay=float(os.getenv("PCCOOLER_CHUNK_DELAY", "0.001")),
            verbose=os.getenv("PCCOOLER_VERBOSE", "").lower() in ("1", "true", "yes"),
        )
        
        logging_cfg = LoggingConfig(
            verbose=transfer.verbose,
            file=os.getenv("PCCOOLER_LOG_FILE"),
        )
        
        return cls(
            display=display,
            transfer=transfer,
            logging=logging_cfg,
        )
    
    def validate(self) -> None:
        """Validate all configuration sections."""
        self.display.validate()
        self.transfer.validate()
        self.screensaver.validate()
        self.logging.validate()
    
    def to_dict(self) -> dict:
        """Convert configuration to dictionary."""
        return asdict(self)


# Global configuration instance
_config: Optional[Config] = None


def get_config() -> Config:
    """Get the global configuration instance.
    
    Creates default config on first call.
    """
    global _config
    if _config is None:
        _config = Config.from_env()
    return _config


def set_config(config: Config) -> None:
    """Set the global configuration instance."""
    global _config
    config.validate()
    _config = config
