"""
========================================================================================
MODULE MÁY CHỦ WEB API BACKEND (FASTAPI SERVER)
========================================================================================
Cung cấp REST API cho Dashboard:
  - Kết nối MT5 Live & Upload báo cáo từ VPS.
  - Bộ lọc thời gian (Mặc định: Tuần này - This Week).
  - Phân tích tổng quan Portfolio & Drill-down chi tiết theo Magic Number.
========================================================================================
"""

import os
import sys
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass
import json
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from mt5_extractor import extractor
from metrics_engine import compute_metrics, sanitize_json_floats
from config_manager import config_mgr

app = FastAPI(title="MT5 Quantitative Strategy Analyzer", version="2.0.0")

# CORS middleware cho phép frontend gọi thoải mái
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Bộ nhớ tạm lưu trữ danh sách lệnh đang chọn (từ Live hoặc từ file Upload VPS)
app_state = {
    "data_source": "offline",  # 'mt5_live' hoặc 'uploaded_file'
    "uploaded_filename": "Chưa tải file báo cáo VPS",
    "uploaded_content": None,
    "current_trades": [],
    "parsed_all_time_trades": None
}

# Thư mục chứa giao diện tĩnh
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
if not os.path.exists(STATIC_DIR):
    os.makedirs(STATIC_DIR)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Tự động đọc file mt5_deal_history.csv nếu có sẵn trong thư mục khi khởi động
try:
    default_csv = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mt5_deal_history.csv")
    if os.path.exists(default_csv):
        with open(default_csv, "rb") as f:
            content = f.read()
        trades = extractor.parse_uploaded_file(content, "mt5_deal_history.csv", time_option="all_time")
        trades = sanitize_json_floats(trades)
        app_state["uploaded_content"] = content
        app_state["uploaded_filename"] = "mt5_deal_history.csv"
        app_state["data_source"] = "uploaded_file"
        app_state["current_trades"] = trades
        app_state["parsed_all_time_trades"] = trades
        print(f"✅ [STARTUP] Đã tự động tải file mt5_deal_history.csv với {len(trades)} lệnh vào bộ nhớ!")
except Exception as e:
    print(f"⚠️ [STARTUP] Không thể tự động đọc file mt5_deal_history.csv: {e}")


@app.get("/", response_class=HTMLResponse)
async def serve_index():
    """Phục vụ trang chủ Dashboard."""
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>MT5 Strategy Analyzer - Vui lòng tạo file index.html trong thư mục static/</h1>"


@app.get("/api/status")
async def get_status():
    """Lấy trạng thái kết nối và nguồn dữ liệu hiện tại."""
    return {
        "data_source": app_state["data_source"],
        "mt5_connected": extractor.connected,
        "account_info": extractor.account_info,
        "uploaded_filename": app_state["uploaded_filename"],
        "trade_count": len(app_state["current_trades"]),
        "time_options": [
            {"id": "this_week", "label": "Tuần này (This Week - Mặc định)"},
            {"id": "today", "label": "Hôm nay (Today)"},
            {"id": "yesterday", "label": "Hôm qua (Yesterday)"},
            {"id": "last_week", "label": "Tuần trước (Last Week)"},
            {"id": "this_month", "label": "Tháng này (This Month)"},
            {"id": "last_month", "label": "Tháng trước (Last Month)"},
            {"id": "this_quarter", "label": "Quý này (This Quarter)"},
            {"id": "this_year", "label": "Năm nay (This Year)"},
            {"id": "all_time", "label": "Toàn bộ thời gian (All Time)"},
            {"id": "custom", "label": "Tùy chỉnh ngày (Custom Range)"}
        ],
        "default_time_range": config_mgr.get_settings().get("default_time_range", "this_week")
    }


@app.post("/api/connect_mt5")
async def connect_mt5():
    """Kết nối tới MT5 Terminal đang chạy trên máy (nếu có)."""
    success, msg = extractor.connect_mt5()
    if success:
        app_state["data_source"] = "mt5_live"
        return {"success": True, "message": msg, "account_info": extractor.account_info}
    else:
        return {"success": False, "message": msg}


@app.post("/api/disconnect_mt5")
async def disconnect_mt5():
    """Ngắt kết nối MT5."""
    extractor.disconnect_mt5()
    app_state["data_source"] = "offline"
    return {"success": True, "message": "Đã ngắt kết nối MT5."}


@app.post("/api/upload_report")
async def upload_report(request: Request, file: Optional[UploadFile] = None):
    """
    Xử lý file báo cáo tải lên từ VPS (hỗ trợ kéo thả giao diện multipart và gọi raw WebRequest từ MT5).
    """
    try:
        content_type = request.headers.get("content-type", "")
        filename = "uploaded_report.csv"
        
        if "multipart/form-data" in content_type:
            if file is None:
                raise HTTPException(status_code=400, detail="Không tìm thấy file tải lên.")
            content = await file.read()
            filename = file.filename
        else:
            # Nhận raw body (ví dụ từ WebRequest MT5)
            content = await request.body()
            filename = request.query_params.get("filename", "mt5_deal_history.csv")
            
        if not content:
            raise HTTPException(status_code=400, detail="Nội dung báo cáo trống.")
            
        # Thử parse ngay để kiểm tra định dạng
        trades = extractor.parse_uploaded_file(content, filename, time_option="all_time")
        trades = sanitize_json_floats(trades)
        
        app_state["uploaded_content"] = content
        app_state["uploaded_filename"] = filename
        app_state["data_source"] = "uploaded_file"
        app_state["current_trades"] = trades
        app_state["parsed_all_time_trades"] = trades
        
        return {
            "success": True,
            "message": f"Đã đọc thành công báo cáo VPS '{filename}' với {len(trades)} lệnh giao dịch!",
            "trade_count": len(trades)
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


def _get_trades_by_filter(time_option: str, custom_start: Optional[str] = None, custom_end: Optional[str] = None) -> List[Dict[str, Any]]:
    """Helper lấy lệnh theo nguồn hiện tại và bộ lọc thời gian."""
    res = []
    if app_state["data_source"] == "mt5_live" and extractor.connected:
        try:
            res = extractor.fetch_live_deals(time_option, custom_start, custom_end)
        except Exception as e:
            print(f"[ERROR] Lỗi lấy lệnh live: {e}")
            res = []
    elif app_state["data_source"] == "uploaded_file" and app_state.get("parsed_all_time_trades") is not None:
        try:
            res = extractor.filter_trades_by_time(
                app_state["parsed_all_time_trades"],
                time_option, custom_start, custom_end
            )
        except Exception as e:
            print(f"[ERROR] Lỗi filter file uploaded: {e}")
            res = []
    elif app_state["uploaded_content"] is not None:
        try:
            res = extractor.parse_uploaded_file(
                app_state["uploaded_content"],
                app_state["uploaded_filename"],
                time_option, custom_start, custom_end
            )
            if time_option == "all_time":
                app_state["parsed_all_time_trades"] = res
        except Exception as e:
            print(f"[ERROR] Lỗi parse file uploaded: {e}")
            res = []
    return sanitize_json_floats(res)


@app.get("/api/summary")
async def get_portfolio_summary(
    time_option: str = Query("this_week"),
    custom_start: Optional[str] = Query(None),
    custom_end: Optional[str] = Query(None)
):
    """
    Lấy tổng quan hiệu suất toàn bộ danh mục và bảng so sánh các Magic Number.
    """
    trades = _get_trades_by_filter(time_option, custom_start, custom_end)
    app_state["current_trades"] = trades
    
    initial_cap = float(config_mgr.get_settings().get("initial_capital", 10000.0))
    rf_rate = float(config_mgr.get_settings().get("risk_free_rate_pct", 5.0))
    
    # Tính chỉ số toàn bộ danh mục
    portfolio_metrics = compute_metrics(trades, initial_capital=initial_cap, risk_free_rate_pct=rf_rate)
    
    # Phân loại theo Magic Number
    magic_groups = {}
    for t in trades:
        m = int(t.get("magic", 0))
        if m not in magic_groups:
            magic_groups[m] = []
        magic_groups[m].append(t)
        
    strategies_comparison = []
    pie_profit_data = []
    pie_trades_data = []
    
    for m, m_trades in magic_groups.items():
        m_info = config_mgr.get_strategy_info(m)
        m_metrics = compute_metrics(m_trades, initial_capital=initial_cap, risk_free_rate_pct=rf_rate)
        
        row = {
            "magic": m,
            "name": m_info["name"],
            "description": m_info["description"],
            "color": m_info["color"],
            "total_trades": m_metrics["summary"]["total_trades"],
            "win_rate": m_metrics["summary"]["win_rate"],
            "net_profit": m_metrics["summary"]["net_profit"],
            "profit_factor": m_metrics["summary"]["profit_factor"],
            "sharpe_ratio": m_metrics["institutional_ratios"]["sharpe_ratio"],
            "sqn": m_metrics["payoff_quality"]["sqn"],
            "sqn_rating": m_metrics["payoff_quality"]["sqn_rating"],
            "max_drawdown_pct": m_metrics["drawdown_risk"]["max_drawdown_pct"],
            "recovery_factor": m_metrics["drawdown_risk"]["recovery_factor"]
        }
        strategies_comparison.append(row)
        
        # Dữ liệu cho biểu đồ tròn
        if m_metrics["summary"]["net_profit"] > 0:
            pie_profit_data.append({"label": m_info["name"], "value": m_metrics["summary"]["net_profit"], "color": m_info["color"]})
        pie_trades_data.append({"label": m_info["name"], "value": m_metrics["summary"]["total_trades"], "color": m_info["color"]})
        
    # Sắp xếp mặc định theo Net Profit giảm dần
    strategies_comparison = sorted(strategies_comparison, key=lambda x: x["net_profit"], reverse=True)
    
    res = {
        "time_option": time_option,
        "trade_count": len(trades),
        "portfolio_metrics": portfolio_metrics,
        "strategies_comparison": strategies_comparison,
        "pie_charts": {
            "profit": pie_profit_data,
            "trades": pie_trades_data
        }
    }
    return sanitize_json_floats(res)


@app.get("/api/strategy/{magic}")
async def get_strategy_drilldown(
    magic: int,
    time_option: str = Query("this_week"),
    custom_start: Optional[str] = Query(None),
    custom_end: Optional[str] = Query(None)
):
    """
    Lấy thông tin phân tích định lượng chuyên sâu (Drill-down) cho một Magic Number cụ thể.
    """
    trades = _get_trades_by_filter(time_option, custom_start, custom_end)
    magic_trades = [t for t in trades if int(t.get("magic", 0)) == int(magic)]
    
    initial_cap = float(config_mgr.get_settings().get("initial_capital", 10000.0))
    rf_rate = float(config_mgr.get_settings().get("risk_free_rate_pct", 5.0))
    
    metrics = compute_metrics(magic_trades, initial_capital=initial_cap, risk_free_rate_pct=rf_rate)
    strategy_info = config_mgr.get_strategy_info(magic)
    
    # Sắp xếp lệnh mới nhất lên đầu cho bảng Trade History
    sorted_trades = sorted(magic_trades, key=lambda x: x.get("close_time", ""), reverse=True)
    
    res = {
        "magic": magic,
        "strategy_info": strategy_info,
        "trade_count": len(magic_trades),
        "metrics": metrics,
        "trades": sorted_trades[:500]  # Trả về 500 lệnh mới nhất để hiển thị bảng
    }
    return sanitize_json_floats(res)


@app.post("/api/strategy_name")
async def update_strategy_name(
    magic: int = Form(...),
    name: str = Form(...),
    description: str = Form(""),
    color: Optional[str] = Form(None)
):
    """Cập nhật ánh xạ tên, mô tả và màu sắc cho một Magic Number."""
    success = config_mgr.update_strategy_info(magic, name, description, color)
    if success:
        return {"success": True, "message": f"Đã cập nhật chiến lược #{magic} -> {name}"}
    else:
        raise HTTPException(status_code=500, detail="Không thể lưu cấu hình")


if __name__ == "__main__":
    print("=========================================================================")
    print("🚀 KHỞI ĐỘNG MT5 QUANTITATIVE STRATEGY ANALYZER DASHBOARD")
    print("👉 Mở trình duyệt web tại: http://localhost:8000")
    print("=========================================================================")
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
