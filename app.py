from flask import Flask, render_template, jsonify, request
import os
from dotenv import load_dotenv
import json
import sqlite3
import requests
import re
from datetime import datetime, timedelta
from collections import Counter
from bs4 import BeautifulSoup

load_dotenv()

app = Flask(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), 'trends.db')
CACHE_FILE = os.path.join(os.path.dirname(__file__), 'news_cache.json')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trends (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT NOT NULL,
            topic2 TEXT,
            category TEXT,
            region TEXT,
            mode TEXT,
            analysis TEXT,
            score INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

init_db()

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

# Scraping directo de páginas web (más confiable que RSS)
SCRAPE_URLS = [
    {'url': 'https://www.biobiochile.cl/', 'name': 'BioBioChile', 'selector': 'h2, h3'},
    {'url': 'https://www.latercera.com/', 'name': 'La Tercera', 'selector': 'h2, h3'},
    {'url': 'https://www.cooperativa.cl/', 'name': 'Cooperativa', 'selector': 'h2, h3'},
    {'url': 'https://www.df.cl/', 'name': 'Diario Financiero', 'selector': 'h2, h3'},
]

# Reddit para tendencias tempranas
REDDIT_SUBREDDITS = ['chile', 'ChileanPolitics']

def get_cached_news(max_age_minutes=60):
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                cache = json.load(f)
                timestamp = datetime.fromisoformat(cache['timestamp'])
                if datetime.now() - timestamp < timedelta(minutes=max_age_minutes):
                    print(f"[CACHE] ✅ Usando caché ({len(cache['articles'])} artículos)")
                    return cache['articles']
        except Exception as e:
            print(f"[CACHE] Error: {str(e)}")
    return None

def save_to_cache(articles):
    if not articles: return
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump({'articles': articles, 'timestamp': datetime.now().isoformat()}, f, ensure_ascii=False)
        print(f"[CACHE] 💾 Guardados {len(articles)} artículos")
    except Exception as e:
        print(f"[CACHE] Error guardando: {str(e)}")

def scrape_website(url_config):
    """Scrapea titulares directamente de la página web"""
    articles = []
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url_config['url'], headers=headers, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            headlines = soup.select(url_config['selector'])
            for headline in headlines[:20]:
                title = headline.get_text().strip()
                if title and len(title) > 15 and len(title) < 200:
                    articles.append({
                        'title': title,
                        'source': url_config['name'],
                        'link': url_config['url'],
                        'published': datetime.now().isoformat()
                    })
            print(f"[SCRAPE] ✅ {url_config['name']}: {len(articles)} titulares")
    except Exception as e:
        print(f"[SCRAPE] ❌ {url_config['name']}: {str(e)}")
    return articles

def fetch_reddit_trends():
    """Obtiene tendencias de Reddit Chile"""
    articles = []
    headers = {'User-Agent': 'RadarEditorial/1.0'}
    
    for subreddit in REDDIT_SUBREDDITS:
        try:
            url = f'https://www.reddit.com/r/{subreddit}/hot.json?limit=20'
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                for post in data['data']['children']:
                    title = post['data']['title']
                    if title and len(title) > 10:
                        articles.append({
                            'title': title,
                            'source': f'Reddit r/{subreddit}',
                            'link': f"https://reddit.com{post['data']['permalink']}",
                            'published': datetime.fromtimestamp(post['data']['created_utc']).isoformat()
                        })
                print(f"[REDDIT] ✅ r/{subreddit}: {len(articles)} posts")
        except Exception as e:
            print(f"[REDDIT] ❌ r/{subreddit}: {str(e)}")
    
    return articles

def fetch_raw_articles(force_refresh=False):
    """Sistema híbrido: Scraping + Reddit"""
    if not force_refresh:
        cached = get_cached_news(max_age_minutes=60)
        if cached:
            print("[FETCH] Usando caché (1 hora)")
            return cached
    
    all_articles = []
    
    # 1. Scraping directo de medios chilenos
    print(f"[FETCH] Scraping {len(SCRAPE_URLS)} sitios web...")
    for url_config in SCRAPE_URLS:
        articles = scrape_website(url_config)
        all_articles.extend(articles)
    
    # 2. Reddit para tendencias tempranas
    print("[FETCH] Consultando Reddit...")
    reddit_articles = fetch_reddit_trends()
    all_articles.extend(reddit_articles)
    
    # Eliminar duplicados
    seen = set()
    unique_articles = []
    for article in all_articles:
        if article['title'] not in seen:
            seen.add(article['title'])
            unique_articles.append(article)
    
    print(f"[FETCH] Total artículos únicos: {len(unique_articles)}")
    if unique_articles:
        save_to_cache(unique_articles)
    
    return unique_articles

def predict_trends(articles):
    """Algoritmo de predicción por frecuencia + novedad"""
    if not articles:
        return []
    
    # Palabras a ignorar
    stop_words = {'el', 'la', 'los', 'las', 'un', 'una', 'de', 'del', 'al', 'y', 'o', 'que', 'por', 'para', 'con', 'en', 'a', 'se', 'su', 'chile', 'santiago', 'hoy', 'más', 'the', 'and', 'for', 'that', 'this', 'es', 'son', 'como', 'pero', 'también'}
    
    # Contar frecuencia de palabras
    word_counts = Counter()
    word_sources = {}
    word_examples = {}
    word_recency = {}
    
    for article in articles:
        title_lower = article['title'].lower()
        words = [w for w in re.findall(r'\b\w{4,}\b', title_lower) if w not in stop_words]
        
        for word in words:
            word_counts[word] += 1
            
            if word not in word_sources:
                word_sources[word] = set()
                word_examples[word] = []
                word_recency[word] = []
            
            word_sources[word].add(article['source'])
            if len(word_examples[word]) < 3:
                word_examples[word].append(article['title'])
            
            # Calcular recencia (artículos más recientes = más relevantes)
            try:
                pub_time = datetime.fromisoformat(article['published'])
                hours_ago = (datetime.now() - pub_time).total_seconds() / 3600
                word_recency[word].append(hours_ago)
            except:
                pass
    
    # Calcular score para cada palabra
    predictions = []
    for word, count in word_counts.most_common(20):
        sources = word_sources[word]
        num_sources = len(sources)
        
        # Solo considerar palabras que aparecen en al menos 2 fuentes o 3+ veces
        if num_sources >= 2 or count >= 3:
            # Score base por frecuencia
            frequency_score = min(count * 10, 50)
            
            # Bonus por múltiples fuentes
            source_bonus = min(num_sources * 15, 30)
            
            # Bonus por recencia (promedio de horas)
            if word_recency[word]:
                avg_hours = sum(word_recency[word]) / len(word_recency[word])
                recency_bonus = max(0, 20 - avg_hours)  # Más reciente = más bonus
            else:
                recency_bonus = 10
            
            total_score = min(int(frequency_score + source_bonus + recency_bonus), 100)
            
            # Determinar nivel de alerta
            alert_level = None
            if total_score >= 85:
                alert_level = 'critical'
            elif total_score >= 70:
                alert_level = 'high'
            
            predictions.append({
                'topic': word_examples[word][0],
                'score': total_score,
                'category': guess_category(word_examples[word][0]),
                'news_count': num_sources,
                'news': [{'titulo': t, 'fuente': 'Múltiples fuentes', 'url': '', 'fecha': datetime.now().strftime('%Y-%m-%d')} for t in word_examples[word][:3]],
                'alert_level': alert_level,
                'source': 'Predicción por Frecuencia',
                'is_realtime': True,
                'timestamp': datetime.now().isoformat()
            })
    
    # Ordenar por score y devolver top 8
    return sorted(predictions, key=lambda x: x['score'], reverse=True)[:8]

def guess_category(topic):
    topic_lower = topic.lower()
    keywords = {
        'Deportes': ['fútbol', 'deporte', 'selección', 'campeonato'],
        'Economía': ['dólar', 'inflación', 'economía', 'peso', 'cobre', 'financial', 'market'],
        'Chile': ['gobierno', 'presidente', 'congreso', 'ley', 'chile'],
        'Internacional': ['eeuu', 'europa', 'guerra', 'mundial', 'world', 'global'],
        'Tecnología': ['tecnología', 'app', 'digital', 'ia', 'inteligencia', 'tech', 'startup'],
        'Salud': ['salud', 'hospital', 'médico', 'vacuna'],
        'Sociedad': ['sociedad', 'educación', 'migración'],
        'TV y Espectáculos': ['actor', 'actriz', 'tv', 'famoso', 'farándula'],
        'Eléctrico': ['eléctric', 'transmisión', 'distribución'],
    }
    for category, words in keywords.items():
        if any(word in topic_lower for word in words):
            return category
    return 'Tendencias'

def get_trends_for_category(category, limit=6, force_refresh=False):
    articles = fetch_raw_articles(force_refresh=force_refresh)
    keywords_raw = SEARCH_KEYWORDS.get(category, 'chile')
    keywords = [kw.strip().lower() for kw in keywords_raw.split(' OR ')]
    
    trends = []
    seen = set()
    for article in articles:
        if category == 'all' or any(kw in article['title'].lower() for kw in keywords):
            if article['title'] not in seen:
                seen.add(article['title'])
                trends.append({'topic': article['title'], 'source': article['source'], 'region': 'Chile'})
        if len(trends) >= limit:
            break
    return trends

def get_status_panel():
    return {
        'mindicador': {'dolar': 950, 'uf': 36000, 'status': 'ok'},
        'weather': {'temperature': 22, 'windspeed': 10, 'status': 'ok'},
        'apis': {'scraping': 'ok', 'reddit': 'ok'},
        'timestamp': datetime.now().isoformat()
    }

def search_news(topic, max_results=5):
    articles = fetch_raw_articles(force_refresh=False)
    news_items = []
    seen = set()
    topic_lower = topic.lower()
    for article in articles:
        if topic_lower in article['title'].lower():
            if article['title'] not in seen:
                seen.add(article['title'])
                news_items.append({'titulo': article['title'], 'fuente': article['source'], 'url': article['link'], 'fecha': article['published'][:10] if article['published'] else ''})
            if len(news_items) >= max_results:
                break
    return news_items

@app.route('/')
def index(): return render_template('index.html')

@app.route('/api/categories', methods=['GET'])
def get_categories(): return jsonify(CATEGORIES)

@app.route('/api/trending', methods=['GET'])
def get_trending():
    category = request.args.get('category', 'all')
    limit = int(request.args.get('limit', 6))
    force_refresh = request.args.get('refresh') == 'true'
    return jsonify(get_trends_for_category(category, limit, force_refresh=force_refresh))

@app.route('/api/predictions', methods=['GET'])
def get_predictions_route():
    force_refresh = request.args.get('refresh') == 'true'
    articles = fetch_raw_articles(force_refresh=force_refresh)
    predictions = predict_trends(articles)
    return jsonify(predictions)

@app.route('/api/status', methods=['GET'])
def get_status(): return jsonify(get_status_panel())

@app.route('/api/history', methods=['GET'])
def get_history():
    limit = int(request.args.get('limit', 10))
    conn = get_db()
    rows = conn.cursor().execute('SELECT id, topic, topic2, category, region, mode, analysis, score, created_at FROM trends ORDER BY created_at DESC LIMIT ?', (limit,)).fetchall()
    conn.close()
    history = []
    for row in rows:
        try: analysis = json.loads(row['analysis']) if row['analysis'] else {}
        except: analysis = {}
        history.append({'id': row['id'], 'topic': row['topic'], 'topic2': row['topic2'], 'category': row['category'], 'region': row['region'], 'mode': row['mode'], 'analysis': analysis, 'score': row['score'] or 0, 'created_at': row['created_at']})
    return jsonify(history)

@app.route('/api/history/<int:analysis_id>', methods=['DELETE'])
def delete_history(analysis_id):
    conn = get_db()
    conn.cursor().execute('DELETE FROM trends WHERE id = ?', (analysis_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
