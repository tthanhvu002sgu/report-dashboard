"""
========================================================================================
MODULE THU THẬP & PHÂN TÍCH DỮ LIỆU GIAO DỊCH ĐA NGUỒN (MT5 EXTRACTOR)
========================================================================================
Hỗ trợ:
  1. Kết nối trực tiếp MT5 Terminal (chạy cục bộ hoặc đã đăng nhập tài khoản từ VPS).
  2. Parser đọc file báo cáo giao dịch (HTML / CSV / Excel XML / JSON) xuất từ VPS.
  3. Bộ lọc thời gian đa dạng (Mặc định: Tuần này - This Week).
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
import io
import json
import re
import math
from datetime import datetime, timedelta, date
from typing import List, Dict, Any, Tuple, Optional
import pandas as pd
import numpy as np

# Thử import MetaTrader5, nếu chạy trên VPS hoặc máy không cài MT5 thì fallback an toàn
try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False


def get_date_range(time_option: str = "this_week", custom_start: Optional[str] = None, custom_end: Optional[str] = None) -> Tuple[datetime, datetime]:
    """
    Tính toán mốc thời gian bắt đầu (from_date) và kết thúc (to_date) theo tùy chọn.
    Mặc định: 'this_week' (Từ 00:00:00 Thứ Hai tuần hiện tại đến hiện tại).
    """
    now = datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    if time_option == "today":
        return today_start, now
    elif time_option == "yesterday":
        yesterday_start = today_start - timedelta(days=1)
        yesterday_end = today_start - timedelta(microseconds=1)
        return yesterday_start, yesterday_end
    elif time_option == "this_week":
        # Thứ Hai tuần này (weekday = 0)
        monday_start = today_start - timedelta(days=today_start.weekday())
        return monday_start, now
    elif time_option == "last_week":
        this_monday = today_start - timedelta(days=today_start.weekday())
        last_monday = this_monday - timedelta(days=7)
        last_sunday_end = this_monday - timedelta(microseconds=1)
        return last_monday, last_sunday_end
    elif time_option == "this_month":
        month_start = today_start.replace(day=1)
        return month_start, now
    elif time_option == "last_month":
        this_month_start = today_start.replace(day=1)
        last_month_end = this_month_start - timedelta(microseconds=1)
        last_month_start = last_month_end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return last_month_start, last_month_end
    elif time_option == "this_quarter":
        quarter_month = 3 * ((today_start.month - 1) // 3) + 1
        quarter_start = today_start.replace(month=quarter_month, day=1)
        return quarter_start, now
    elif time_option == "this_year":
        year_start = today_start.replace(month=1, day=1)
        return year_start, now
    elif time_option == "all_time":
        # Từ năm 2000
        return datetime(2000, 1, 1), now
    elif time_option == "custom" and custom_start and custom_end:
        try:
            start_dt = datetime.fromisoformat(custom_start.replace("Z", ""))
            end_dt = datetime.fromisoformat(custom_end.replace("Z", ""))
            return start_dt, end_dt
        except Exception:
            return today_start - timedelta(days=30), now
    else:
        # Mặc định an toàn: tuần này
        monday_start = today_start - timedelta(days=today_start.weekday())
        return monday_start, now


class MT5Extractor:
    def __init__(self):
        self.connected = False
        self.account_info = {}

    def connect_mt5(self) -> Tuple[bool, str]:
        """Kết nối tới MT5 terminal đang chạy trên máy."""
        if not MT5_AVAILABLE:
            return False, "Thư viện MetaTrader5 chưa được cài đặt hoặc không hỗ trợ trên OS này."
        
        if not mt5.initialize():
            err = mt5.last_error()
            return False, f"Không thể kết nối MT5 Terminal: {err}. Hãy đảm bảo MT5 đang mở và đã bật 'Allow Automated Trading'."
        
        acc = mt5.account_info()
        if acc is None:
            return False, "Kết nối MT5 thành công nhưng không lấy được thông tin tài khoản."
        
        self.connected = True
        self.account_info = {
            "login": acc.login,
            "server": acc.server,
            "currency": acc.currency,
            "balance": acc.balance,
            "equity": acc.equity,
            "company": acc.company
        }
        return True, f"Đã kết nối tài khoản {acc.login} ({acc.server}) - Balance: {acc.balance:,.2f} {acc.currency}"

    def disconnect_mt5(self):
        """Ngắt kết nối MT5."""
        if MT5_AVAILABLE and self.connected:
            mt5.shutdown()
            self.connected = False

    def fetch_live_deals(self, time_option: str = "this_week", custom_start: Optional[str] = None, custom_end: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Lấy danh sách các lệnh đã đóng (Deals) từ MT5 Terminal trực tiếp trong khoảng thời gian.
        """
        if not self.connected:
            success, msg = self.connect_mt5()
            if not success:
                raise RuntimeError(msg)

        from_date, to_date = get_date_range(time_option, custom_start, custom_end)
        deals = mt5.history_deals_get(from_date, to_date)
        if deals is None:
            return []

        processed_trades = []
        for d in deals:
            # Trong MT5, lệnh đóng có entry = DEAL_ENTRY_OUT (1) hoặc DEAL_ENTRY_INOUT (2)
            if d.entry not in (mt5.DEAL_ENTRY_OUT, mt5.DEAL_ENTRY_INOUT):
                continue
            
            # Nếu PnL = 0 và commission = 0 và swap = 0 (ví dụ lệnh chuyển khoán, hoặc balance deposit)
            if d.type in (mt5.DEAL_TYPE_BALANCE, mt5.DEAL_TYPE_CREDIT, mt5.DEAL_TYPE_BONUS, mt5.DEAL_TYPE_CHARGE):
                continue

            magic = int(d.magic) if hasattr(d, 'magic') else 0
            net_profit = float(d.profit) + float(d.commission) + float(d.swap) + float(getattr(d, 'fee', 0.0))
            
            # Cố gắng tìm lệnh mở (DEAL_ENTRY_IN) cùng position ticket để tính holding time & open price
            open_time = datetime.fromtimestamp(d.time)
            open_price = float(d.price)
            hold_duration_sec = 0
            
            if hasattr(d, 'position') and d.position > 0:
                pos_deals = mt5.history_deals_get(position=d.position)
                if pos_deals and len(pos_deals) > 0:
                    for pd_deal in pos_deals:
                        if pd_deal.entry == mt5.DEAL_ENTRY_IN:
                            open_time = datetime.fromtimestamp(pd_deal.time)
                            open_price = float(pd_deal.price)
                            hold_duration_sec = int(d.time - pd_deal.time)
                            break
            
            # Xác định chiều giao dịch ban đầu (BUY hay SELL)
            # Nếu closing deal là SELL (1) -> position ban đầu là BUY (Long)
            # Nếu closing deal là BUY (0) -> position ban đầu là SELL (Short)
            direction = "LONG" if d.type == mt5.DEAL_TYPE_SELL else "SHORT" if d.type == mt5.DEAL_TYPE_BUY else "OTHER"
            
            trade_record = {
                "ticket": int(d.ticket),
                "position_ticket": int(getattr(d, 'position', d.ticket)),
                "magic": magic,
                "symbol": str(d.symbol),
                "direction": direction,
                "volume": float(d.volume),
                "open_price": open_price,
                "close_price": float(d.price),
                "open_time": open_time.isoformat(),
                "close_time": datetime.fromtimestamp(d.time).isoformat(),
                "hold_duration_sec": hold_duration_sec,
                "profit": float(d.profit),
                "commission": float(d.commission),
                "swap": float(d.swap),
                "fee": float(getattr(d, 'fee', 0.0)),
                "net_profit": round(net_profit, 2),
                "comment": str(d.comment) if hasattr(d, 'comment') else ""
            }
            processed_trades.append(trade_record)
            
        return processed_trades

    def parse_uploaded_file(self, file_content: bytes, filename: str, time_option: str = "this_week", custom_start: Optional[str] = None, custom_end: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Parser đa năng đọc báo cáo xuất từ MT5 trên VPS (HTML / CSV / Excel / JSON).
        """
        ext = filename.lower().split(".")[-1]
        raw_trades = []
        
        if ext == "json":
            try:
                data = json.loads(file_content.decode("utf-8"))
                if isinstance(data, list):
                    raw_trades = data
                elif isinstance(data, dict) and "trades" in data:
                    raw_trades = data["trades"]
                elif isinstance(data, dict) and "deals" in data:
                    raw_trades = data["deals"]
            except Exception as e:
                raise ValueError(f"Lỗi đọc định dạng JSON: {e}")
                
        elif ext in ("csv", "txt"):
            try:
                df = pd.read_csv(io.BytesIO(file_content))
                raw_trades = self._convert_df_to_trades(df)
            except Exception as e:
                raise ValueError(f"Lỗi đọc định dạng CSV: {e}")
                
        elif ext in ("html", "htm", "xls", "xlsx", "xml"):
            try:
                # 1. Thử parse như bảng HTML (báo cáo chuẩn MT5 xuất Excel thường là HTML table)
                dfs = pd.read_html(io.BytesIO(file_content))
                for df in dfs:
                    if len(df) > 1 and any(col in str(df.columns).lower() or any("profit" in str(val).lower() for val in df.iloc[0:5].values.flatten()) for col in ["profit", "deal", "magic", "time", "symbol"]):
                        raw_trades.extend(self._convert_mt5_html_table(df))
            except Exception as e_html:
                # 2. Nếu read_html thất bại (ví dụ file là Excel workbook nhị phân chuẩn .xlsx), thử pd.read_excel
                try:
                    df_excel = pd.read_excel(io.BytesIO(file_content))
                    raw_trades.extend(self._convert_mt5_html_table(df_excel))
                    if len(raw_trades) == 0:
                        raw_trades.extend(self._convert_df_to_trades(df_excel))
                except Exception as e_excel:
                    # 3. Fallback parse thủ công bằng regex nếu là text/html
                    try:
                        raw_trades = self._parse_html_regex(file_content.decode("utf-8", errors="ignore"))
                    except Exception:
                        pass
        else:
            raise ValueError(f"Định dạng file không hỗ trợ: .{ext}. Vui lòng upload file HTML, Excel (.xlsx/.xls), CSV hoặc JSON xuất từ MT5.")

        # Post-processing: Map Magic Numbers từ lệnh mở (Entry) sang lệnh đóng (Exit) cùng Position ID trước khi lọc ngày
        pos_magic_map = {}
        for t in raw_trades:
            m_val = t.get("magic", 0)
            p_val = t.get("position_ticket", t.get("ticket", 0))
            try:
                m_int = int(float(str(m_val).replace(" ", ""))) if m_val and str(m_val).strip() != "" else 0
                p_int = int(float(str(p_val).replace(" ", ""))) if p_val and str(p_val).strip() != "" else 0
                if m_int != 0 and p_int != 0:
                    pos_magic_map[p_int] = m_int
            except Exception:
                continue

        for t in raw_trades:
            p_val = t.get("position_ticket", t.get("ticket", 0))
            try:
                p_int = int(float(str(p_val).replace(" ", ""))) if p_val and str(p_val).strip() != "" else 0
                m_val = t.get("magic", 0)
                m_int = int(float(str(m_val).replace(" ", ""))) if m_val and str(m_val).strip() != "" else 0
                if m_int == 0 and p_int in pos_magic_map:
                    t["magic"] = pos_magic_map[p_int]
            except Exception:
                continue

        # Lọc theo mốc thời gian đã chọn
        from_date, to_date = get_date_range(time_option, custom_start, custom_end)
        filtered_trades = []
        for t in raw_trades:
            try:
                # Đảm bảo có magic number
                if "magic" not in t or t["magic"] is None or str(t["magic"]).strip() == "":
                    t["magic"] = 0
                else:
                    t["magic"] = int(float(t["magic"]))
                
                # Parse close_time
                ct_str = str(t.get("close_time", t.get("time", datetime.now().isoformat())))
                if "T" in ct_str:
                    ct = datetime.fromisoformat(ct_str.split(".")[0])
                else:
                    # Thử các định dạng ngày phổ biến của MT5 (YYYY.MM.DD HH:MM:SS hoặc YYYY-MM-DD HH:MM:SS)
                    ct_clean = ct_str.replace(".", "-")
                    ct = pd.to_datetime(ct_clean).to_pydatetime()
                
                t["close_time"] = ct.isoformat()
                if "open_time" not in t:
                    t["open_time"] = t["close_time"]
                
                # Lọc thời gian
                if from_date <= ct <= to_date:
                    # Đảm bảo các chỉ số số học an toàn, tuyệt đối không có NaN hay Inf
                    t["profit"] = self._safe_float(t.get("profit", 0.0))
                    t["commission"] = self._safe_float(t.get("commission", 0.0))
                    t["swap"] = self._safe_float(t.get("swap", 0.0))
                    t["fee"] = self._safe_float(t.get("fee", 0.0))
                    t["net_profit"] = round(t["profit"] + t["commission"] + t["swap"] + t["fee"], 2)
                    t["volume"] = self._safe_float(t.get("volume", 0.1), default=0.1)
                    t["open_price"] = self._safe_float(t.get("open_price", 0.0))
                    t["close_price"] = self._safe_float(t.get("close_price", 0.0))
                    t["ticket"] = int(self._safe_float(t.get("ticket", 0)))
                    t["position_ticket"] = int(self._safe_float(t.get("position_ticket", t["ticket"])))
                    filtered_trades.append(t)
            except Exception as e:
                continue
                
        return filtered_trades

    def filter_trades_by_time(self, trades: List[Dict[str, Any]], time_option: str = "this_week", custom_start: Optional[str] = None, custom_end: Optional[str] = None) -> List[Dict[str, Any]]:
        """Lọc nhanh danh sách lệnh trong bộ nhớ theo mốc thời gian (không cần parse lại file)."""
        if time_option == "all_time":
            return trades
        from_date, to_date = get_date_range(time_option, custom_start, custom_end)
        filtered = []
        for t in trades:
            try:
                ct_str = str(t.get("close_time", t.get("time", "")))
                if not ct_str:
                    continue
                if "T" in ct_str:
                    ct = datetime.fromisoformat(ct_str.split(".")[0])
                else:
                    ct = pd.to_datetime(ct_str).to_pydatetime()
                if from_date <= ct <= to_date:
                    filtered.append(t)
            except Exception:
                continue
        return filtered

    def _safe_float(self, val: Any, default: float = 0.0) -> float:
        """Chuyển đổi số thực an toàn từ mọi định dạng chuỗi (tiền tệ, khoảng trắng, \\xa0, dấu phẩy...)."""
        try:
            if val is None or pd.isna(val):
                return default
            s_val = str(val).strip()
            if s_val.lower() in ("nan", "inf", "-inf", "", "null", "none", "-", "--"):
                return default
                
            # Loại bỏ các ký tự không phải số, dấu trừ, dấu chấm, dấu phẩy (bỏ tiền tệ như $, USD, EUR, \\xa0...)
            s_clean = re.sub(r'[^\d.,-]+', '', s_val)
            if not s_clean or s_clean in ("-", ".", ",", "-.", "-,"):
                return default
                
            # Xử lý dấu phẩy và dấu chấm:
            if ',' in s_clean and '.' in s_clean:
                if s_clean.rfind('.') > s_clean.rfind(','):
                    s_clean = s_clean.replace(',', '')
                else:
                    s_clean = s_clean.replace('.', '').replace(',', '.')
            elif ',' in s_clean:
                parts = s_clean.split(',')
                if len(parts) == 2 and len(parts[1]) <= 2:
                    s_clean = s_clean.replace(',', '.')
                else:
                    s_clean = s_clean.replace(',', '')
                    
            res = float(s_clean)
            if math.isnan(res) or math.isinf(res):
                return default
            return res
        except Exception:
            return default

    def _convert_df_to_trades(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """Chuyển đổi DataFrame từ CSV sang danh sách dict chuẩn."""
        # Chuẩn hóa tên cột
        df.columns = [str(c).strip().lower().replace(" ", "_").replace(".", "_") for c in df.columns]
        
        # Mapping cột CSV MT5 phổ biến
        col_map = {
            "magic_number": "magic", "magicnumber": "magic",
            "close_time": "close_time", "time": "close_time", "time_close": "close_time",
            "open_time": "open_time", "time_open": "open_time",
            "profit_usd": "profit", "net_profit": "net_profit",
            "comm": "commission", "swap_usd": "swap", "size": "volume", "lots": "volume"
        }
        for old_col, new_col in col_map.items():
            if old_col in df.columns and new_col not in df.columns:
                df[new_col] = df[old_col]

        trades = []
        records = df.to_dict('records')
        for row in records:
            if "profit" in row or "net_profit" in row:
                trades.append(row)
        return trades

    def _convert_mt5_html_table(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """Xử lý DataFrame từ bảng HTML hoặc Excel xuất ra bởi MT5."""
        # Clean header nếu header nằm ở dòng dưới (trong vòng 25 dòng đầu)
        if not any("profit" in str(c).lower() for c in df.columns):
            for i in range(min(25, len(df))):
                row_vals = [str(v).lower() for v in df.iloc[i].values]
                if "profit" in row_vals or "time" in row_vals:
                    df.columns = df.iloc[i].values
                    df = df.iloc[i+1:].reset_index(drop=True)
                    break
                    
        # Khử trùng lặp và chuẩn hóa tên cột (MT5 Excel reports thường có 2 cột 'time' và 2 cột 'price')
        new_cols = []
        time_count = 0
        price_count = 0
        for c in df.columns:
            c_clean = str(c).strip().lower().replace(" ", "_").replace(".", "_")
            if c_clean == "time":
                time_count += 1
                new_cols.append("open_time" if time_count == 1 else "close_time")
            elif c_clean == "price":
                price_count += 1
                new_cols.append("open_price" if price_count == 1 else "close_price")
            elif c_clean in ("position", "deal", "order", "ticket", "position/deal"):
                new_cols.append("ticket")
            else:
                new_cols.append(c_clean)
        df.columns = new_cols

        trades = []
        records = df.to_dict('records')
        for row in records:
            # Kiểm tra nếu là dòng deal hợp lệ
            val_str = " ".join([str(v) for v in row.values()])
            if any(term in val_str.lower() for term in ["buy", "sell", "in", "out", "long", "short"]) and not any(term in val_str.lower() for term in ["balance", "deposit"]):
                try:
                    profit = self._safe_float(row.get("profit", 0))
                    magic = int(self._safe_float(row.get("magic", 0))) if "magic" in row else 0
                    
                    # Time
                    time_str = str(row.get("close_time", row.get("open_time", row.get("time", datetime.now().isoformat()))))
                    open_time_str = str(row.get("open_time", time_str))
                    
                    # Ticket
                    ticket_val = row.get("ticket", row.get("deal", row.get("order", 0)))
                    ticket = int(self._safe_float(ticket_val))
                    
                    # Symbol
                    symbol = str(row.get("symbol", "XAUUSD")).strip()
                    if symbol.lower() == "nan" or not symbol: continue
                    
                    # Direction
                    direction = "LONG" if any(b in val_str.lower() for b in ["buy", "long"]) else "SHORT"
                    
                    # Volume & Price
                    volume = self._safe_float(row.get("volume", 0.1), default=0.1)
                    close_price = self._safe_float(row.get("close_price", row.get("open_price", row.get("price", 0))))
                    open_price = self._safe_float(row.get("open_price", close_price))
                    
                    # Commission & Swap
                    commission = self._safe_float(row.get("commission", 0))
                    swap = self._safe_float(row.get("swap", 0))
                    
                    comment = str(row.get("comment", "")) if pd.notna(row.get("comment", "")) else ""
                    if comment.lower() == "nan": comment = ""
                    
                    trades.append({
                        "ticket": ticket,
                        "position_ticket": ticket,
                        "magic": magic,
                        "symbol": symbol,
                        "direction": direction,
                        "volume": volume,
                        "open_price": open_price,
                        "close_price": close_price,
                        "open_time": open_time_str,
                        "close_time": time_str,
                        "hold_duration_sec": 3600,
                        "profit": profit,
                        "commission": commission,
                        "swap": swap,
                        "fee": 0.0,
                        "net_profit": round(profit + commission + swap, 2),
                        "comment": comment
                    })
                except Exception:
                    continue
        return trades

    def _parse_html_regex(self, html_text: str) -> List[Dict[str, Any]]:
        """Parse dự phòng bằng regex cho file HTML báo cáo MT5."""
        trades = []
        # Tìm các dòng tr trong table html
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html_text, re.DOTALL | re.IGNORECASE)
        for r in rows:
            cells = re.findall(r'<td[^>]*>(.*?)</td>', r, re.DOTALL | re.IGNORECASE)
            cells = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
            if len(cells) >= 10 and any(t in cells[2].lower() for t in ["buy", "sell", "out"]):
                try:
                    profit = self._safe_float(cells[-1])
                    swap = self._safe_float(cells[-2]) if len(cells) >= 11 else 0.0
                    comm = self._safe_float(cells[-3]) if len(cells) >= 12 else 0.0
                    
                    trades.append({
                        "ticket": int(self._safe_float(cells[1])),
                        "magic": 0,
                        "symbol": cells[2] if len(cells[2]) > 2 else "UNKNOWN",
                        "direction": "LONG" if "buy" in cells[3].lower() else "SHORT",
                        "volume": self._safe_float(cells[5], default=0.1) if len(cells) > 5 else 0.1,
                        "close_price": self._safe_float(cells[6]) if len(cells) > 6 else 0.0,
                        "close_time": cells[0].replace(".", "-"),
                        "profit": profit,
                        "commission": comm,
                        "swap": swap,
                        "net_profit": round(profit + comm + swap, 2)
                    })
                except Exception:
                    continue
        return trades

# Instance mặc định
extractor = MT5Extractor()
