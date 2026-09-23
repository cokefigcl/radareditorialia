from flask import Flask, render_template, jsonify, request
import os
from dotenv import load_dotenv
import json
import sqlite3
import requests
import re
from datetime import datetime, timedelta

load_dotenv()

app = Flask(__name__)

# Fallback temporal si Railway no carga NEWSAPI_KEY
if not os.getenv('NEWSAPI_KEY'):
    os.environ['NEWSAPI_KEY'] = "89f88b93d0634e1ab94c3a5fd018bc1a"
    print("⚠️ Usando NEWSAPI_KEY hardcodeada")

DB_PATH = os.path.join(os.path.dirname(__file__), 'trends.db')

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
            analysis_type TEXT,
            lens TEXT,
            analysis TEXT,
            score INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

init_db()

CATEGORIES = [
    {'name': 'Eléctrico', 'icon': '⚡'},
    {'name': 'Automotriz', 'icon': '🚗'},
    {'name': 'Belleza', 'icon': '💄'},
    {'name': 'Minería', 'icon': '⛏️'},
    {'name': 'IA', 'icon': '🤖'},
    {'name': 'Tendencias', 'icon': '📈'},
    {'name': 'Tecnología', 'icon': '💻'},
    {'name': 'Economía', 'icon': '💰'}
]

REGIONS = ['Chile']

TRENDS_BY_CATEGORY = {
    'Eléctrico': ["Subsidios a la electromovilidad en Chile 2026", "Expansión de la red de carga", "Nuevas normativas de eficiencia energética", "Energía solar en hogares", "Baterías de litio: Chile como actor global"],
    'Automotriz': ["Caída en ventas de autos nuevos", "Auge de autos usados importados", "Nuevas regulaciones de emisiones", "Competencia de marcas chinas", "Seguros automotrices: alzas"],
    'Belleza': ["Boom del skincare coreano", "Cosmética natural en Chile", "Influencers de belleza y ventas", "Tendencias de maquillaje 2026", "Tratamientos capilares en auge"],
    'Minería': ["Precio del cobre en máximos", "Litio: estrategia nacional", "Minería verde y descarbonización", "Automatización en faenas", "Conflictos socioambientales"],
    'IA': ["Regulación de IA en Chile", "IA generativa y mundo laboral", "Startups chilenas de IA", "Deepfakes y desinformación", "IA en la educación"],
    'Tendencias': ["Deuda de jóvenes y pagos digitales", "Crisis habitacional en Santiago", "Migración y mercado laboral", "Turismo interno post-pandemia", "Foodtech en Chile"],
    'Tecnología': ["Expansión del 5G en regiones", "Ciberseguridad: ataques a empresas", "Fintech y bancarización digital", "Gaming y esports en crecimiento", "Transformación digital pymes"],
    'Economía': ["Tasa de interés del Banco Central", "Inflación y canasta básica", "Reforma tributaria: impactos", "Desempleo y mercado laboral", "Dólar y economía local"]
}

def get_trends_for_category(category):
    if category and category != 'all' and category in TRENDS_BY_CATEGORY:
        return TRENDS_BY_CATEGORY[category]
    all_trends = [t for trends in TRENDS_BY_CATEGORY.values() for t in trends]
    import random
    random.shuffle(all_trends)
    return all_trends[:5]

def search_news(topic, max_results=5):
    print(f"[DEBUG] Buscando noticias para: {topic}")
    newsapi_key = os.getenv('NEWSAPI_KEY')
    
    if newsapi_key and len(newsapi_key) > 10:
        try:
            url = 'https://newsapi.org/v2/everything'
            params = {
                'q': topic,
                'from': (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d'),
                'to': datetime.now().strftime('%Y-%m-%d'),
                'sortBy': 'publishedAt',
                'language': 'es',
                'pageSize': max_results * 3,
                'apiKey': newsapi_key
            }
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                news_items = []
                seen = set()
                for article in data.get('articles', []):
                    title = article.get('title', '').strip()
                    if title and title not in seen and len(title) > 10:
                        seen.add(title)
                        news_items.append({
                            'titulo': title,
                            'fuente': article.get('source', {}).get('name', ''),
                            'url': article.get('url', ''),
                            'fecha': article.get('publishedAt', '')[:10]
                        })
                    if len(news_items) >= max_results:
                        break
                if news_items:
                    return news_items
        except Exception as e:
            print(f"[DEBUG] NewsAPI error: {str(e)}")
    
    # Fallback GDELT
    try:
        url = 'https://api.gdeltproject.org/api/v2/doc/doc'
        params = {
            'query': topic,
            'mode': 'artlist',
            'format': 'json',
            'startdatetime': (datetime.now() - timedelta(days=14)).strftime('%Y%m%d%H%M%S'),
            'enddatetime': datetime.now().strftime('%Y%m%d%H%M%S'),
            'maxrecords': max_results * 5,
            'sourcelang': 'spa'
        }
        response = requests.get(url, params=params, timeout=15)
        if response.status_code == 200:
            data = response.json()
            news_items = []
            seen = set()
            for article in data.get('articles', []):
                title = article.get('title', '').strip()
                if title and title not in seen and len(title) > 5:
                    seen.add(title)
                    news_items.append({
                        'titulo': title,
                        'fuente': article.get('domain', ''),
                        'url': article.get('url', ''),
                        'fecha': article.get('seendate', '')[:10]
                    })
                if len(news_items) >= max_results:
                    break
            return news_items
    except Exception as e:
        print(f"[DEBUG] GDELT error: {str(e)}")
    
    return []

def build_prompt(analysis_type, lens, topic, topic2, category, region, news):
    """Construye el prompt según el tipo de análisis y lente"""
    
    news_text = "\n\nNoticias encontradas:\n" + "\n".join([f"- {n['titulo']}" for n in news[:5]]) if news else ""
    
    # Lente
    lens_instructions = {
        'datos': "Enfócate en datos duros, estadísticas, cifras verificables y fuentes oficiales.",
        'polemico': "Busca controversias, conflictos, debates y posturas enfrentadas.",
        'humano': "Prioriza el impacto en las personas, historias de vida y testimonios."
    }
    lens_text = lens_instructions.get(lens, "")
    
    if analysis_type == 'briefing':
        prompt = f"""Eres un editor jefe. Genera un BRIEFING PERIODÍSTICO de 1 minuto sobre este tema.

{lens_text}

TEMA: {topic}
CATEGORÍA: {category or 'General'}
REGIÓN: {region or 'Chile'}{news_text}

Responde SOLO con JSON válido:
{{
  "resumen_ejecutivo": "1 párrafo claro: qué está pasando y por qué importa ahora",
  "preguntas_clave": ["Pregunta 1 que debes hacer a tu fuente", "Pregunta 2", "Pregunta 3"],
  "datos_a_verificar": ["Dato 1 que debes confirmar antes de publicar", "Dato 2"],
  "fuentes_prioritarias": ["Fuente 1", "Fuente 2", "Fuente 3"],
  "titulares_sugeridos": ["Titular 1", "Titular 2"],
  "noticias_reales": {json.dumps(news if news else [], ensure_ascii=False)}
}}"""
    
    elif analysis_type == 'devil':
        prompt = f"""Eres el "Abogado del Diablo" periodístico. Tu trabajo es encontrar el ÁNGULO CIEGO que nadie está cubriendo.

{lens_text}

TEMA: {topic}
CATEGORÍA: {category or 'General'}
REGIÓN: {region or 'Chile'}{news_text}

Responde SOLO con JSON válido:
{{
  "lo_que_todos_dicen": "Resumen de lo que ya están cubriendo otros medios",
  "angulo_ciego": "El ángulo que NADIE está preguntando pero debería",
  "pregunta_incomoda": "La pregunta incómoda que nadie se atreve a hacer",
  "contradiccion": "Una contradicción o hipocresía en la narrativa actual",
  "fuentes_alternativas": ["Fuente no convencional 1", "Fuente no convencional 2"],
  "titular_contraintuitivo": "Un titular que vaya contra la narrativa dominante",
  "noticias_reales": {json.dumps(news if news else [], ensure_ascii=False)}
}}"""
    
    elif analysis_type == 'compare' and topic2:
        prompt = f"""Eres un analista editorial. Compara estos DOS temas y determina cuál tiene más recorrido periodístico.

{lens_text}

TEMA A: {topic}
TEMA B: {topic2}
CATEGORÍA: {category or 'General'}
REGIÓN: {region or 'Chile'}{news_text}

Responde SOLO con JSON válido:
{{
  "tema_a": "{topic}",
  "tema_b": "{topic2}",
  "ganador": "Tema A o Tema B (cuál tiene más recorrido ahora)",
  "razon_ganador": "Por qué ese tema tiene más fuerza periodística ahora",
  "puntos_en_comun": ["Punto en común 1", "Punto en común 2"],
  "angulo_conector": "Un ángulo que conecte ambos temas en una sola nota",
  "fuentes_compartidas": ["Fuente que sirve para ambos 1", "Fuente 2"],
  "recomendacion": "Qué tema cubrir primero y por qué",
  "noticias_reales": {json.dumps(news if news else [], ensure_ascii=False)}
}}"""
    
    else:
        # Análisis estándar
        prompt = f"""Analiza esta tendencia periodística.

{lens_text}

TEMA: {topic}
CATEGORÍA: {category or 'General'}
REGIÓN: {region or 'Chile'}{news_text}

Responde SOLO con JSON válido:
{{
  "puntaje_relevancia": 7,
  "justificacion_puntaje": "Explicación breve",
  "hipotesis": "Hipótesis de 2-3 oraciones",
  "senales_clave": ["Señal 1", "Señal 2"],
  "angulos_periodisticos": ["Ángulo 1", "Ángulo 2"],
  "fuentes_sugeridas": ["Fuente 1", "Fuente 2"],
  "titulares_ejemplo": ["Titular 1", "Titular 2"],
  "noticias_reales": {json.dumps(news if news else [], ensure_ascii=False)}
}}"""
    
    return prompt

def analyze_with_qwen(prompt):
    api_key = os.getenv('QWEN_API_KEY')
    if not api_key:
        return None, "QWEN_API_KEY no configurada"
    
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    
    payload = {
        'model': 'qwen-plus',
        'input': {'messages': [{'role': 'user', 'content': prompt}]},
        'parameters': {'temperature': 0.1, 'max_tokens': 1500}
    }
    
    try:
        response = requests.post(
            'https://dashscope-intl.aliyuncs.com/api/v1/services/aigc/text-generation/generation',
            headers=headers,
            json=payload,
            timeout=60
        )
        
        print(f"[DEBUG] Qwen status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            
            analysis_text = None
            try:
                analysis_text = result['output']['choices'][0]['message']['content']
            except:
                try:
                    analysis_text = result['output']['text']
                except:
                    try:
                        analysis_text = result['output']['result']
                    except:
                        pass
            
            if not analysis_text or not isinstance(analysis_text, str):
                return None, f"Respuesta vacía de Qwen"
            
            # Extraer JSON con regex
            match = re.search(r'\{.*\}', analysis_text, re.DOTALL)
            if match:
                json_str = match.group(0)
            else:
                json_str = analysis_text.replace('```json', '').replace('```', '').strip()
            
            try:
                analysis = json.loads(json_str)
                return analysis, None
            except json.JSONDecodeError as e:
                return None, f"Error parseando JSON: {str(e)}"
        else:
            return None, f"Error HTTP {response.status_code}"
            
    except requests.exceptions.Timeout:
        return None, "Timeout de Qwen API"
    except Exception as e:
        return None, f"Error: {str(e)}"

def generate_fallback(analysis_type, topic, topic2, lens, news):
    """Fallback cuando Qwen falla"""
    if analysis_type == 'briefing':
        return {
            'resumen_ejecutivo': f'El tema "{topic}" requiere investigación adicional. Se recomienda consultar fuentes oficiales y expertos del sector.',
            'preguntas_clave': ['¿Qué está pasando exactamente?', '¿Quiénes son los afectados?', '¿Cuál es el contexto histórico?'],
            'datos_a_verificar': ['Cifras oficiales', 'Declaraciones de autoridades'],
            'fuentes_prioritarias': ['Organismos oficiales', 'Expertos del sector'],
            'titulares_sugeridos': [f"Análisis: {topic}", f"Las claves de {topic}"],
            'noticias_reales': news if news else []
        }
    elif analysis_type == 'devil':
        return {
            'lo_que_todos_dicen': f'La narrativa dominante sobre "{topic}" se centra en aspectos superficiales.',
            'angulo_ciego': 'Se necesita investigación profunda para encontrar el ángulo no cubierto.',
            'pregunta_incomoda': '¿Qué intereses hay detrás de la narrativa actual?',
            'contradiccion': 'Existen contradicciones entre lo que se dice y lo que muestran los datos.',
            'fuentes_alternativas': ['Fuentes independientes', 'Testimonios directos'],
            'titular_contraintuitivo': f"Lo que nadie te cuenta sobre {topic}",
            'noticias_reales': news if news else []
        }
    elif analysis_type == 'compare':
        return {
            'tema_a': topic,
            'tema_b': topic2 or 'N/A',
            'ganador': 'Requiere análisis manual',
            'razon_ganador': 'Ambos temas requieren investigación periodística profunda.',
            'puntos_en_comun': ['Ambos son relevantes para la audiencia', 'Requieren fuentes verificadas'],
            'angulo_conector': 'Se puede crear una nota comparativa que analice ambos fenómenos.',
            'fuentes_compartidas': ['Expertos en el tema', 'Datos oficiales'],
            'recomendacion': 'Evaluar cuál tiene más actualidad y fuentes disponibles.',
            'noticias_reales': news if news else []
        }
    else:
        return {
            'puntaje_relevancia': 5,
            'justificacion_puntaje': 'Análisis automático (IA no disponible)',
            'hipotesis': f'El tema "{topic}" muestra relevancia. Se recomienda monitorear.',
            'senales_clave': ['Aumento de menciones', 'Nuevas regulaciones'],
            'angulos_periodisticos': ['Impacto económico', 'Perspectivas de expertos'],
            'fuentes_sugeridas': ['Organismos oficiales', 'Expertos'],
            'titulares_ejemplo': [f"Análisis: {topic}"],
            'noticias_reales': news if news else []
        }

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/categories', methods=['GET'])
def get_categories():
    return jsonify(CATEGORIES)

@app.route('/api/regions', methods=['GET'])
def get_regions():
    return jsonify(REGIONS)

@app.route('/api/trending', methods=['GET'])
def get_trending():
    category = request.args.get('category', 'all')
    limit = int(request.args.get('limit', 5))
    return jsonify([{'topic': t, 'source': 'Tendencias ' + (category if category != 'all' else 'Chile'), 'region': 'Chile'} for t in get_trends_for_category(category)[:limit]])

@app.route('/api/debug', methods=['GET'])
def debug():
    return jsonify({
        'qwen_configured': bool(os.getenv('QWEN_API_KEY')),
        'newsapi_configured': bool(os.getenv('NEWSAPI_KEY')),
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/history', methods=['GET'])
def get_history():
    limit = int(request.args.get('limit', 20))
    conn = get_db()
    rows = conn.cursor().execute('SELECT id, topic, topic2, category, region, analysis_type, lens, analysis, score, created_at FROM trends ORDER BY created_at DESC LIMIT ?', (limit,)).fetchall()
    conn.close()
    history = []
    for row in rows:
        try:
            analysis = json.loads(row['analysis']) if row['analysis'] else {}
        except:
            analysis = {}
        history.append({
            'id': row['id'], 'topic': row['topic'], 'topic2': row['topic2'],
            'category': row['category'], 'region': row['region'],
            'analysis_type': row['analysis_type'], 'lens': row['lens'],
            'analysis': analysis, 'score': row['score'] or 0, 'created_at': row['created_at']
        })
    return jsonify(history)

@app.route('/api/history/<int:analysis_id>', methods=['DELETE'])
def delete_history(analysis_id):
    conn = get_db()
    conn.cursor().execute('DELETE FROM trends WHERE id = ?', (analysis_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/analyze', methods=['POST'])
def analyze():
    try:
        data = request.json
        topic = data.get('topic', '').strip()
        topic2 = data.get('topic2', '').strip()
        category = data.get('category')
        region = data.get('region')
        analysis_type = data.get('analysis_type', 'standard')
        lens = data.get('lens', 'standard')
        
        if not topic:
            return jsonify({'error': 'Falta el tema'}), 400
        
        if analysis_type == 'compare' and not topic2:
            return jsonify({'error': 'Para comparar necesitas dos temas'}), 400
        
        print(f"\n{'='*60}")
        print(f"[ANALYZE] Type: {analysis_type}, Lens: {lens}")
        print(f"[ANALYZE] Topic: {topic}, Topic2: {topic2}")
        
        # Buscar noticias
        news = search_news(topic, max_results=5)
        if analysis_type == 'compare' and topic2:
            news2 = search_news(topic2, max_results=3)
            news = news + news2
        
        print(f"[ANALYZE] Noticias: {len(news)}")
        
        # Construir prompt
        prompt = build_prompt(analysis_type, lens, topic, topic2, category, region, news)
        
        # Analizar con Qwen
        analysis, error = analyze_with_qwen(prompt)
        
        used_fallback = False
        if error or not analysis:
            print(f"[ANALYZE] Qwen falló: {error}")
            analysis = generate_fallback(analysis_type, topic, topic2, lens, news)
            used_fallback = True
        else:
            print(f"[ANALYZE] Qwen OK!")
        
        if 'noticias_reales' not in analysis:
            analysis['noticias_reales'] = news if news else []
        
        score = analysis.get('puntaje_relevancia', 5)
        
        # Guardar
        conn = get_db()
        conn.cursor().execute('''INSERT INTO trends (topic, topic2, category, region, analysis_type, lens, analysis, score) 
                                  VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                              (topic, topic2 if analysis_type == 'compare' else None, category, region, 
                               analysis_type, lens, json.dumps(analysis, ensure_ascii=False), score))
        conn.commit()
        conn.close()
        
        print(f"[ANALYZE] Completado. Fallback: {used_fallback}")
        print(f"{'='*60}\n")
        
        return jsonify({
            'topic': topic, 'topic2': topic2, 'category': category, 'region': region,
            'analysis_type': analysis_type, 'lens': lens,
            'analysis': analysis, 'score': score, 'used_fallback': used_fallback,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        print(f"[ERROR] {str(e)}")
        topic = request.json.get('topic', 'Tema') if request.json else 'Tema'
        return jsonify({'topic': topic, 'analysis': generate_fallback('standard', topic, None, 'standard', []), 'score': 5, 'warning': f'Error: {str(e)}'}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
