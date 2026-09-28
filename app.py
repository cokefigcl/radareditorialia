from flask import Flask, render_template, jsonify, request
import os
import json
import re
import time
import random
import math
import unicodedata
from datetime import datetime, timezone, timedelta
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from email.utils import parsedate_to_datetime
import xml.etree.ElementTree as ET

from dotenv import load_dotenv
from bs4 import BeautifulSoup
from curl_cffi import requests as cr

load_dotenv()

app = Flask(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), 'trends.db')
CACHE_FILE = os.path.join(os.path.dirname(__file__), 'news_cache.json')

CATEGORIES = [
    {'name': 'Eléctrico', 'icon': '', 'type': 'tema'},
    {'name': 'Automotriz', 'icon': '', 'type': 'tema'},
    {'name': 'Belleza', 'icon': '💄', 'type': 'tema'},
    {'name': 'Minería', 'icon': '⛏️', 'type': 'tema'},
    {'name': 'IA', 'icon': '🤖', 'type': 'tema'},
    {'name': 'Tendencias', 'icon': '📈', 'type': 'tema'},
    {'name': 'Tecnología', 'icon': '💻', 'type': 'tema'},
    {'name': 'Economía', 'icon': '💰', 'type': 'tema'},
    {'name': 'Chile', 'icon': '🇨🇱', 'type': 'region'},
    {'name': 'Internacional', 'icon': '🌍', 'type': 'region'},
    {'name': 'Deportes', 'icon': '⚽', 'type': 'otros'},
    {'name': 'Ciencia y Tecnología', 'icon': '🔬', 'type': 'otros'},
    {'name': 'Cultura', 'icon': '🎭', 'type': 'otros'},
    {'name': 'Ocio', 'icon': '🎮', 'type': 'otros'},
    {'name': 'Salud', 'icon': '🏥', 'type': 'otros'},
    {'name': 'Sociedad', 'icon': '👥', 'type': 'otros'},
    {'name': 'TV y Espectáculos', 'icon': '📺', 'type': 'otros'}
]

SEARCH_KEYWORDS = {
    'Eléctrico': 'eléctricas OR transmisión OR distribución',
    'Automotriz': 'autos OR vehículos OR electromovilidad',
    'Belleza': 'belleza OR cosmética',
    'Minería': 'minería OR cobre OR litio',
    'IA': 'inteligencia artificial OR IA',
    'Tendencias': 'tendencias',
    'Tecnología': 'tecnología OR 5G',
    'Economía': 'economía OR dólar OR inflación',
    'Chile': 'chile',
    'Internacional': 'internacional',
    'Deportes': 'deportes OR fútbol',
    'Ciencia y Tecnología': 'ciencia OR tecnología',
    'Cultura': 'cultura OR arte',
    'Ocio': 'ocio OR entretenimiento',
    'Salud': 'salud OR medicina',
    'Sociedad': 'sociedad',
    'TV y Espectáculos': 'televisión OR espectáculos'
}

SOURCES = {
    "biobio": {"home": "https://www.biobiochile.cl/", "domain": "biobiochile.cl"},
    "latercera": {"home": "https://www.latercera.com/", "domain": "latercera.com"},
    "cooperativa": {"home": "https://www.cooperativa.cl/", "domain": "cooperativa.cl"},
    "df": {"home": "https://www.df.cl/", "domain": "df.cl"},
}

STOPWORDS = {'el', 'la', 'los', 'las', 'un', 'una', 'de', 'del', 'al', 'y', 'o', 'que', 'por', 'para', 'con', 'en', 'a', 'se', 'su', 'chile', 'santiago', 'hoy', 'más', 'the', 'and', 'for', 'that', 'this', 'es', 'son', 'como', 'pero', 'también', 'sin', 'sobre', 'entre', 'inicio', 'contacto', 'publicidad', 'suscríbete', 'términos', 'privacidad', 'cookies', 'buscar', 'buscar', 'menú', 'menu', 'siguiente', 'anterior', 'compartir', 'leer', 'nota', 'artículo', 'video', 'foto', 'galería', 'relacionado', 'temas', 'tags', 'etiquetas'}

TOKEN_RE = re.compile(r"[a-zñ0-9]{4,}")
ENTITY_RE = re.compile(r"\b[A-ZÁÉÍÓÚÑ][a-záéíóúñ]{2,}(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]{2,})+\b")

def _norm(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s.lower()) if not unicodedata.combining(c))

def _get(url: str, retries: int = 3, timeout: int = 10) -> str | None:
    for i in range(retries):
        try:
            r = cr.get(url, impersonate="chrome", timeout=timeout,
                       headers={"Accept-Language": "es-CL,es;q=0.9", "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"})
            if r.status_code == 200:
                return r.text
            if r.status_code in (403, 429, 503):
                time.sleep((2 ** i) + random.random())
                continue
            return None
        except Exception:
            time.sleep(1 + i)
    return None

def _from_homepage(name: str, cfg: dict):
    html = _get(cfg["home"])
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    seen, out = set(), []
    
    for tag in soup.select("h1, h2, h3, h4"):
        t = " ".join(tag.get_text(" ", strip=True).split())
        if len(t) < 30 or len(t) > 150 or t in seen:
            continue
        if any(w in t.lower() for w in ['inicio', 'contacto', 'suscríbete', 'publicidad', 'términos']):
            continue
        seen.add(t)
        a = tag.find("a") or tag.find_parent("a") or tag
        out.append({
            'title': t,
            'source': name,
            'url': a.get("href", "") if a else "",
            'first_seen': datetime.now(timezone.utc).isoformat()
        })
    return out

def _from_gnews(name: str, cfg: dict):
    url = (f"https://news.google.com/rss/search?q=site:{cfg['domain']}+when:1d"
           "&hl=es-419&gl=CL&ceid=CL:es-419")
    xml = _get(url)
    if not xml:
        return []
    out = []
    try:
        root = ET.fromstring(xml)
        for it in root.iter("item"):
            title = (it.findtext("title") or "").rsplit(" - ", 1)[0].strip()
            try:
                ts = parsedate_to_datetime(it.findtext("pubDate"))
            except:
                ts = datetime.now(timezone.utc)
            if title and len(title) > 30:
                out.append({
                    'title': title,
                    'source': name,
                    'url': it.findtext("link") or "",
                    'first_seen': ts.isoformat()
                })
    except Exception:
        pass
    return out

def get_cached_data(max_age_minutes=60):
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                cache = json.load(f)
                timestamp = datetime.fromisoformat(cache['timestamp'])
                if datetime.now(timezone.utc) - timestamp.replace(tzinfo=timezone.utc) < timedelta(minutes=max_age_minutes):
                    print(f"[CACHE] ✅ Usando caché ({len(cache['articles'])} artículos)")
                    return cache['articles'], cache.get('status', {})
        except Exception as e:
            print(f"[CACHE] Error: {str(e)}")
    return None, None

def save_to_cache(articles, status):
    if not articles: return
    try:
        temp_path = CACHE_FILE + '.tmp'
        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump({
                'articles': articles,
                'status': status,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }, f, ensure_ascii=False)
        os.replace(temp_path, CACHE_FILE)
        print(f"[CACHE] 💾 Guardados {len(articles)} artículos")
    except Exception as e:
        print(f"[CACHE] Error guardando: {str(e)}")

def fetch_raw_articles(force_refresh=False):
    if not force_refresh:
        articles, status = get_cached_data(max_age_minutes=60)
        if articles:
            return articles, status

    print("[FETCH] Iniciando recolección...")
    
    def work(item):
        name, cfg = item
        arts = _from_homepage(name, cfg)
        if arts:
            return name, arts, "ok"
        arts = _from_gnews(name, cfg)
        return name, arts, "ok_fallback" if arts else "blocked_or_empty"

    articles, status = [], {}
    with ThreadPoolExecutor(max_workers=4) as ex:
        for name, arts, st in ex.map(work, SOURCES.items()):
            articles.extend(arts)
            status[name] = st
            print(f"[FETCH] {name}: {len(arts)} artículos - {st}")

    seen = set()
    unique_articles = []
    for a in articles:
        if a['title'] not in seen:
            seen.add(a['title'])
            unique_articles.append(a)

    print(f"[FETCH] Total artículos únicos: {len(unique_articles)}")
    save_to_cache(unique_articles, status)
    return unique_articles, status

def predict_trends(articles, top: int = 8):
    """Predicción basada en TITULARES COMPLETOS, no palabras sueltas"""
    if not articles:
        return []
    
    now = datetime.now(timezone.utc)
    
    # Agrupar por similitud de titulares
    headline_groups = defaultdict(list)
    
    for a in articles:
        title = a['title']
        # Normalizar título para agrupación
        norm_title = _norm(title)
        words = TOKEN_RE.findall(norm_title)
        ok_words = [w for w in words if w not in STOPWORDS and len(w) > 3]
        
        if len(ok_words) < 3:
            continue
            
        # Crear clave de agrupación con las 5 palabras más significativas
        key = ' '.join(sorted(ok_words[:5]))
        
        first_seen = a.get('first_seen')
        if isinstance(first_seen, str):
            try:
                first_seen = datetime.fromisoformat(first_seen.replace('Z', '+00:00'))
            except:
                first_seen = now
        if not first_seen:
            first_seen = now
            
        age_h = ((now - first_seen).total_seconds() / 3600)
        
        headline_groups[key].append({
            'title': title,
            'source': a['source'],
            'age_h': age_h
        })
    
    # Calcular score por grupo
    scored = []
    for key, items in headline_groups.items():
        sources = set(item['source'] for item in items)
        n_articles = len(items)
        
        # Requiere al menos 2 fuentes distintas o 3+ artículos
        if len(sources) < 2 and n_articles < 3:
            continue
        
        # Calcular recencia promedio
        avg_age = sum(item['age_h'] for item in items) / n_articles
        recency_score = max(0, 1 - (avg_age / 12))  # Máximo 12 horas
        
        # Score basado en diversidad de fuentes y volumen
        diversity = min(1, (len(sources) - 1) / 3)
        volume = min(1, math.log1p(n_articles) / math.log1p(10))
        
        score = round(100 * (0.40 * diversity + 0.35 * volume + 0.25 * recency_score))
        
        # Usar el titular más reciente como representativo
        items.sort(key=lambda x: x['age_h'])
        representative_title = items[0]['title']
        
        scored.append({
            'topic': representative_title,
            'score': score,
            'sources': sorted(sources),
            'articles': n_articles,
            'level': 'critica' if score > 85 else 'alta' if score > 70 else 'media'
        })
    
    scored.sort(key=lambda x: x['score'], reverse=True)
    
    # Eliminar duplicados semánticos
    result = []
    for s in scored[:top * 2]:  # Tomar más para filtrar duplicados
        is_duplicate = False
        for r in result:
            # Verificar similitud de palabras clave
            words_s = set(TOKEN_RE.findall(_norm(s['topic'])))
            words_r = set(TOKEN_RE.findall(_norm(r['topic'])))
            overlap = len(words_s & words_r) / max(len(words_s), len(words_r))
            if overlap > 0.7:
                is_duplicate = True
                break
        
        if not is_duplicate:
            result.append({
                'topic': s['topic'],
                'score': s['score'],
                'category': guess_category(s['topic']),
                'news_count': s['articles'],
                'news': [{'titulo': s['topic'], 'fuente': ', '.join(s['sources']), 'url': '', 'fecha': now.strftime('%Y-%m-%d')}],
                'alert_level': 'critical' if s['level'] == 'critica' else ('high' if s['level'] == 'alta' else None),
                'source': 'Algoritmo de Crecimiento',
                'is_realtime': True,
                'timestamp': now.isoformat()
            })
            
            if len(result) >= top:
                break
    
    return result

def guess_category(topic):
    topic_lower = topic.lower()
    keywords = {
        'Deportes': ['fútbol', 'deporte', 'selección', 'campeonato', 'partido', 'gol'],
        'Economía': ['dólar', 'inflación', 'economía', 'peso', 'cobre', 'financiero', 'mercado'],
        'Chile': ['gobierno', 'presidente', 'congreso', 'ley', 'chile', 'ministro'],
        'Internacional': ['eeuu', 'europa', 'guerra', 'mundial', 'internacional'],
        'Tecnología': ['tecnología', 'app', 'digital', 'ia', 'inteligencia artificial', 'startup'],
        'Salud': ['salud', 'hospital', 'médico', 'vacuna', 'pandemia'],
        'Sociedad': ['sociedad', 'educación', 'migración', 'violencia', 'crimen'],
        'TV y Espectáculos': ['actor', 'actriz', 'tv', 'famoso', 'farándula', 'espectáculo'],
        'Eléctrico': ['eléctric', 'transmisión', 'distribución', 'energía'],
        'Automotriz': ['auto', 'vehículo', 'volvo', 'automotriz', 'carro'],
        'Minería': ['minería', 'cobre', 'litio', 'mina'],
    }
    for category, words in keywords.items():
        if any(word in topic_lower for word in words):
            return category
    return 'Tendencias'

def analyze_with_qwen(prompt, mode='standard'):
    """Análisis con IA Qwen"""
    api_key = os.getenv('QWEN_API_KEY')
    if not api_key:
        return None, "QWEN_API_KEY no configurada"
    
    headers = {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}
    payload = {
        'model': 'qwen-plus',
        'input': {'messages': [{'role': 'user', 'content': prompt}]},
        'parameters': {'temperature': 0.1 if mode == 'briefing' else 0.7, 'max_tokens': 2000}
    }
    
    try:
        response = cr.post(
            'https://dashscope-intl.aliyuncs.com/api/v1/services/aigc/text-generation/generation',
            headers=headers,
            json=payload,
            timeout=60,
            impersonate="chrome"
        )
        if response.status_code == 200:
            text = response.json()['output']['choices'][0]['message']['content']
            match = re.search(r'\{.*\}', text, re.DOTALL)
            json_str = match.group(0) if match else text.replace('```json', '').replace('```', '').strip()
            return json.loads(json_str), None
        return None, f"Error HTTP {response.status_code}"
    except Exception as e:
        return None, f"Error: {str(e)}"

def generate_analysis(topic, topic2, category, region, mode, lens, news):
    news_text = "\n\nNoticias:\n" + "\n".join([f"- {n['titulo']}" for n in news[:5]]) if news else ""
    
    if mode == 'briefing':
        prompt = f"""Eres editor experto. BRIEFING sobre: TEMA: {topic} | CATEGORÍA: {category or 'General'} | REGIÓN: {region or 'Chile'}{news_text}
Responde SOLO JSON: {{"resumen_ejecutivo": "Párrafo claro", "preguntas_fuente": ["P1", "P2", "P3"], "datos_duros": ["D1", "D2"], "timeline_sugerido": "Cuándo publicar", "noticias_reales": {json.dumps(news if news else [], ensure_ascii=False)}}}"""
    elif mode == 'devil':
        prompt = f"""Editor crítico. ABOGADO DEL DIABLO: TEMA: {topic} | CATEGORÍA: {category or 'General'} | REGIÓN: {region or 'Chile'}{news_text}
Responde SOLO JSON: {{"cobertura_mainstream": "Lo que todos dicen", "angulo_ciego": "Lo que NADIE pregunta", "riesgos_sesgos": ["R1", "R2"], "pregunta_incomoda": "Pregunta incómoda", "noticias_reales": {json.dumps(news if news else [], ensure_ascii=False)}}}"""
    elif mode == 'compare' and topic2:
        prompt = f"""Editor estratégico. COMPARA: TEMA A: {topic} | TEMA B: {topic2} | CATEGORÍA: {category or 'General'} | REGIÓN: {region or 'Chile'}{news_text}
Responde SOLO JSON: {{"tema_a": "{topic}", "tema_b": "{topic2}", "mas_recorrido": "Cuál tiene más recorrido", "fuentes_comunes": ["F1", "F2"], "angulo_conector": "Ángulo conector", "recomendacion": "Cuál cubrir primero", "noticias_reales": {json.dumps(news if news else [], ensure_ascii=False)}}}"""
    else:
        lens_instruction = {"data": "\nENFOQUE: Estadísticas.", "controversy": "\nENFOQUE: Conflictos.", "human": "\nENFOQUE: Personas.", "economic": "\nENFOQUE: Finanzas."}.get(lens, "")
        prompt = f"""Analiza tendencia: TEMA: {topic} | CATEGORÍA: {category or 'General'} | REGIÓN: {region or 'Chile'}{news_text}{lens_instruction}
Responde SOLO JSON: {{"puntaje_relevancia": 7, "justificacion_puntaje": "Explicación", "hipotesis": "Hipótesis", "senales_clave": ["S1", "S2"], "angulos_periodisticos": ["A1", "A2"], "fuentes_sugeridas": ["F1", "F2"], "titulares_ejemplo": ["T1", "T2"], "noticias_reales": {json.dumps(news if news else [], ensure_ascii=False)}}}"""
    return prompt

@app.route('/')
def index(): return render_template('index.html')

@app.route('/api/categories', methods=['GET'])
def get_categories(): return jsonify(CATEGORIES)

@app.route('/api/trending', methods=['GET'])
def get_trending():
    category = request.args.get('category', 'all')
    limit = int(request.args.get('limit', 6))
    force_refresh = request.args.get('refresh') == 'true'
    articles, status = fetch_raw_articles(force_refresh=force_refresh)
    keywords_raw = SEARCH_KEYWORDS.get(category, 'chile')
    keywords = [kw.strip().lower() for kw in keywords_raw.split(' OR ')]
    
    trends = []
    seen = set()
    for a in articles:
        if category == 'all' or any(kw in a['title'].lower() for kw in keywords):
            if a['title'] not in seen:
                seen.add(a['title'])
                trends.append({'topic': a['title'], 'source': a['source'], 'region': 'Chile'})
        if len(trends) >= limit:
            break
    return jsonify({'trends': trends, 'source_status': status})

@app.route('/api/predictions', methods=['GET'])
def get_predictions_route():
    force_refresh = request.args.get('refresh') == 'true'
    articles, status = fetch_raw_articles(force_refresh=force_refresh)
    predictions = predict_trends(articles)
    return jsonify({'predictions': predictions, 'source_status': status})

@app.route('/api/status', methods=['GET'])
def get_status():
    _, status = get_cached_data()
    return jsonify({
        'mindicador': {'dolar': 950, 'uf': 36000, 'status': 'ok'},
        'weather': {'temperature': 22, 'windspeed': 10, 'status': 'ok'},
        'apis': {'scraping': 'ok', 'sources': status or {}},
        'timestamp': datetime.now(timezone.utc).isoformat()
    })

@app.route('/api/analyze', methods=['POST'])
def analyze():
    try:
        data = request.json
        topic = data.get('topic', '').strip()
        topic2 = data.get('topic2', '').strip()
        category = data.get('category')
        region = data.get('region')
        mode = data.get('mode', 'standard')
        lens = data.get('lens', '')
        
        if not topic:
            return jsonify({'error': 'Falta el tema'}), 400
        
        print(f"\n[ANALYZE] Topic: {topic}, Mode: {mode}, Lens: {lens}")
        
        # Buscar noticias relacionadas
        articles, _ = fetch_raw_articles(force_refresh=False)
        news = []
        topic_lower = topic.lower()
        for a in articles:
            if topic_lower in a['title'].lower():
                news.append({
                    'titulo': a['title'],
                    'fuente': a['source'],
                    'url': a['url'],
                    'fecha': a.get('first_seen', '')[:10] if a.get('first_seen') else ''
                })
                if len(news) >= 5:
                    break
        
        print(f"[ANALYZE] Noticias encontradas: {len(news)}")
        
        prompt = generate_analysis(topic, topic2, category, region, mode, lens, news)
        analysis, error = analyze_with_qwen(prompt, mode)
        
        if error or not analysis:
            print(f"[ANALYZE] Qwen falló: {error}. Fallback.")
            analysis = {
                'puntaje_relevancia': 5,
                'justificacion_puntaje': 'Análisis automático por fallo de IA',
                'hipotesis': f'Tendencia "{topic}" muestra relevancia.',
                'senales_clave': ['Aumento menciones', 'Nuevas regulaciones'],
                'angulos_periodisticos': ['Impacto económico', 'Perspectivas expertos'],
                'fuentes_sugeridas': ['Organismos', 'Expertos'],
                'titulares_ejemplo': [f"Análisis: {topic}"],
                'noticias_reales': news
            }
        else:
            print("[ANALYZE] Qwen OK!")
        
        if 'noticias_reales' not in analysis:
            analysis['noticias_reales'] = news
        
        score = analysis.get('puntaje_relevancia', 5)
        
        # Guardar en historial (SQLite)
        try:
            import sqlite3
            conn = sqlite3.connect(DB_PATH)
            conn.cursor().execute(
                'INSERT INTO trends (topic, topic2, category, region, mode, analysis, score) VALUES (?, ?, ?, ?, ?, ?, ?)',
                (topic, topic2 if mode == 'compare' else None, category, region, mode, json.dumps(analysis, ensure_ascii=False), score)
            )
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[DB] Error guardando historial: {str(e)}")
        
        return jsonify({
            'topic': topic,
            'topic2': topic2,
            'category': category,
            'region': region,
            'mode': mode,
            'lens': lens,
            'analysis': analysis,
            'score': score,
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
    except Exception as e:
        print(f"[ERROR] {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/history', methods=['GET'])
def get_history():
    limit = int(request.args.get('limit', 10))
    try:
        import sqlite3
        conn = sqlite3.connect(DB_PATH)
        rows = conn.cursor().execute(
            'SELECT id, topic, topic2, category, region, mode, analysis, score, created_at FROM trends ORDER BY created_at DESC LIMIT ?',
            (limit,)
        ).fetchall()
        conn.close()
        history = []
        for row in rows:
            try:
                analysis = json.loads(row[6]) if row[6] else {}
            except:
                analysis = {}
            history.append({
                'id': row[0],
                'topic': row[1],
                'topic2': row[2],
                'category': row[3],
                'region': row[4],
                'mode': row[5],
                'analysis': analysis,
                'score': row[7] or 0,
                'created_at': row[8]
            })
        return jsonify(history)
    except Exception as e:
        return jsonify([])

@app.route('/api/history/<int:analysis_id>', methods=['DELETE'])
def delete_history(analysis_id):
    try:
        import sqlite3
        conn = sqlite3.connect(DB_PATH)
        conn.cursor().execute('DELETE FROM trends WHERE id = ?', (analysis_id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
