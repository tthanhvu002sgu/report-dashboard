//+------------------------------------------------------------------+
//|                                                ExportHistory.mq5 |
//|                                                       Antigravity |
//|        Export account deal history including Magic Number to CSV |
//+------------------------------------------------------------------+
#property copyright "Antigravity"
#property link      "https://github.com"
#property version   "1.00"
#property script_show_inputs

//--- input parameters
input string   InpFileName="mt5_deal_history.csv"; // Tên file xuất ra

//+------------------------------------------------------------------+
//| Script program start function                                    |
//+------------------------------------------------------------------+
void OnStart()
  {
//--- Yêu cầu nạp toàn bộ lịch sử tài khoản
   if(!HistorySelect(0, TimeCurrent()))
     {
      Print("❌ Lỗi tải lịch sử tài khoản!");
      return;
     }

   int totalDeals = HistoryDealsTotal();
   Print("📊 Tìm thấy tổng cộng ", totalDeals, " deals trong lịch sử.");

//--- Mở file để ghi trong thư mục MQL5/Files
   int fileHandle = FileOpen(InpFileName, FILE_WRITE|FILE_CSV|FILE_ANSI, ',');
   if(fileHandle == INVALID_HANDLE)
     {
      Print("❌ Không thể tạo file: ", InpFileName, ". Lỗi: ", GetLastError());
      return;
     }

//--- Ghi tiêu đề cột CSV
   FileWrite(fileHandle, 
             "ticket", 
             "magic", 
             "symbol", 
             "direction", 
             "volume", 
             "open_price", 
             "close_price", 
             "open_time", 
             "close_time", 
             "profit", 
             "commission", 
             "swap", 
             "comment");

   int exportedCount = 0;
   
//--- Pass 1: Quét nhanh qua toàn bộ lịch sử để xây dựng bản đồ Position ID -> Magic Number của EA
   ulong pos_ids[];
   long  pos_magics[];
   int   pos_count = 0;
   
   for(int i = 0; i < totalDeals; i++)
     {
      ulong ticket = HistoryDealGetTicket(i);
      if(ticket <= 0) continue;
      
      long magic       = HistoryDealGetInteger(ticket, DEAL_MAGIC);
      long position_id = HistoryDealGetInteger(ticket, DEAL_POSITION_ID);
      
      if(magic > 0 && position_id > 0)
        {
         ArrayResize(pos_ids, pos_count + 1);
         ArrayResize(pos_magics, pos_count + 1);
         pos_ids[pos_count]    = position_id;
         pos_magics[pos_count] = magic;
         pos_count++;
        }
     }
     
   Print("🔗 Đã ánh xạ thành công ", pos_count, " vị thế từ các EA.");

//--- Pass 2: Xuất dữ liệu, tự động kế thừa Magic từ lệnh mở (Entry) cho các lệnh đóng thủ công (Exit)
   for(int i = 0; i < totalDeals; i++)
     {
      ulong ticket = HistoryDealGetTicket(i);
      if(ticket <= 0) continue;

      // Lấy thông tin deal
      long     magic       = HistoryDealGetInteger(ticket, DEAL_MAGIC);
      long     position_id = HistoryDealGetInteger(ticket, DEAL_POSITION_ID);
      string   symbol      = HistoryDealGetString(ticket, DEAL_SYMBOL);
      long     type        = HistoryDealGetInteger(ticket, DEAL_TYPE);
      long     entry       = HistoryDealGetInteger(ticket, DEAL_ENTRY);
      double   volume      = HistoryDealGetDouble(ticket, DEAL_VOLUME);
      double   price       = HistoryDealGetDouble(ticket, DEAL_PRICE);
      datetime time        = (datetime)HistoryDealGetInteger(ticket, DEAL_TIME);
      double   profit      = HistoryDealGetDouble(ticket, DEAL_PROFIT);
      double   commission  = HistoryDealGetDouble(ticket, DEAL_COMMISSION);
      double   swap        = HistoryDealGetDouble(ticket, DEAL_SWAP);
      string   comment     = HistoryDealGetString(ticket, DEAL_COMMENT);

      // Nếu magic == 0 (ví dụ lệnh đóng thủ công bằng tay), tra cứu trong bản đồ Position ID -> Magic
      if(magic == 0 && position_id > 0)
        {
         for(int j = pos_count - 1; j >= 0; j--)
           {
            if(pos_ids[j] == position_id)
              {
               magic = pos_magics[j];
               break;
              }
           }
        }

      // Bỏ qua các dòng nạp rút tiền hoặc cân bằng tài khoản (chỉ lấy buy/sell)
      if(type != DEAL_TYPE_BUY && type != DEAL_TYPE_SELL) continue;

      // Chiều giao dịch
      string direction = (type == DEAL_TYPE_BUY) ? "BUY" : "SELL";

      // Định dạng thời gian
      string timeStr = TimeToString(time, TIME_DATE|TIME_MINUTES|TIME_SECONDS);

      // Ghi dòng dữ liệu vào CSV
      FileWrite(fileHandle, 
                IntegerToString(ticket), 
                IntegerToString(magic), 
                symbol, 
                direction, 
                DoubleToString(volume, 2), 
                DoubleToString(price, 5), 
                DoubleToString(price, 5), // Close price tạm lấy bằng deal price
                timeStr, 
                timeStr, 
                DoubleToString(profit, 2), 
                DoubleToString(commission, 2), 
                DoubleToString(swap, 2), 
                comment);
                
      exportedCount++;
     }

   FileClose(fileHandle);
   
   string path = TerminalInfoString(TERMINAL_DATA_PATH) + "\\MQL5\\Files\\" + InpFileName;
   Print("🎉 Xuất lịch sử thành công! Đã ghi ", exportedCount, " deals vào file.");
   Alert("🎉 Xuất lịch sử thành công!\nFile lưu tại: MQL5\\Files\\", InpFileName);
  }
//+------------------------------------------------------------------+
