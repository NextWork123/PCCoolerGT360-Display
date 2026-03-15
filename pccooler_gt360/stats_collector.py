"""
System statistics collector for CPU/GPU monitoring.
Uses lm-sensors for temperatures and /proc/stat for CPU usage (no psutil required).
"""

import sys
import time
import subprocess
import re
from typing import Dict, Optional, Tuple, List
from dataclasses import dataclass


@dataclass
class CPUStats:
    """CPU statistics data"""
    usage_percent: float = 0.0
    temperature: Optional[float] = None
    frequency_mhz: Optional[float] = None
    core_count: int = 0
    
    def __str__(self) -> str:
        temp_str = f"{self.temperature:.0f}°C" if self.temperature else "N/A"
        return f"CPU: {self.usage_percent:.0f}% {temp_str}"


@dataclass
class GPUStats:
    """GPU statistics data"""
    usage_percent: float = 0.0
    temperature: Optional[float] = None
    memory_used_mb: Optional[int] = None
    memory_total_mb: Optional[int] = None
    name: str = "GPU"
    
    def __str__(self) -> str:
        temp_str = f"{self.temperature:.0f}°C" if self.temperature else "N/A"
        mem_str = ""
        if self.memory_used_mb and self.memory_total_mb:
            mem_pct = (self.memory_used_mb / self.memory_total_mb) * 100
            mem_str = f" | Mem: {mem_pct:.0f}%"
        return f"{self.name}: {self.usage_percent:.0f}% {temp_str}{mem_str}"


class SystemStatsCollector:
    """Collects system statistics for CPU and GPU using lm-sensors and /proc/stat"""
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self._lm_sensors_available = False
        self._nvidia_available = False
        self._amd_available = False
        self._last_cpu_times = None
        self._last_cpu_time = 0
        
        self._init_lm_sensors()
        self._init_nvidia()
        self._init_amd()
    
    def _init_lm_sensors(self) -> None:
        """Initialize lm-sensors for temperature monitoring"""
        try:
            result = subprocess.run(
                ['sensors', '-v'],
                capture_output=True,
                text=True,
                timeout=2
            )
            if result.returncode == 0:
                self._lm_sensors_available = True
                if self.verbose:
                    print("lm-sensors initialized for temperature monitoring")
            else:
                if self.verbose:
                    print("lm-sensors not available")
        except (FileNotFoundError, subprocess.TimeoutExpired):
            if self.verbose:
                print("lm-sensors not installed: sudo apt install lm-sensors")
    
    def _init_nvidia(self) -> None:
        """Initialize NVIDIA GPU monitoring via nvidia-ml-py"""
        try:
            import pynvml
            pynvml.nvmlInit()
            self._pynvml = pynvml
            self._nvidia_handle = None
            
            # Get first GPU handle
            device_count = pynvml.nvmlDeviceGetCount()
            if device_count > 0:
                self._nvidia_handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                self._nvidia_available = True
                if self.verbose:
                    name = pynvml.nvmlDeviceGetName(self._nvidia_handle)
                    print(f"NVIDIA GPU monitoring initialized: {name}")
            else:
                if self.verbose:
                    print("No NVIDIA GPUs found")
        except ImportError:
            if self.verbose:
                print("nvidia-ml-py not available: pip install nvidia-ml-py")
        except Exception as e:
            if self.verbose:
                print(f"NVIDIA initialization failed: {e}")
    
    def _init_amd(self) -> None:
        """Initialize AMD GPU monitoring (placeholder for future)"""
        self._amd_available = False
    
    def _get_cpu_usage_from_proc(self) -> float:
        """Get CPU usage percentage from /proc/stat (no psutil required)"""
        try:
            with open('/proc/stat', 'r') as f:
                line = f.readline()
                # Line format: cpu  user nice system idle iowait irq softirq steal guest guest_nice
                fields = line.split()
                if fields[0] != 'cpu':
                    return 0.0
                
                # Extract times
                times = [int(x) for x in fields[1:]]
                user, nice, system, idle, iowait, irq, softirq, steal = times[:8]
                
                # Calculate active and total time
                active = user + nice + system + irq + softirq + steal
                total = active + idle + iowait
                
                current_time = time.time()
                
                if self._last_cpu_times is not None:
                    last_active, last_total, last_time = self._last_cpu_times
                    active_delta = active - last_active
                    total_delta = total - last_total
                    time_delta = current_time - last_time
                    
                    if total_delta > 0 and time_delta >= 0.1:
                        usage = (active_delta / total_delta) * 100
                        return min(usage, 100.0)
                
                # Store for next call
                self._last_cpu_times = (active, total, current_time)
                return 0.0  # First call returns 0 (need baseline)
                
        except Exception as e:
            if self.verbose:
                print(f"Error reading /proc/stat: {e}")
            return 0.0
    
    def _get_cpu_temperature_from_sensors(self) -> Optional[float]:
        """Get CPU temperature from lm-sensors"""
        if not self._lm_sensors_available:
            return None
        
        try:
            result = subprocess.run(
                ['sensors', '-u'],
                capture_output=True,
                text=True,
                timeout=2
            )
            
            if result.returncode != 0:
                return None
            
            output = result.stdout
            
            # Try to find CPU temperature from common sensor sections
            # k10temp (AMD), zenpower (AMD), coretemp (Intel), cpu_thermal (ARM)
            cpu_sensor_patterns = [
                (r'(k10temp-.*?)(?=\n\w+-|\Z)', r'Tctl:.*?temp1_input:\s*([0-9.]+)'),
                (r'(k10temp-.*?)(?=\n\w+-|\Z)', r'Tdie:.*?temp1_input:\s*([0-9.]+)'),
                (r'(zenpower-.*?)(?=\n\w+-|\Z)', r'Tctl:.*?temp1_input:\s*([0-9.]+)'),
                (r'(coretemp-.*?)(?=\n\w+-|\Z)', r'Package.*?temp1_input:\s*([0-9.]+)'),
                (r'(coretemp-.*?)(?=\n\w+-|\Z)', r'temp1_input:\s*([0-9.]+)'),
                (r'(cpu_thermal-.*?)(?=\n\w+-|\Z)', r'temp1_input:\s*([0-9.]+)'),
            ]
            
            for section_pattern, temp_pattern in cpu_sensor_patterns:
                section_match = re.search(section_pattern, output, re.DOTALL)
                if section_match:
                    section = section_match.group(1)
                    temp_match = re.search(temp_pattern, section, re.DOTALL)
                    if temp_match:
                        return float(temp_match.group(1))
            
            # Fallback: look for any temp*_input that's reasonable (> 10°C to filter noise)
            temp_matches = re.findall(r'temp([0-9]+)_input:\s*([0-9.]+)', output)
            for _, temp_str in temp_matches:
                temp = float(temp_str)
                if temp > 10:  # Filter out very low values that might be sensor errors
                    return temp
                    
            return None
            
        except Exception as e:
            if self.verbose:
                print(f"Error getting temperature from sensors: {e}")
            return None
    
    def _get_core_count(self) -> int:
        """Get CPU core count from /proc/cpuinfo"""
        try:
            with open('/proc/cpuinfo', 'r') as f:
                content = f.read()
                # Count processor entries
                matches = re.findall(r'^processor\s*:', content, re.MULTILINE)
                return len(matches) if matches else 0
        except:
            return 0
    
    def get_cpu_stats(self) -> CPUStats:
        """Get current CPU statistics using /proc/stat and lm-sensors"""
        try:
            # Get CPU usage from /proc/stat
            usage = self._get_cpu_usage_from_proc()
            
            # Get temperature from lm-sensors
            temp = self._get_cpu_temperature_from_sensors()
            
            # Get core count
            core_count = self._get_core_count()
            
            return CPUStats(
                usage_percent=usage,
                temperature=temp,
                frequency_mhz=None,  # Would need /proc/cpuinfo parsing
                core_count=core_count
            )
        except Exception as e:
            if self.verbose:
                print(f"Error getting CPU stats: {e}")
            return CPUStats(usage_percent=0.0, core_count=0)
    
    def get_gpu_stats(self) -> GPUStats:
        """Get current GPU statistics"""
        if self._nvidia_available:
            return self._get_nvidia_gpu_stats()
        
        # Try to get GPU temperature from lm-sensors if available
        if self._lm_sensors_available:
            temp = self._get_gpu_temperature_from_sensors()
            if temp is not None:
                return GPUStats(usage_percent=0.0, temperature=temp, name="GPU")
        
        return GPUStats(usage_percent=0.0, name="No GPU")
    
    def _get_gpu_temperature_from_sensors(self) -> Optional[float]:
        """Try to get GPU temperature from lm-sensors (for AMD GPUs)"""
        try:
            result = subprocess.run(
                ['sensors', '-u'],
                capture_output=True,
                text=True,
                timeout=2
            )
            
            if result.returncode != 0:
                return None
            
            output = result.stdout
            
            # Look for GPU temperature patterns
            patterns = [
                r'amdgpu-.*?temp1_input.*?([0-9.]+)',
                r'radeon-.*?temp1_input.*?([0-9.]+)',
            ]
            
            for pattern in patterns:
                match = re.search(pattern, output, re.DOTALL)
                if match:
                    return float(match.group(1))
            
            return None
            
        except Exception:
            return None
    
    def _get_nvidia_gpu_stats(self) -> GPUStats:
        """Get NVIDIA GPU statistics"""
        try:
            pynvml = self._pynvml
            handle = self._nvidia_handle
            
            # Get utilization
            util = pynvml.nvmlDeviceGetUtilizationRates(handle)
            usage = util.gpu
            
            # Get temperature
            temp = None
            try:
                temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
            except Exception:
                pass
            
            # Get memory info
            mem_used = None
            mem_total = None
            try:
                mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                mem_used = mem_info.used // (1024 * 1024)
                mem_total = mem_info.total // (1024 * 1024)
            except Exception:
                pass
            
            # Get GPU name
            name = "GPU"
            try:
                name = pynvml.nvmlDeviceGetName(handle)
            except Exception:
                pass
            
            return GPUStats(
                usage_percent=usage,
                temperature=temp,
                memory_used_mb=mem_used,
                memory_total_mb=mem_total,
                name=name[:10]
            )
        except Exception as e:
            if self.verbose:
                print(f"Error getting NVIDIA GPU stats: {e}")
            return GPUStats(usage_percent=0.0, name="GPU Error")
    
    def get_all_stats(self) -> Tuple[CPUStats, GPUStats]:
        """Get both CPU and GPU statistics"""
        return self.get_cpu_stats(), self.get_gpu_stats()
    
    def is_cpu_available(self) -> bool:
        """Check if CPU monitoring is available"""
        return True  # /proc/stat is always available on Linux
    
    def is_gpu_available(self) -> bool:
        """Check if GPU monitoring is available"""
        return self._nvidia_available or self._amd_available


# Convenience function for quick stats
def get_system_stats(verbose: bool = False) -> Dict[str, str]:
    """Quick function to get system stats as strings"""
    collector = SystemStatsCollector(verbose=verbose)
    cpu, gpu = collector.get_all_stats()
    return {
        'cpu': str(cpu),
        'gpu': str(gpu)
    }
