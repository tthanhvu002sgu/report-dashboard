/* ======================================================================================
   FRONTEND LOGIC & API INTEGRATION: INSTITUTIONAL DASHBOARD
   ====================================================================================== */

let currentView = "portfolio";
let selectedMagic = 0;
let currentTimeOption = "this_week";
let allTradesList = [];
let currentPage = 1;
let pageSize = 30;
let globalStrategiesList = [];
let currentSortField = "close_time";
let currentSortOrder = "desc";

// Biểu đồ Chart.js references
let chartProfitPie = null;
let chartTradesPie = null;
let chartEquityDD = null;
let chartDow = null;
let chartHod = null;

// Khởi tạo màu sắc mặc định cho Chart.js nền tối
Chart.defaults.color = '#94a3b8';
Chart.defaults.font.family = "'Inter', sans-serif";
Chart.defaults.borderColor = 'rgba(255, 255, 255, 0.06)';

document.addEventListener("DOMContentLoaded", () => {
    initEventListeners();
    fetchStatus();
    
    // Đăng ký định tuyến bằng Hash
    window.addEventListener("hashchange", handleRouting);
    handleRouting();
});

function initEventListeners() {
    // 1. Kết nối MT5 Local
    document.getElementById("btn-connect-mt5").addEventListener("click", async () => {
        showLoading(true);
        try {
            const res = await fetch("/api/connect_mt5", { method: "POST" });
            const data = await res.json();
            if (data.success) {
                alert("✅ " + data.message);
                await fetchStatus();
                refreshCurrentView();
            } else {
                alert("⚠️ " + data.message);
            }
        } catch (e) {
            alert("❌ Lỗi kết nối API: " + e);
        } finally {
            showLoading(false);
        }
    });

    // 2. Drag & Drop file báo cáo VPS
    const dropzone = document.getElementById("dropzone");
    const fileInput = document.getElementById("file-input");
    const btnBrowse = document.getElementById("btn-browse-file");

    btnBrowse.addEventListener("click", () => fileInput.click());
    
    dropzone.addEventListener("dragover", (e) => {
        e.preventDefault();
        dropzone.classList.add("dragover");
    });
    
    dropzone.addEventListener("dragleave", () => dropzone.classList.remove("dragover"));
    
    dropzone.addEventListener("drop", (e) => {
        e.preventDefault();
        dropzone.classList.remove("dragover");
        if (e.dataTransfer.files.length > 0) {
            uploadReportFile(e.dataTransfer.files[0]);
        }
    });

    fileInput.addEventListener("change", (e) => {
        if (e.target.files.length > 0) {
            uploadReportFile(e.target.files[0]);
        }
    });

    // 3. Chọn mốc thời gian (Time Pills)
    const pills = document.querySelectorAll(".time-pill");
    const customBox = document.getElementById("custom-date-box");

    pills.forEach(pill => {
        pill.addEventListener("click", () => {
            pills.forEach(p => p.classList.remove("active"));
            pill.classList.add("active");
            
            currentTimeOption = pill.getAttribute("data-time");
            if (currentTimeOption === "custom") {
                if (customBox) customBox.classList.remove("hidden");
            } else {
                if (customBox) customBox.classList.add("hidden");
                refreshCurrentView();
            }
        });
    });

    const btnApplyCustom = document.getElementById("btn-apply-custom");
    if (btnApplyCustom) {
        btnApplyCustom.addEventListener("click", () => {
            const start = document.getElementById("custom-start").value;
            const end = document.getElementById("custom-end").value;
            if (!start || !end) {
                alert("Vui lòng chọn đầy đủ ngày bắt đầu và ngày kết thúc!");
                return;
            }
            refreshCurrentView();
        });
    }

    // 4. Quay lại Portfolio bằng Hash
    document.getElementById("btn-back-portfolio").addEventListener("click", () => {
        window.location.hash = "#portfolio";
    });

    // 5. Modal chỉnh sửa tên chiến lược
    const modalEdit = document.getElementById("modal-edit");
    document.getElementById("btn-edit-strategy").addEventListener("click", () => {
        openEditModal();
    });
    
    document.getElementById("btn-close-modal").addEventListener("click", () => {
        modalEdit.classList.add("hidden");
    });

    document.getElementById("form-edit-strategy").addEventListener("submit", async (e) => {
        e.preventDefault();
        showLoading(true);
        await saveStrategyConfig();
        modalEdit.classList.add("hidden");
        await loadStrategyDrilldown(selectedMagic);
        showLoading(false);
    });

    // Color picker sync
    const colorPicker = document.getElementById("edit-color-picker");
    const colorText = document.getElementById("edit-color-text");
    colorPicker.addEventListener("input", () => colorText.value = colorPicker.value);
    colorText.addEventListener("input", () => colorPicker.value = colorText.value);

    // 6. Phân trang & Tìm kiếm bảng Trade History có bộ lọc
    const tradeSearch = document.getElementById("trade-search");
    if (tradeSearch) {
        tradeSearch.addEventListener("input", () => {
            currentPage = 1;
            renderTradesTable();
        });
    }
    
    const tradeFilterDir = document.getElementById("trade-filter-dir");
    if (tradeFilterDir) {
        tradeFilterDir.addEventListener("change", () => {
            currentPage = 1;
            renderTradesTable();
        });
    }
    
    const tradeFilterResult = document.getElementById("trade-filter-result");
    if (tradeFilterResult) {
        tradeFilterResult.addEventListener("change", () => {
            currentPage = 1;
            renderTradesTable();
        });
    }

    const tradePageSize = document.getElementById("trade-page-size");
    if (tradePageSize) {
        tradePageSize.addEventListener("change", (e) => {
            pageSize = parseInt(e.target.value) || 30;
            currentPage = 1;
            renderTradesTable();
        });
    }

    document.getElementById("btn-prev-page").addEventListener("click", () => {
        if (currentPage > 1) { currentPage--; renderTradesTable(); }
    });
    
    document.getElementById("btn-next-page").addEventListener("click", () => {
        const maxPage = Math.ceil(getFilteredTrades().length / pageSize) || 1;
        if (currentPage < maxPage) { currentPage++; renderTradesTable(); }
    });

    // Clickable table header sorting
    const headers = document.querySelectorAll("#table-trades th.sortable");
    headers.forEach(th => {
        th.addEventListener("click", () => {
            const field = th.getAttribute("data-sort");
            if (currentSortField === field) {
                currentSortOrder = currentSortOrder === "asc" ? "desc" : "asc";
            } else {
                currentSortField = field;
                currentSortOrder = "asc";
            }
            
            // Update sort arrows/indicators
            headers.forEach(h => {
                const span = h.querySelector("span");
                if (span) {
                    const defaultArrow = h.getAttribute("data-sort") === "close_time" ? "" : "";
                    span.innerText = "";
                }
            });
            const span = th.querySelector("span");
            if (span) {
                span.innerText = currentSortOrder === "asc" ? " ▲" : " ▼";
            }
            
            currentPage = 1;
            renderTradesTable();
        });
    });

    // 7. Bộ chuyển đổi chiến lược nhanh
    document.getElementById("drill-strategy-select").addEventListener("change", (e) => {
        const magic = e.target.value;
        window.location.hash = `#strategy/${magic}`;
    });
}

function doSwitchView(viewName) {
    currentView = viewName;
    const viewPortfolio = document.getElementById("view-portfolio");
    const viewDrill = document.getElementById("view-drilldown");
    
    if (viewName === "portfolio") {
        viewDrill.classList.add("hidden");
        viewPortfolio.classList.remove("hidden");
        loadPortfolioSummary();
    } else {
        viewPortfolio.classList.add("hidden");
        viewDrill.classList.remove("hidden");
    }
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

function handleRouting() {
    const hash = window.location.hash || '#portfolio';
    const strategyMatch = hash.match(/^#strategy\/(\d+)$/);
    
    if (strategyMatch) {
        const magic = parseInt(strategyMatch[1]);
        selectedMagic = magic;
        doSwitchView("drilldown");
        loadStrategyDrilldown(magic);
    } else {
        doSwitchView("portfolio");
    }
}

function showLoading(show = true) {
    const activeViewId = currentView === "portfolio" ? "view-portfolio" : "view-drilldown";
    const activeContainer = document.getElementById(activeViewId);
    if (activeContainer) {
        if (show) {
            activeContainer.classList.add("loading");
        } else {
            activeContainer.classList.remove("loading");
        }
    }
}

function refreshCurrentView() {
    if (currentView === "portfolio") {
        loadPortfolioSummary();
    } else {
        loadStrategyDrilldown(selectedMagic);
    }
}

async function fetchStatus() {
    try {
        const res = await fetch("/api/status");
        const data = await res.json();
        
        const badge = document.getElementById("status-badge");
        const statusText = document.getElementById("status-text");
        const fileLabel = document.getElementById("current-file-label");
        
        if (data.data_source === "mt5_live" && data.mt5_connected) {
            badge.className = "status-badge live";
            statusText.innerText = `Live MT5: ${data.account_info.login} (${data.account_info.currency})`;
            fileLabel.innerText = `Đang đồng bộ trực tiếp từ tài khoản MT5 (${data.trade_count} lệnh)`;
        } else {
            badge.className = "status-badge offline";
            statusText.innerText = "Chế độ Offline (VPS Report)";
            fileLabel.innerText = data.uploaded_filename ? `File đang phân tích: ${data.uploaded_filename} (${data.trade_count} lệnh)` : "Chưa tải file báo cáo VPS";
        }
    } catch (e) {
        console.error("Lỗi lấy status:", e);
    }
}

async function uploadReportFile(file) {
    const formData = new FormData();
    formData.append("file", file);
    
    showLoading(true);
    try {
        const res = await fetch("/api/upload_report", {
            method: "POST",
            body: formData
        });
        const data = await res.json();
        if (res.ok && data.success) {
            alert("🎉 " + data.message);
            await fetchStatus();
            refreshCurrentView();
        } else {
            alert("❌ Lỗi tải file: " + (data.detail || data.message));
        }
    } catch (e) {
        alert("❌ Lỗi upload: " + e);
    } finally {
        showLoading(false);
    }
}

function getQueryString() {
    let qs = `?time_option=${currentTimeOption}`;
    if (currentTimeOption === "custom") {
        const start = document.getElementById("custom-start").value;
        const end = document.getElementById("custom-end").value;
        if (start && end) {
            qs += `&custom_start=${start}&custom_end=${end}`;
        }
    }
    return qs;
}

/* --------------------------------------------------------------------------------------
   VIEW 1: PORTFOLIO SUMMARY LOAD
-------------------------------------------------------------------------------------- */
async function loadPortfolioSummary() {
    showLoading(true);
    try {
        const res = await fetch(`/api/summary${getQueryString()}`);
        const data = await res.json();
        
        const sum = data.portfolio_metrics.summary;
        const dd = data.portfolio_metrics.drawdown_risk;
        const payoff = data.portfolio_metrics.payoff_quality;
        
        // Render 4 Hero Cards
        const netProfitEl = document.getElementById("kpi-net-profit");
        netProfitEl.innerText = formatCurrency(sum.net_profit);
        netProfitEl.style.color = sum.net_profit >= 0 ? "#10b981" : "#f43f5e";
        
        document.getElementById("kpi-return-pct").innerText = `${sum.total_return_pct >= 0 ? '+' : ''}${sum.total_return_pct}% ROI (${sum.total_trades} Lệnh)`;
        document.getElementById("kpi-win-rate").innerText = `${sum.win_rate}%`;
        document.getElementById("kpi-trades-count").innerText = `Thắng ${sum.winning_trades} / Thua ${sum.losing_trades} lệnh`;
        document.getElementById("kpi-profit-factor").innerText = sum.profit_factor;
        document.getElementById("kpi-payoff-ratio").innerText = `Payoff Ratio: ${payoff.payoff_ratio} | SQN: ${payoff.sqn}`;
        document.getElementById("kpi-max-dd").innerText = `${dd.max_drawdown_pct}%`;
        document.getElementById("kpi-dd-usd").innerText = `-$${formatNumber(dd.max_drawdown_usd)} | Recovery Factor: ${dd.recovery_factor}`;

        // Render Strategies Comparison Table
        const tbody = document.getElementById("tbody-strategies");
        tbody.innerHTML = "";
        
        globalStrategiesList = data.strategies_comparison || [];
        
        if (globalStrategiesList.length === 0) {
            tbody.innerHTML = `<tr><td colspan="10" class="empty-cell">Chưa có dữ liệu giao dịch cho mốc thời gian này. Hãy tải file báo cáo VPS hoặc kết nối MT5!</td></tr>`;
        } else {
            globalStrategiesList.forEach(st => {
                const tr = document.createElement("tr");
                tr.className = "clickable-row";
                tr.onclick = () => {
                    window.location.hash = `#strategy/${st.magic}`;
                };
                
                const pnlClass = st.net_profit >= 0 ? "badge badge-green" : "badge badge-red";
                
                tr.innerHTML = `
                    <td><span class="magic-badge" style="border: 1px solid ${st.color}; color: ${st.color};">${st.magic}</span></td>
                    <td>
                        <strong style="color: #ffffff;">${st.name}</strong><br>
                        <span style="font-size: 11px; color: #64748b;">${st.description || 'Không có mô tả'}</span>
                    </td>
                    <td><strong style="color: #cbd5e1;">${st.total_trades}</strong></td>
                    <td>
                        <div style="display:flex; align-items:center; gap:8px;">
                            <div style="width:50px; background:rgba(255,255,255,0.1); height:6px; border-radius:3px; overflow:hidden;">
                                <div style="width:${st.win_rate}%; background:#38bdf8; height:100%;"></div>
                            </div>
                            <span>${st.win_rate}%</span>
                        </div>
                    </td>
                    <td><span class="${pnlClass}">${formatCurrency(st.net_profit)}</span></td>
                    <td><strong style="color: #f8fafc;">${st.profit_factor}</strong></td>
                    <td><span class="badge badge-blue">${st.sharpe_ratio}</span></td>
                    <td><span class="badge badge-amber">${st.sqn} (${st.sqn_rating})</span></td>
                    <td><span style="color: #f43f5e; font-weight:700;">-${st.max_drawdown_pct}%</span></td>
                    <td><button class="btn-secondary" style="padding:4px 10px; font-size:11px;">🔍 Drill-down</button></td>
                `;
                tbody.appendChild(tr);
            });
        }

        // Render 2 Pie Charts
        renderPieCharts(data.pie_charts.profit, data.pie_charts.trades);
        
    } catch (e) {
        console.error("Lỗi load summary:", e);
    } finally {
        showLoading(false);
    }
}

function renderPieCharts(profitData, tradesData) {
    if (chartProfitPie) chartProfitPie.destroy();
    if (chartTradesPie) chartTradesPie.destroy();

    const ctxProfit = document.getElementById("chart-profit-pie").getContext("2d");
    chartProfitPie = new Chart(ctxProfit, {
        type: 'doughnut',
        data: {
            labels: profitData.map(d => d.label),
            datasets: [{
                data: profitData.map(d => d.value),
                backgroundColor: profitData.map(d => d.color || '#38bdf8'),
                borderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { position: 'right' } }
        }
    });

    const ctxTrades = document.getElementById("chart-trades-pie").getContext("2d");
    chartTradesPie = new Chart(ctxTrades, {
        type: 'doughnut',
        data: {
            labels: tradesData.map(d => d.label),
            datasets: [{
                data: tradesData.map(d => d.value),
                backgroundColor: tradesData.map(d => d.color || '#818cf8'),
                borderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { position: 'right' } }
        }
    });
}

/* --------------------------------------------------------------------------------------
   VIEW 2: STRATEGY DRILL-DOWN LOAD
-------------------------------------------------------------------------------------- */
async function loadStrategyDrilldown(magic) {
    showLoading(true);
    try {
        // Nếu danh sách chiến lược toàn cục trống (ví dụ load thẳng bằng deep link), tải portfolio trước để lấy tên/màu sắc
        if (globalStrategiesList.length === 0) {
            const resSum = await fetch(`/api/summary${getQueryString()}`);
            const dataSum = await resSum.json();
            globalStrategiesList = dataSum.strategies_comparison || [];
        }

        const res = await fetch(`/api/strategy/${magic}${getQueryString()}`);
        const data = await res.json();
        
        const info = data.strategy_info;
        const met = data.metrics;
        allTradesList = data.trades || [];
        currentPage = 1;
        
        // Header
        document.getElementById("drill-color-dot").style.background = info.color || "#38bdf8";
        document.getElementById("drill-strategy-name").innerText = info.name || `Strategy #${magic}`;
        document.getElementById("drill-magic-badge").innerText = `Magic Number: ${magic}`;
        document.getElementById("drill-strategy-desc").innerText = info.description || "Chưa có mô tả chi tiết";
        
        // Edit modal bind
        document.getElementById("edit-magic").value = magic;
        document.getElementById("edit-magic-display").value = magic;
        document.getElementById("edit-name").value = info.name;
        document.getElementById("edit-desc").value = info.description || "";
        document.getElementById("edit-color-picker").value = info.color || "#38bdf8";
        document.getElementById("edit-color-text").value = info.color || "#38bdf8";

        // Render Scorecard Grid
        renderScorecard(met);

        // Render Equity & Drawdown Chart
        renderEquityDDChart(met.charts.equity_curve, met.charts.underwater_curve);

        // Render Heatmap
        renderHeatmapTable(met.heatmap);

        // Render DOW & HOD
        renderTimingCharts(met.day_of_week, met.hour_of_day);

        // Render Trades Table
        renderTradesTable();

        // Render Strategy Switcher Dropdown
        renderStrategySelect(magic);
        
    } catch (e) {
        console.error("Lỗi load drilldown:", e);
    } finally {
        showLoading(false);
    }
}

function renderStrategySelect(activeMagic) {
    const container = document.getElementById("drill-strategy-select-container");
    if (!container) return;
    
    if (globalStrategiesList.length <= 1) {
        container.classList.add("hidden");
        return;
    }
    container.classList.remove("hidden");
    
    const select = document.getElementById("drill-strategy-select");
    select.innerHTML = "";
    
    globalStrategiesList.forEach(st => {
        const opt = document.createElement("option");
        opt.value = st.magic;
        opt.innerText = `${st.name} (Magic: ${st.magic})`;
        if (st.magic === activeMagic) {
            opt.selected = true;
        }
        select.appendChild(opt);
    });
}

function renderScorecard(met) {
    const grid = document.getElementById("drill-scorecard");
    const sum = met.summary;
    const pay = met.payoff_quality;
    const dd = met.drawdown_risk;
    const inst = met.institutional_ratios;
    const str = met.streaks_timing;

    const cards = [
        { label: "Lợi Nhuận Ròng (Net Profit)", val: formatCurrency(sum.net_profit), color: sum.net_profit >= 0 ? "#10b981" : "#f43f5e" },
        { label: "Win Rate (%)", val: `${sum.win_rate}% (${sum.winning_trades}/${sum.total_trades})`, color: "#38bdf8" },
        { label: "Profit Factor", val: sum.profit_factor, color: "#f8fafc" },
        { label: "Sharpe Ratio (Annualized)", val: inst.sharpe_ratio, color: "#818cf8" },
        { label: "Sortino Ratio", val: inst.sortino_ratio, color: "#a855f7" },
        { label: "Calmar Ratio", val: inst.calmar_ratio, color: "#eab308" },
        { label: "Chỉ Số SQN (Van Tharp)", val: `${pay.sqn} (${pay.sqn_rating})`, color: "#10b981" },
        { label: "Max Drawdown (%)", val: `-${dd.max_drawdown_pct}% (-$${formatNumber(dd.max_drawdown_usd)})`, color: "#f43f5e" },
        { label: "Recovery Factor", val: dd.recovery_factor, color: "#38bdf8" },
        { label: "Payoff Ratio (Avg Win / Avg Loss)", val: `${pay.payoff_ratio} ($${formatNumber(pay.avg_win)} / $${formatNumber(pay.avg_loss)})`, color: "#f8fafc" },
        { label: "Expected Payoff / Trade", val: formatCurrency(pay.expected_payoff), color: pay.expected_payoff >= 0 ? "#10b981" : "#f43f5e" },
        { label: "Chuỗi Thắng / Thua Liên Tiếp", val: `Thắng ${str.max_consecutive_wins} / Thua ${str.max_consecutive_losses}`, color: "#cbd5e1" },
        { label: "Thời Gian Giữ Lệnh Trung Bình", val: str.avg_holding_time_str, color: "#38bdf8" },
        { label: "ROI Thường Niên (Annualized)", val: `${inst.annualized_return_pct}% / năm`, color: "#10b981" }
    ];

    grid.innerHTML = cards.map(c => `
        <div class="scorecard-item">
            <div class="scorecard-label">${c.label}</div>
            <div class="scorecard-val" style="color: ${c.color};">${c.val}</div>
        </div>
    `).join("");
}

function renderEquityDDChart(equityCurve, underwaterCurve) {
    if (chartEquityDD) chartEquityDD.destroy();
    
    const ctx = document.getElementById("chart-equity-dd").getContext("2d");
    const labels = equityCurve.map(d => d.time.replace("T", " ").substring(0, 16));
    
    chartEquityDD = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Tài Sản (Equity USD)',
                    data: equityCurve.map(d => d.value),
                    borderColor: '#38bdf8',
                    backgroundColor: 'rgba(56, 189, 248, 0.1)',
                    fill: true,
                    tension: 0.2,
                    yAxisID: 'yEquity',
                    borderWidth: 2,
                    pointRadius: 0
                },
                {
                    label: 'Sụt Giảm (Drawdown %)',
                    data: underwaterCurve.map(d => d.value),
                    borderColor: '#f43f5e',
                    backgroundColor: 'rgba(244, 63, 94, 0.25)',
                    fill: true,
                    tension: 0.1,
                    yAxisID: 'yDD',
                    borderWidth: 1.5,
                    pointRadius: 0
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            scales: {
                x: { grid: { color: 'rgba(255,255,255,0.04)' }, ticks: { maxTicksLimit: 12 } },
                yEquity: {
                    type: 'linear', position: 'left',
                    grid: { color: 'rgba(255,255,255,0.06)' },
                    title: { display: true, text: 'Equity ($)' }
                },
                yDD: {
                    type: 'linear', position: 'right',
                    grid: { display: false },
                    max: 0,
                    title: { display: true, text: 'Drawdown (%)' }
                }
            }
        }
    });
}

function renderHeatmapTable(heatmapData) {
    const tbody = document.getElementById("tbody-heatmap");
    tbody.innerHTML = "";
    
    if (!heatmapData || heatmapData.length === 0) {
        tbody.innerHTML = `<tr><td colspan="14" class="empty-cell">Chưa có dữ liệu lịch sử tháng...</td></tr>`;
        return;
    }

    const monthKeys = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    
    heatmapData.forEach(row => {
        const tr = document.createElement("tr");
        let html = `<td><strong style="color:#ffffff;">${row.year}</strong></td>`;
        
        monthKeys.forEach(m => {
            const cell = row.months[m];
            if (!cell) {
                html += `<td style="color:#475569;">-</td>`;
            } else {
                const color = cell.pct > 0 ? "rgba(16, 185, 129, 0.25)" : cell.pct < 0 ? "rgba(244, 63, 94, 0.25)" : "transparent";
                const textColor = cell.pct > 0 ? "#10b981" : cell.pct < 0 ? "#f43f5e" : "#94a3b8";
                html += `<td class="heat-cell" style="background:${color}; color:${textColor};" title="+$${cell.usd}">
                            ${cell.pct > 0 ? '+' : ''}${cell.pct}%<br><span style="font-size:10px; opacity:0.8;">$${cell.usd}</span>
                         </td>`;
            }
        });
        
        const totColor = row.total_pct >= 0 ? "#10b981" : "#f43f5e";
        html += `<td><strong style="color:${totColor};">${row.total_pct >= 0 ? '+' : ''}${row.total_pct}%</strong><br><span style="font-size:11px;">$${row.total_usd}</span></td>`;
        
        tr.innerHTML = html;
        tbody.appendChild(tr);
    });
}

function renderTimingCharts(dowData, hodData) {
    if (chartDow) chartDow.destroy();
    if (chartHod) chartHod.destroy();

    const ctxDow = document.getElementById("chart-dow").getContext("2d");
    chartDow = new Chart(ctxDow, {
        type: 'bar',
        data: {
            labels: dowData.map(d => d.day.substring(0, 3)),
            datasets: [{
                label: 'Lợi Nhuận ($)',
                data: dowData.map(d => d.net_profit),
                backgroundColor: dowData.map(d => d.net_profit >= 0 ? '#10b981' : '#f43f5e'),
                borderRadius: 6
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } }
        }
    });

    const ctxHod = document.getElementById("chart-hod").getContext("2d");
    chartHod = new Chart(ctxHod, {
        type: 'bar',
        data: {
            labels: hodData.map(d => d.hour),
            datasets: [{
                label: 'Lợi Nhuận ($)',
                data: hodData.map(d => d.net_profit),
                backgroundColor: hodData.map(d => d.net_profit >= 0 ? '#38bdf8' : '#f43f5e'),
                borderRadius: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } }
        }
    });
}

/* --------------------------------------------------------------------------------------
   TRADES TABLE PAGINATION & SEARCH
-------------------------------------------------------------------------------------- */
function getFilteredTrades() {
    const query = document.getElementById("trade-search").value.trim().toLowerCase();
    const filterDir = document.getElementById("trade-filter-dir").value;
    const filterResult = document.getElementById("trade-filter-result").value;
    
    let list = allTradesList;
    
    // 1. Lọc theo chiều (Direction)
    if (filterDir !== "ALL") {
        list = list.filter(t => t.direction === filterDir);
    }
    
    // 2. Lọc theo kết quả (Result)
    if (filterResult !== "ALL") {
        if (filterResult === "PROFIT") {
            list = list.filter(t => t.net_profit > 0);
        } else if (filterResult === "LOSS") {
            list = list.filter(t => t.net_profit < 0);
        }
    }
    
    // 3. Tìm kiếm từ khóa
    if (query) {
        list = list.filter(t => 
            strVal(t.symbol).toLowerCase().includes(query) ||
            strVal(t.ticket).includes(query) ||
            strVal(t.comment).toLowerCase().includes(query)
        );
    }
    
    // 4. Sắp xếp (Sorting)
    list.sort((a, b) => {
        let valA = a[currentSortField];
        let valB = b[currentSortField];
        
        // Handle numeric fields
        if (["ticket", "volume", "open_price", "close_price", "hold_duration_sec", "net_profit"].includes(currentSortField)) {
            valA = parseFloat(valA) || 0;
            valB = parseFloat(valB) || 0;
        } else if (currentSortField === "commission_swap") {
            valA = (parseFloat(a.commission) || 0) + (parseFloat(a.swap) || 0);
            valB = (parseFloat(b.commission) || 0) + (parseFloat(b.swap) || 0);
        } else {
            // Strings / Dates
            valA = String(valA || "").toLowerCase();
            valB = String(valB || "").toLowerCase();
        }
        
        if (valA < valB) return currentSortOrder === "asc" ? -1 : 1;
        if (valA > valB) return currentSortOrder === "asc" ? 1 : -1;
        return 0;
    });
    
    return list;
}

function renderTradesTable() {
    const filtered = getFilteredTrades();
    const totalPages = Math.ceil(filtered.length / pageSize) || 1;
    if (currentPage > totalPages) currentPage = totalPages;
    
    const startIdx = (currentPage - 1) * pageSize;
    const pageTrades = filtered.slice(startIdx, startIdx + pageSize);
    
    const tbody = document.getElementById("tbody-trades");
    tbody.innerHTML = "";
    
    if (pageTrades.length === 0) {
        tbody.innerHTML = `<tr><td colspan="11" class="empty-cell">Không tìm thấy lệnh nào phù hợp...</td></tr>`;
    } else {
        pageTrades.forEach(t => {
            const tr = document.createElement("tr");
            const pnlClass = t.net_profit >= 0 ? "badge badge-green" : "badge badge-red";
            const dirBadge = t.direction === "LONG" ? "badge badge-blue" : "badge badge-amber";
            
            tr.innerHTML = `
                <td><code style="color:#38bdf8;">#${t.ticket}</code></td>
                <td><strong style="color:#ffffff;">${t.symbol}</strong></td>
                <td><span class="${dirBadge}">${t.direction}</span></td>
                <td>${t.volume}</td>
                <td>${formatNumber(t.open_price)}</td>
                <td>${formatNumber(t.close_price)}</td>
                <td><span style="font-size:12px; color:#cbd5e1;">${t.close_time.replace("T", " ").substring(0, 19)}</span></td>
                <td><span style="font-size:11px; color:#94a3b8;">${formatDurationSec(t.hold_duration_sec)}</span></td>
                <td><span style="font-size:11px; color:#94a3b8;">$${formatNumber(t.commission + t.swap)}</span></td>
                <td><span class="${pnlClass}">${formatCurrency(t.net_profit)}</span></td>
                <td><span style="font-size:11px; color:#64748b;">${t.comment || '-'}</span></td>
            `;
            tbody.appendChild(tr);
        });
    }

    document.getElementById("page-info").innerText = `Trang ${currentPage} / ${totalPages} (Tổng ${filtered.length} lệnh)`;
}

function openEditModal() {
    document.getElementById("modal-edit").classList.remove("hidden");
}

async function saveStrategyConfig() {
    const magic = document.getElementById("edit-magic").value;
    const name = document.getElementById("edit-name").value;
    const desc = document.getElementById("edit-desc").value;
    const color = document.getElementById("edit-color-picker").value;
    
    const formData = new FormData();
    formData.append("magic", magic);
    formData.append("name", name);
    formData.append("description", desc);
    formData.append("color", color);
    
    try {
        const res = await fetch("/api/strategy_name", { method: "POST", body: formData });
        const data = await res.json();
        if (data.success) {
            alert("✅ " + data.message);
        }
    } catch (e) {
        alert("❌ Lỗi lưu cấu hình: " + e);
    }
}

/* --------------------------------------------------------------------------------------
   HELPER FORMATTERS
-------------------------------------------------------------------------------------- */
function formatCurrency(val) {
    if (val === undefined || val === null) return "$0.00";
    const num = parseFloat(val);
    return (num < 0 ? "-" : "") + "$" + Math.abs(num).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatNumber(val) {
    if (val === undefined || val === null) return "0.00";
    return parseFloat(val).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 4 });
}

function formatDurationSec(sec) {
    if (!sec || sec <= 0) return "-";
    const m = Math.floor(sec / 60);
    const h = Math.floor(m / 60);
    const d = Math.floor(h / 24);
    if (d > 0) return `${d}d ${h%24}h`;
    if (h > 0) return `${h}h ${m%60}m`;
    return `${m}m`;
}

function intVal(v) { return parseInt(v) || 0; }
function strVal(v) { return v !== undefined && v !== null ? str(v) : ""; }
function str(v) { return String(v); }
