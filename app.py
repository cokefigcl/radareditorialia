async function loadTrending(force = false) {
    const list = document.getElementById('trendingList');
    list.innerHTML = `<div class="perro-loader-container"><img src="https://ltv.cl/x/uriweb.png" alt="Perro detective" class="perro-loader"><div class="perro-loader-text">${getRandomPhrase(perroPhrases)}</div></div>`;
    try {
        const refreshParam = force ? '&refresh=true' : '';
        const url = '/api/trending?category=' + encodeURIComponent(currentCategory) + '&limit=8' + refreshParam;
        const res = await fetch(url);
        const data = await res.json();
        const trends = data.trends || [];
        const status = data.source_status || {};
        
        if (!trends || trends.length === 0) {
            // Verificar si es por bloqueo o realmente no hay datos
            const blocked = Object.values(status).some(s => s === 'blocked_or_empty');
            const msg = blocked ? '⚠️ Algunas fuentes están bloqueadas temporalmente. Intenta actualizar más tarde.' : 'Sin tendencias disponibles para esta categoría';
            list.innerHTML = `<div class="empty-state">${msg}</div>`;
            return;
        }
        
        let html = '';
        trends.forEach((t, i) => {
            html += `<div class="trend-item" onclick="useTrend('${t.topic.replace(/'/g, "\\'").replace(/"/g, '&quot;')}')">
                <div class="topic">${i + 1}. ${t.topic}</div>
                <div class="meta">📊 ${t.source || 'Medio'} | ${t.region || 'Chile'}</div>
            </div>`;
        });
        list.innerHTML = html;
    } catch (err) { list.innerHTML = '<div class="empty-state">Error cargando</div>'; }
}

async function loadPredictions(force = false) {
    const list = document.getElementById('predictionsList');
    list.innerHTML = `<div class="gata-loader-container"><img src="https://ltv.cl/x/maybisweb.png" alt="Gata vidente" class="gata-loader"><div class="gata-loader-text">${getRandomPhrase(gataPhrases)}</div></div>`;
    try {
        const refreshParam = force ? '?refresh=true' : '';
        const res = await fetch('/api/predictions' + refreshParam);
        const data = await res.json();
        const predictions = data.predictions || [];
        const status = data.source_status || {};
        
        if (!predictions || predictions.length === 0) {
            const blocked = Object.values(status).some(s => s === 'blocked_or_empty');
            const msg = blocked ? '⚠️ Fuentes bloqueadas. Usando datos en caché o reintentando...' : 'Sin predicciones disponibles';
            list.innerHTML = `<div class="empty-state">${msg}</div>`;
            return;
        }
        
        let html = '';
        predictions.forEach(p => {
            const scoreClass = p.score >= 70 ? 'score-high' : (p.score >= 40 ? 'score-medium' : 'score-low');
            const cardClass = p.alert_level === 'critical' ? 'critical' : (p.alert_level === 'high' ? 'high' : '');
            html += `<div class="prediction-item ${cardClass}">
                <div class="prediction-top">
                    <div class="prediction-topic">${p.topic}${p.is_realtime ? '<span class="realtime-badge">LIVE</span>' : ''}</div>
                    <div class="prediction-score ${scoreClass}">${p.score}%</div>
                </div>
                <div class="prediction-meta">
                    <span>📂 ${p.category || 'General'}</span>
                    <span>📰 ${p.news_count} artículos</span>
                    <span>📡 ${p.sources ? p.sources.join(', ') : p.source}</span>
                </div>`;
            if (p.alert_level) {
                const alertText = p.alert_level === 'critical' ? '🚨 ALERTA CRÍTICA' : '⚠️ ALERTA: Crecimiento acelerado';
                html += `<div class="prediction-alert">${alertText}</div>`;
            }
            html += '</div>';
        });
        list.innerHTML = html;
    } catch (err) { list.innerHTML = '<div class="empty-state">Error cargando</div>'; }
}
