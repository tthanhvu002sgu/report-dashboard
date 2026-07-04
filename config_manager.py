"""
========================================================================================
MODULE QUẢN LÝ CẤU HÌNH & ÁNH XẠ CHIẾN LƯỢC (CONFIG MANAGER)
========================================================================================
Quản lý việc đọc, ghi, và ánh xạ Magic Number sang tên chiến lược nhân xưng, màu sắc,
và cấu hình chung của ứng dụng MT5 Strategy Performance Analyzer.
========================================================================================
"""

import os
import json
from typing import Dict, Any, Optional

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "strategy_config.json")

# Danh sách bảng màu mặc định cực kỳ sang trọng cho các chiến lược mới phát hiện
DEFAULT_COLORS = [
    "#38bdf8",  # Sky Blue
    "#818cf8",  # Indigo
    "#f43f5e",  # Rose
    "#10b981",  # Emerald
    "#f97316",  # Orange
    "#a855f7",  # Purple
    "#ec4899",  # Pink
    "#eab308",  # Yellow
    "#06b6d4",  # Cyan
    "#64748b"   # Slate
]

class ConfigManager:
    def __init__(self, config_path: str = CONFIG_FILE):
        self.config_path = config_path
        self.data = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """Tải cấu hình từ file JSON. Nếu file chưa tồn tại hoặc lỗi, tạo mặc định."""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"[WARN] Lỗi đọc file config ({e}), sử dụng cấu hình mặc định.")
        
        default_config = {
            "strategies": {
                "0": {
                    "name": "Manual / Unassigned Trading",
                    "description": "Giao dịch thủ công hoặc lệnh không gán Magic Number.",
                    "color": "#94a3b8"
                }
            },
            "settings": {
                "default_time_range": "this_week",
                "risk_free_rate_pct": 5.0,
                "initial_capital": 10000.0,
                "theme": "dark_glass"
            }
        }
        self.save_config(default_config)
        return default_config

    def save_config(self, data: Optional[Dict[str, Any]] = None) -> bool:
        """Lưu cấu hình xuống file JSON."""
        if data is not None:
            self.data = data
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"[ERROR] Không thể lưu config: {e}")
            return False

    def get_strategy_info(self, magic_number: int) -> Dict[str, str]:
        """Lấy thông tin (tên, mô tả, màu sắc) của một Magic Number."""
        magic_str = str(magic_number)
        strategies = self.data.get("strategies", {})
        
        if magic_str in strategies:
            return strategies[magic_str]
        
        # Nếu chưa có trong config, tạo mặc định tự động
        color_idx = abs(int(magic_number)) % len(DEFAULT_COLORS)
        new_info = {
            "name": f"Strategy #{magic_number}" if magic_number != 0 else "Manual Trading",
            "description": f"Chiến lược tự động nhận diện từ Magic Number {magic_number}",
            "color": DEFAULT_COLORS[color_idx]
        }
        self.data["strategies"][magic_str] = new_info
        self.save_config()
        return new_info

    def update_strategy_info(self, magic_number: int, name: str, description: str = "", color: Optional[str] = None) -> bool:
        """Cập nhật tên và mô tả cho chiến lược từ giao diện Dashboard."""
        magic_str = str(magic_number)
        if "strategies" not in self.data:
            self.data["strategies"] = {}
        
        current_info = self.data["strategies"].get(magic_str, {})
        current_info["name"] = name
        if description:
            current_info["description"] = description
        if color:
            current_info["color"] = color
        elif "color" not in current_info:
            color_idx = abs(int(magic_number)) % len(DEFAULT_COLORS)
            current_info["color"] = DEFAULT_COLORS[color_idx]
            
        self.data["strategies"][magic_str] = current_info
        return self.save_config()

    def get_all_strategies(self) -> Dict[str, Dict[str, str]]:
        """Lấy toàn bộ danh sách chiến lược đã ánh xạ."""
        return self.data.get("strategies", {})

    def get_settings(self) -> Dict[str, Any]:
        """Lấy các cài đặt chung."""
        return self.data.get("settings", {})

    def update_setting(self, key: str, value: Any) -> bool:
        """Cập nhật một cài đặt chung."""
        if "settings" not in self.data:
            self.data["settings"] = {}
        self.data["settings"][key] = value
        return self.save_config()

# Instance mặc định toàn cục
config_mgr = ConfigManager()
