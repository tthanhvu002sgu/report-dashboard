"""
========================================================================================
MODULE ĐỘNG CƠ TOÁN HỌC & CHỈ SỐ ĐỊNH LƯỢNG (METRICS ENGINE)
========================================================================================
Tính toán các chỉ số định lượng chuyên sâu chuẩn Quỹ (Institutional-grade Metrics):
  - Lợi nhuận & Thắng/Thua: Win Rate, Profit Factor, Expected Payoff, Payoff Ratio.
  - Rủi ro & Sụt giảm: Max Drawdown ($ & %), Recovery Factor, Average DD.
  - Institutional Ratios: Sharpe Ratio (Annualized), Sortino Ratio, Calmar Ratio, SQN.
  - Dữ liệu biểu đồ: Equity Curve, Underwater Drawdown, Monthly Returns Heatmap.
========================================================================================
"""

import math
from datetime import datetime
from typing import List, Dict, Any, Tuple
import pandas as pd
import numpy as np


def compute_metrics(trades: List[Dict[str, Any]], initial_capital: float = 10000.0, risk_free_rate_pct: float = 5.0) -> Dict[str, Any]:
    """
    Tính toán toàn bộ bộ chỉ số định lượng cho danh sách giao dịch.
    """
    if not trades or len(trades) == 0:
        return _empty_metrics(initial_capital)

    # Sắp xếp lệnh theo thời gian đóng lệnh
    sorted_trades = sorted(trades, key=lambda x: x.get("close_time", ""))
    
    total_trades = len(sorted_trades)
    wins = [t for t in sorted_trades if t["net_profit"] > 0]
    losses = [t for t in sorted_trades if t["net_profit"] < 0]
    bes = [t for t in sorted_trades if t["net_profit"] == 0]
    
    win_count = len(wins)
    loss_count = len(losses)
    be_count = len(bes)
    
    win_rate = (win_count / total_trades) * 100.0
    loss_rate = (loss_count / total_trades) * 100.0
    
    gross_profit = sum(t["net_profit"] for t in wins)
    gross_loss = abs(sum(t["net_profit"] for t in losses))
    net_profit = gross_profit - gross_loss
    
    if gross_loss == 0:
        profit_factor = 999.0 if gross_profit > 0 else 0.0
    else:
        profit_factor = gross_profit / gross_loss

    avg_win = gross_profit / win_count if win_count > 0 else 0.0
    avg_loss = gross_loss / loss_count if loss_count > 0 else 0.0
    payoff_ratio = avg_win / avg_loss if avg_loss > 0 else (999.0 if avg_win > 0 else 0.0)
    
    avg_trade_pnl = net_profit / total_trades
    expected_payoff = (win_rate / 100.0 * avg_win) - (loss_rate / 100.0 * avg_loss)
    
    largest_win = max((t["net_profit"] for t in wins), default=0.0)
    largest_loss = min((t["net_profit"] for t in losses), default=0.0)

    # ---------------------------------------------------------
    # 1. Equity Curve & Drawdown Analysis
    # ---------------------------------------------------------
    equity_curve = []
    underwater_curve = []
    current_equity = initial_capital
    peak_equity = initial_capital
    
    max_dd_usd = 0.0
    max_dd_pct = 0.0
    dd_usd_list = []
    
    # Điểm xuất phát 0
    start_time_str = sorted_trades[0].get("open_time", sorted_trades[0].get("close_time", ""))
    equity_curve.append({"time": start_time_str, "value": round(initial_capital, 2)})
    underwater_curve.append({"time": start_time_str, "value": 0.0})
    
    for t in sorted_trades:
        current_equity += t["net_profit"]
        if current_equity > peak_equity:
            peak_equity = current_equity
            
        dd_usd = peak_equity - current_equity
        dd_pct = (dd_usd / peak_equity) * 100.0 if peak_equity > 0 else 0.0
        
        if dd_usd > max_dd_usd:
            max_dd_usd = dd_usd
        if dd_pct > max_dd_pct:
            max_dd_pct = dd_pct
            
        if dd_usd > 0:
            dd_usd_list.append(dd_usd)
            
        t_time = t.get("close_time", "")
        equity_curve.append({"time": t_time, "value": round(current_equity, 2)})
        underwater_curve.append({"time": t_time, "value": round(-dd_pct, 2)})

    avg_dd_usd = float(np.mean(dd_usd_list)) if len(dd_usd_list) > 0 else 0.0
    
    if max_dd_usd == 0:
        recovery_factor = 999.0 if net_profit > 0 else 0.0
    else:
        recovery_factor = net_profit / max_dd_usd

    # ---------------------------------------------------------
    # 2. System Quality Number (SQN - Van Tharp)
    # ---------------------------------------------------------
    pnl_array = np.array([t["net_profit"] for t in sorted_trades])
    pnl_std = float(np.std(pnl_array, ddof=1)) if len(pnl_array) > 1 else 0.0
    if pnl_std > 0 and total_trades > 1:
        sqn = math.sqrt(total_trades) * (avg_trade_pnl / pnl_std)
    else:
        sqn = 0.0
        
    sqn_rating = "Poor"
    if sqn >= 3.0: sqn_rating = "Holy Grail 👑"
    elif sqn >= 2.5: sqn_rating = "Excellent ⭐"
    elif sqn >= 2.0: sqn_rating = "Good 👍"
    elif sqn >= 1.6: sqn_rating = "Average ⚪"
    else: sqn_rating = "Poor 🔴"

    # ---------------------------------------------------------
    # 3. Institutional Risk-Adjusted Ratios (Sharpe, Sortino, Calmar)
    # ---------------------------------------------------------
    # Gom PnL theo ngày để tính Sharpe / Sortino thường niên (Annualized)
    df_trades = pd.DataFrame(sorted_trades)
    df_trades["dt"] = pd.to_datetime(df_trades["close_time"]).dt.date
    daily_pnl = df_trades.groupby("dt")["net_profit"].sum()
    
    # Tính số ngày giao dịch hoặc span ngày
    days_span = (pd.to_datetime(sorted_trades[-1]["close_time"]) - pd.to_datetime(sorted_trades[0]["close_time"])).days
    days_span = max(1, days_span)
    years_span = days_span / 365.25
    annualized_return_pct = ((net_profit / initial_capital) / years_span) * 100.0 if years_span > 0 else 0.0
    
    rf_daily_usd = (initial_capital * (risk_free_rate_pct / 100.0)) / 252.0
    
    if len(daily_pnl) > 1:
        mean_daily = float(daily_pnl.mean())
        std_daily = float(daily_pnl.std(ddof=1))
        
        if std_daily > 0:
            sharpe_ratio = ((mean_daily - rf_daily_usd) / std_daily) * math.sqrt(252)
        else:
            sharpe_ratio = 0.0
            
        # Sortino: Chỉ lấy độ lệch chuẩn của các ngày lỗ (Downside deviation)
        downside_diffs = daily_pnl[daily_pnl < rf_daily_usd] - rf_daily_usd
        if len(downside_diffs) > 0:
            downside_std = math.sqrt((downside_diffs ** 2).mean())
            if downside_std > 0:
                sortino_ratio = ((mean_daily - rf_daily_usd) / downside_std) * math.sqrt(252)
            else:
                sortino_ratio = 0.0
        else:
            sortino_ratio = 99.0 if mean_daily > rf_daily_usd else 0.0
    else:
        sharpe_ratio = 0.0
        sortino_ratio = 0.0

    if max_dd_pct == 0:
        calmar_ratio = 99.0 if annualized_return_pct > 0 else 0.0
    else:
        calmar_ratio = annualized_return_pct / max_dd_pct

    # ---------------------------------------------------------
    # 4. Streaks & Holding Time
    # ---------------------------------------------------------
    max_consec_wins = 0
    max_consec_losses = 0
    cur_w = 0
    cur_l = 0
    for t in sorted_trades:
        if t["net_profit"] > 0:
            cur_w += 1
            cur_l = 0
            if cur_w > max_consec_wins: max_consec_wins = cur_w
        elif t["net_profit"] < 0:
            cur_l += 1
            cur_w = 0
            if cur_l > max_consec_losses: max_consec_losses = cur_l
        else:
            cur_w = 0
            cur_l = 0

    hold_secs = [t.get("hold_duration_sec", 0) for t in sorted_trades if t.get("hold_duration_sec", 0) > 0]
    avg_hold_sec = float(np.mean(hold_secs)) if len(hold_secs) > 0 else 0.0
    avg_hold_str = _format_duration(avg_hold_sec)

    # ---------------------------------------------------------
    # 5. Time Breakdown & Heatmap
    # ---------------------------------------------------------
    heatmap_data = _generate_heatmap_data(df_trades, initial_capital)
    day_of_week_stats = _generate_dow_stats(df_trades)
    hour_of_day_stats = _generate_hod_stats(df_trades)

    return {
        "summary": {
            "total_trades": total_trades,
            "winning_trades": win_count,
            "losing_trades": loss_count,
            "break_even_trades": be_count,
            "win_rate": round(win_rate, 2),
            "loss_rate": round(loss_rate, 2),
            "net_profit": round(net_profit, 2),
            "gross_profit": round(gross_profit, 2),
            "gross_loss": round(gross_loss, 2),
            "profit_factor": round(profit_factor, 2),
            "total_return_pct": round((net_profit / initial_capital) * 100.0, 2)
        },
        "payoff_quality": {
            "avg_trade_pnl": round(avg_trade_pnl, 2),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "payoff_ratio": round(payoff_ratio, 2),
            "expected_payoff": round(expected_payoff, 2),
            "largest_win": round(largest_win, 2),
            "largest_loss": round(largest_loss, 2),
            "sqn": round(sqn, 2),
            "sqn_rating": sqn_rating
        },
        "drawdown_risk": {
            "max_drawdown_usd": round(max_dd_usd, 2),
            "max_drawdown_pct": round(max_dd_pct, 2),
            "avg_drawdown_usd": round(avg_dd_usd, 2),
            "recovery_factor": round(recovery_factor, 2)
        },
        "institutional_ratios": {
            "sharpe_ratio": round(sharpe_ratio, 2),
            "sortino_ratio": round(sortino_ratio, 2),
            "calmar_ratio": round(calmar_ratio, 2),
            "annualized_return_pct": round(annualized_return_pct, 2)
        },
        "streaks_timing": {
            "max_consecutive_wins": max_consec_wins,
            "max_consecutive_losses": max_consec_losses,
            "avg_holding_time_sec": int(avg_hold_sec),
            "avg_holding_time_str": avg_hold_str
        },
        "charts": {
            "equity_curve": equity_curve,
            "underwater_curve": underwater_curve
        },
        "heatmap": heatmap_data,
        "day_of_week": day_of_week_stats,
        "hour_of_day": hour_of_day_stats
    }
    return sanitize_json_floats(res)


def _empty_metrics(initial_capital: float = 10000.0) -> Dict[str, Any]:
    """Trả về cấu trúc rỗng khi không có giao dịch nào."""
    res = {
        "summary": {
            "total_trades": 0, "winning_trades": 0, "losing_trades": 0, "break_even_trades": 0,
            "win_rate": 0.0, "loss_rate": 0.0, "net_profit": 0.0, "gross_profit": 0.0,
            "gross_loss": 0.0, "profit_factor": 0.0, "total_return_pct": 0.0
        },
        "payoff_quality": {
            "avg_trade_pnl": 0.0, "avg_win": 0.0, "avg_loss": 0.0, "payoff_ratio": 0.0,
            "expected_payoff": 0.0, "largest_win": 0.0, "largest_loss": 0.0, "sqn": 0.0, "sqn_rating": "N/A"
        },
        "drawdown_risk": {
            "max_drawdown_usd": 0.0, "max_drawdown_pct": 0.0, "avg_drawdown_usd": 0.0, "recovery_factor": 0.0
        },
        "institutional_ratios": {
            "sharpe_ratio": 0.0, "sortino_ratio": 0.0, "calmar_ratio": 0.0, "annualized_return_pct": 0.0
        },
        "streaks_timing": {
            "max_consecutive_wins": 0, "max_consecutive_losses": 0,
            "avg_holding_time_sec": 0, "avg_holding_time_str": "0s"
        },
        "charts": {"equity_curve": [], "underwater_curve": []},
        "heatmap": [],
        "day_of_week": [],
        "hour_of_day": []
    }
    return sanitize_json_floats(res)


def sanitize_json_floats(obj: Any) -> Any:
    """Đảm bảo tuyệt đối không có giá trị nan, inf hay -inf gây lỗi khi chuyển đổi sang JSON."""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return 0.0
        return obj
    elif isinstance(obj, dict):
        return {k: sanitize_json_floats(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_json_floats(x) for x in obj]
    elif isinstance(obj, tuple):
        return tuple(sanitize_json_floats(x) for x in obj)
    return obj


def _format_duration(seconds: float) -> str:
    """Chuyển số giây thành chuỗi giờ/phút/giây dễ đọc."""
    if seconds <= 0: return "0s"
    mins, secs = divmod(int(seconds), 60)
    hours, mins = divmod(mins, 60)
    days, hours = divmod(hours, 24)
    res = []
    if days > 0: res.append(f"{days}d")
    if hours > 0: res.append(f"{hours}h")
    if mins > 0: res.append(f"{mins}m")
    if secs > 0 and days == 0: res.append(f"{secs}s")
    return " ".join(res) if res else "0s"


def _generate_heatmap_data(df: pd.DataFrame, initial_capital: float) -> List[Dict[str, Any]]:
    """Tạo bảng Heatmap lợi nhuận theo năm/tháng (%), chuẩn bị cho giao diện."""
    if len(df) == 0: return []
    df_copy = df.copy()
    df_copy["year"] = pd.to_datetime(df_copy["close_time"]).dt.year
    df_copy["month"] = pd.to_datetime(df_copy["close_time"]).dt.month
    
    grouped = df_copy.groupby(["year", "month"])["net_profit"].sum().reset_index()
    years = sorted(df_copy["year"].unique(), reverse=True)
    
    heatmap = []
    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    
    for y in years:
        year_row = {"year": int(y), "months": {}, "total_usd": 0.0, "total_pct": 0.0}
        y_data = grouped[grouped["year"] == y]
        
        for m in range(1, 13):
            m_data = y_data[y_data["month"] == m]
            if len(m_data) > 0:
                pnl = float(m_data["net_profit"].iloc[0])
                pct = round((pnl / initial_capital) * 100.0, 2)
                year_row["months"][month_names[m-1]] = {"usd": round(pnl, 2), "pct": pct}
                year_row["total_usd"] += pnl
            else:
                year_row["months"][month_names[m-1]] = None
                
        year_row["total_usd"] = round(year_row["total_usd"], 2)
        year_row["total_pct"] = round((year_row["total_usd"] / initial_capital) * 100.0, 2)
        heatmap.append(year_row)
        
    return heatmap


def _generate_dow_stats(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """Thống kê theo ngày trong tuần (Mon -> Sun)."""
    if len(df) == 0: return []
    df_copy = df.copy()
    df_copy["dow"] = pd.to_datetime(df_copy["close_time"]).dt.dayofweek
    dow_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    
    stats = []
    for i, name in enumerate(dow_names):
        sub = df_copy[df_copy["dow"] == i]
        total = len(sub)
        if total > 0:
            wins = len(sub[sub["net_profit"] > 0])
            pnl = float(sub["net_profit"].sum())
            stats.append({
                "day": name, "trades": total, "win_rate": round((wins/total)*100.0, 1),
                "net_profit": round(pnl, 2)
            })
        else:
            stats.append({"day": name, "trades": 0, "win_rate": 0.0, "net_profit": 0.0})
    return stats


def _generate_hod_stats(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """Thống kê theo giờ trong ngày (0h -> 23h)."""
    if len(df) == 0: return []
    df_copy = df.copy()
    df_copy["hod"] = pd.to_datetime(df_copy["close_time"]).dt.hour
    
    stats = []
    for h in range(24):
        sub = df_copy[df_copy["hod"] == h]
        total = len(sub)
        if total > 0:
            wins = len(sub[sub["net_profit"] > 0])
            pnl = float(sub["net_profit"].sum())
            stats.append({
                "hour": f"{h:02d}:00", "trades": total, "win_rate": round((wins/total)*100.0, 1),
                "net_profit": round(pnl, 2)
            })
        else:
            stats.append({"hour": f"{h:02d}:00", "trades": 0, "win_rate": 0.0, "net_profit": 0.0})
    return stats
