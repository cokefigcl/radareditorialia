<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
    <title>Dashboard - Cora Radar Editorial</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; color: #333; }
        .topbar { background: white; padding: 12px 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 15px; position: sticky; top: 0; z-index: 100; }
        .topbar-title { font-size: 18px; font-weight: 700; color: #1a1a1a; }
        .topbar-title span { color: #11998e; }
        .topbar-nav { display: flex; gap: 10px; align-items: center; }
        .nav-btn { padding: 6px 14px; background: #007bff; color: white; border: none; border-radius: 6px; cursor: pointer; font-size: 13px; text-decoration: none; }
        .nav-btn:hover { background: #0056b3; }
        .nav-btn.secondary { background: #6c757d; }
        .nav-btn.secondary:hover { background: #545b62; }
        .dashboard-container { max-width: 1400px; margin: 20px auto; padding: 0 20px; }
        .module { background: white; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); margin-bottom: 20px; overflow: hidden; }
        .module-header { padding: 15px 20px; border-bottom: 1px solid #e0e0e0; display: flex; justify-content: space-between; align-items: center; background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%); color: white; }
        .module-header h3 { font-size: 16px; font-weight: 700; }
        .module-header button { background: rgba(255,255,255,0.2); border: 1px solid rgba(255,255,255,0.3); color: white; padding: 5px 10px; border-radius: 6px; cursor: pointer; font-size: 11px; }
        .module-header button:hover { background: rgba(255,255,255,0.3); }
        .module-body { padding: 20px; }
        .kpi-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin-bottom: 20px; }
        @media (max-width: 900px) { .kpi-grid { grid-template-columns: repeat(2, 1fr); } }
        .kpi-card { color: white; padding: 20px; border-radius: 10px; }
        .kpi-card .label { font-size: 12px; opacity: 0.9; margin-bottom: 5px; }
        .kpi-card .value { font-size: 32px; font-weight: bold; }
        .kpi-card .sublabel { font-size: 11px; opacity: 0.8; margin-top: 5px; }
        .kpi-1 { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); }
        .kpi-2 { background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); }
        .kpi-3 { background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); }
        .kpi-4 { background: linear-gradient(135deg, #fa709a 0%, #fee140 100%); }
        .charts-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 20px; margin-bottom: 20px; }
        @media (max-width: 1100px) { .charts-grid { grid-template-columns: 1fr 1fr; } }
        @media (max-width: 700px) { .charts-grid { grid-template-columns: 1fr; } }
        .chart-card { background: #f8f9fa; padding: 20px; border-radius: 10px; }
        .chart-card h4 { font-size: 14px; color: #666; margin-bottom: 15px; }
        .chart-container { position: relative; height: 250px; }
        .sources-table { width: 100%; border-collapse: collapse; margin-top: 15px; }
        .sources-table th, .sources-table td { padding: 10px; text-align: left; border-bottom: 1px solid #e0e0e0; font-size: 13px; }
        .sources-table th { background: #f8f9fa; font-weight: 600; color: #666; }
        .status-ok { color: #28a745; font-weight: 600; }
        .status-error { color: #dc3545; font-weight: 600; }
        .status-empty { color: #ffc107; font-weight: 600; }
        .footer { text-align: center; padding: 15px; color: #666; font-size: 11px; }
        .footer a { color: #007bff; text-decoration: none; }
        .loading { text-align: center; padding: 40px; color: #999; }
    </style>
</head>
<body>
    <div class="topbar">
        <div class="topbar-title">📊 Dashboard <span>Cora</span></div>
        <div class="topbar-nav">
            <a href="/" class="nav-btn secondary">← Volver al Radar</a>
            <button onclick="loadAll()" class="nav-btn">🔄 Actualizar</button>
        </div>
    </div>
    
    <div class="dashboard-container">
        <div class="kpi-grid">
            <div class="kpi-card kpi-1">
                <div class="label">Total Artículos</div>
                <div class="value" id="statTotal">--</div>
                <div class="sublabel">Recolectados hoy</div>
            </div>
            <div class="kpi-card kpi-2">
                <div class="label">Fuentes Activas</div>
                <div class="value" id="statSources">--</div>
                <div class="sublabel">Medios + APIs</div>
            </div>
            <div class="kpi-card kpi-3">
                <div class="label">Tendencias Detectadas</div>
                <div class="value" id="statTrends">--</div>
                <div class="sublabel">Google Trends + Wiki</div>
            </div>
            <div class="kpi-card kpi-4">
                <div class="label">Predicciones IA</div>
                <div class="value" id="statPredictions">--</div>
                <div class="sublabel">Análisis cruzado</div>
            </div>
        </div>
        
        <div class="kpi-grid">
            <div class="kpi-card" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);">
                <div class="label">Total Solicitudes IA</div>
                <div class="value" id="usageTotalRequests">--</div>
                <div class="sublabel">Todas las APIs</div>
            </div>
            <div class="kpi-card" style="background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);">
                <div class="label">Tasa de Éxito</div>
                <div class="value" id="usageSuccessRate">--</div>
                <div class="sublabel">Solicitudes exitosas</div>
            </div>
            <div class="kpi-card" style="background: linear-gradient(135deg, #fc4a1a 0%, #f7b733 100%);">
                <div class="label">Tokens Usados</div>
                <div class="value" id="usageTotalTokens">--</div>
                <div class="sublabel">Input + Output</div>
            </div>
            <div class="kpi-card" style="background: linear-gradient(135deg, #ee0979 0%, #ff6a00 100%);">
                <div class="label">Costo Total</div>
                <div class="value" id="usageTotalCost">--</div>
                <div class="sublabel">USD estimado</div>
            </div>
        </div>
        
        <div class="module">
            <div class="module-header">
                <h3>📈 Análisis Visual de Datos</h3>
            </div>
            <div class="module-body">
                <div class="charts-grid">
                    <div class="chart-card">
                        <h4>📂 Distribución por Categoría</h4>
                        <div class="chart-container">
                            <canvas id="categoryChart"></canvas>
                        </div>
                    </div>
                    <div class="chart-card">
                        <h4>📡 Aporte por Fuente</h4>
                        <div class="chart-container">
                            <canvas id="sourceChart"></canvas>
                        </div>
                    </div>
                    <div class="chart-card">
                        <h4>🎯 Distribución de Scores</h4>
                        <div class="chart-container">
                            <canvas id="scoreChart"></canvas>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        
        <div class="module">
            <div class="module-header" style="background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);">
                <h3>🤖 Uso de APIs (Qwen)</h3>
            </div>
            <div class="module-body">
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
                    <div class="chart-card">
                        <h4>📈 Uso por Día (últimos 7 días)</h4>
                        <div class="chart-container" style="height: 200px;">
                            <canvas id="usageDailyChart"></canvas>
                        </div>
                    </div>
                    <div class="chart-card">
                        <h4>🔌 Uso por Endpoint</h4>
                        <div class="chart-container" style="height: 200px;">
                            <canvas id="usageEndpointChart"></canvas>
                        </div>
                    </div>
                </div>
                <div style="margin-top: 15px; padding: 15px; background: #f8f9fa; border-radius: 8px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 15px;">
                        <div>
                            <strong>📅 Hoy:</strong>
                            <span id="usageTodayRequests" style="margin-left: 10px; font-size: 18px; font-weight: bold;">--</span>
                            solicitudes
                        </div>
                        <div>
                            <strong>💰 Costo hoy:</strong>
                            <span id="usageTodayCost" style="margin-left: 10px; font-size: 18px; font-weight: bold; color: #28a745;">--</span>
                            USD
                        </div>
                    </div>
                </div>
            </div>
        </div>
        
        <div class="module">
            <div class="module-header" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);">
                <h3>🔌 Estado de Fuentes</h3>
            </div>
            <div class="module-body">
                <table class="sources-table">
                    <thead>
                        <tr>
                            <th>Fuente</th>
                            <th>Estado</th>
                            <th>Artículos</th>
                        </tr>
                    </thead>
                    <tbody id="sourcesTableBody">
                        <tr><td colspan="3" class="loading">Cargando...</td></tr>
                    </tbody>
                </table>
            </div>
        </div>
    </div>
    
    <div class="footer">
        Desarrollado por <a href="https://ltv.cl" target="_blank">Joesramirez</a> - LTV.cl | Dashboard v12.0
    </div>

    <script>
        let categoryChartInstance = null;
        let sourceChartInstance = null;
        let scoreChartInstance = null;
        let usageDailyChartInstance = null;
        let usageEndpointChartInstance = null;

        async function loadDashboard() {
            try {
                const res = await fetch('/api/statistics?_t=' + Date.now(), { cache: 'no-store' });
                const data = await res.json();
                if (data.error) return;
                
                const stats = data.stats || {};
                const sourceStatus = data.source_status || {};
                
                document.getElementById('statTotal').textContent = stats.total_articles || 0;
                document.getElementById('statSources').textContent = stats.sources_count || 0;
                document.getElementById('statTrends').textContent = stats.trends_detected || 0;
                document.getElementById('statPredictions').textContent = data.predictions_count || 0;
                
                const catLabels = Object.keys(stats.by_category || {});
                const catData = Object.values(stats.by_category || {});
                const catColors = ['#667eea', '#f093fb', '#4facfe', '#fa709a', '#fee140', '#38ef7d', '#11998e', '#ff6b6b', '#feca57', '#a29bfe'];
                
                if (categoryChartInstance) categoryChartInstance.destroy();
                categoryChartInstance = new Chart(document.getElementById('categoryChart'), {
                    type: 'doughnut',
                    data: { labels: catLabels.slice(0, 10), datasets: [{ data: catData.slice(0, 10), backgroundColor: catColors, borderWidth: 2, borderColor: '#fff' }] },
                    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom', labels: { font: { size: 10 }, padding: 10 } } } }
                });
                
                const srcLabels = Object.keys(stats.by_source || {});
                const srcData = Object.values(stats.by_source || {});
                const srcColors = ['#ff6b6b', '#4ecdc4', '#45b7d1', '#96ceb4', '#ffeaa7', '#dfe6e9', '#fd79a8', '#a29bfe', '#fdcb6e', '#6c5ce7'];
                
                if (sourceChartInstance) sourceChartInstance.destroy();
                sourceChartInstance = new Chart(document.getElementById('sourceChart'), {
                    type: 'bar',
                    data: { labels: srcLabels, datasets: [{ label: 'Artículos', data: srcData, backgroundColor: srcColors, borderRadius: 6 }] },
                    options: { responsive: true, maintainAspectRatio: false, indexAxis: 'y', plugins: { legend: { display: false } }, scales: { y: { ticks: { font: { size: 11 } } }, x: { beginAtZero: true, ticks: { font: { size: 10 } } } } }
                });
                
                const scoreDist = data.predictions_by_score || {high: 0, medium: 0, low: 0};
                if (scoreChartInstance) scoreChartInstance.destroy();
                scoreChartInstance = new Chart(document.getElementById('scoreChart'), {
                    type: 'pie',
                    data: { labels: ['Alto (70-100)', 'Medio (40-69)', 'Bajo (0-39)'], datasets: [{ data: [scoreDist.high, scoreDist.medium, scoreDist.low], backgroundColor: ['#28a745', '#ffc107', '#dc3545'], borderWidth: 2, borderColor: '#fff' }] },
                    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom', labels: { font: { size: 11 }, padding: 10 } } } }
                });
                
                const tbody = document.getElementById('sourcesTableBody');
                tbody.innerHTML = '';
                const sourceNames = {
                    'biobio': 'BioBioChile', 'latercera': 'La Tercera', 'cooperativa': 'Cooperativa', 'df': 'Diario Financiero',
                    'emol': 'Emol', 'ciper': 'CIPER Chile', '24horas': '24 Horas', 'bbc_mundo': 'BBC Mundo',
                    'elpais': 'El País América', 'cnn_es': 'CNN en Español', 'dw_es': 'DW Español', 'france24': 'France 24',
                    'reuters': 'Reuters', 'guardian': 'The Guardian', 'aljazeera': 'Al Jazeera', 'techcrunch': 'TechCrunch',
                    'ap_news': 'AP News', 'reddit': 'Reddit', 'youtube': 'YouTube Trending', 'trends': 'Google Trends'
                };
                
                for (const [key, value] of Object.entries(stats.by_source || {})) {
                    const status = sourceStatus[key] || 'unknown';
                    // CORRECCIÓN DEFINITIVA: Si hay artículos, está OK, sin importar el estado del caché
                    const actualStatus = value > 0 ? 'ok' : (status === 'unknown' ? 'empty' : status);
                    const statusClass = actualStatus === 'ok' ? 'status-ok' : (actualStatus === 'empty' ? 'status-empty' : 'status-error');
                    const statusText = actualStatus === 'ok' ? '✅ OK' : (actualStatus === 'empty' ? '⚠️ Vacío' : '❌ Error');
                    const displayName = sourceNames[key] || key;
                    
                    tbody.innerHTML += `<tr><td><strong>${displayName}</strong></td><td class="${statusClass}">${statusText}</td><td>${value} artículos</td></tr>`;
                }
            } catch (err) { console.error('[DASHBOARD] Error:', err); }
        }

        async function loadUsageStats() {
            try {
                const res = await fetch('/api/usage?_t=' + Date.now(), { cache: 'no-store' });
                const data = await res.json();
                if (data.error) return;
                
                document.getElementById('usageTotalRequests').textContent = data.total_requests || 0;
                document.getElementById('usageSuccessRate').textContent = (data.success_rate || 0) + '%';
                document.getElementById('usageTotalTokens').textContent = (data.total_tokens || 0).toLocaleString();
                document.getElementById('usageTotalCost').textContent = '$' + (data.total_cost || 0).toFixed(4);
                document.getElementById('usageTodayRequests').textContent = data.today_requests || 0;
                document.getElementById('usageTodayCost').textContent = '$' + (data.today_cost || 0).toFixed(4);
                
                const dailyLabels = data.daily_usage.map(d => d.day);
                const dailyRequests = data.daily_usage.map(d => d.requests);
                const dailyCosts = data.daily_usage.map(d => d.cost);
                
                if (usageDailyChartInstance) usageDailyChartInstance.destroy();
                usageDailyChartInstance = new Chart(document.getElementById('usageDailyChart'), {
                    type: 'line',
                    data: { labels: dailyLabels, datasets: [
                        { label: 'Solicitudes', data: dailyRequests, borderColor: '#667eea', backgroundColor: 'rgba(102, 126, 234, 0.1)', tension: 0.4, fill: true },
                        { label: 'Costo (USD)', data: dailyCosts, borderColor: '#f5576c', backgroundColor: 'rgba(245, 87, 108, 0.1)', tension: 0.4, fill: true, yAxisID: 'y1' }
                    ]},
                    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom', labels: { font: { size: 10 } } } }, scales: { y: { beginAtZero: true, ticks: { font: { size: 10 } } }, y1: { position: 'right', beginAtZero: true, ticks: { font: { size: 10 } }, grid: { drawOnChartArea: false } } } }
                });
                
                const endpointLabels = data.by_endpoint.map(e => e.endpoint);
                const endpointCounts = data.by_endpoint.map(e => e.count);
                const endpointColors = ['#667eea', '#f093fb', '#4facfe', '#fa709a', '#fee140'];
                
                if (usageEndpointChartInstance) usageEndpointChartInstance.destroy();
                usageEndpointChartInstance = new Chart(document.getElementById('usageEndpointChart'), {
                    type: 'bar',
                    data: { labels: endpointLabels, datasets: [{ label: 'Solicitudes', data: endpointCounts, backgroundColor: endpointColors, borderRadius: 6 }] },
                    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true, ticks: { font: { size: 10 } } }, x: { ticks: { font: { size: 10 }, maxRotation: 45 } } } }
                });
            } catch (err) { console.error('[USAGE] Error:', err); }
        }

        async function loadAll() {
            await loadDashboard();
            await loadUsageStats();
        }

        loadAll();
    </script>
</body>
</html>
