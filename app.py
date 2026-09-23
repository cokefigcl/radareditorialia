from flask import Flask, render_template, jsonify, request
import os
from dotenv import load_dotenv
import json
import sqlite3
import requests
from datetime import datetime

load_dotenv()

app = Flask(__name__)

# ==================== BASE DE DATOS ====================
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
            category TEXT,
            region TEXT,
            analysis TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# ==================== CONFIGURACIÓN ====================
CATEGORIES = [
    {'name': 'Eléctrico', 'icon': '⚡'},
    {'name': 'Automotriz', 'icon': '🚗'},
    {'name': 'Belleza', 'icon': '💄'},
    {'name': 'Minería', 'icon': '️'},
    {'name': 'IA', 'icon': '🤖'},
    {'name': 'Tendencias', 'icon': '📈'},
    {'name': 'Tecnología', 'icon': '💻'},
    {'name': 'Economía', 'icon': '💰'}
]

REGIONS = ['Chile', 'Sudamérica', 'Norteamérica', 'América Latina', 'Europa', 'Asia', 'Global']

# ==================== RUTAS ====================
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
    region = request.args.get('region', 'Global')
    limit = int(request.args.get('limit', 5))
    
    trends_db = {
        'Chile': ["Reforma de pensiones y su impacto", "Precio del cobre alcanza máximos", "Sequía en la zona central", "Avance de la electromovilidad", "Nuevas regulaciones al comercio electrónico"],
        'Sudamérica': ["Acuerdos comerciales en el Mercosur", "Crisis hídrica en la cuenca del Plata", "Crecimiento del sector tecnológico", "Elecciones regionales", "Exportaciones de litio"],
        'Norteamérica': ["Tasas de interés de la Reserva Federal", "Avances en IA generativa", "Crisis en la cadena de suministro", "Elecciones y mercados", "Inversión en energías renovables"],
        'América Latina': ["Inflación y políticas monetarias", "Crecimiento de la banca digital", "Migración laboral", "Desafíos de la educación", "Turismo sostenible"],
        'Europa': ["Regulaciones de IA de la UE", "Crisis energética y transición verde", "Inflación en la eurozona", "Elecciones al Parlamento Europeo", "Innovación automotriz"],
        'Asia': ["Crecimiento económico de India", "Tensiones comerciales", "Avances en semiconductores", "Envejecimiento poblacional", "Inversión en infraestructura"],
        'Global': ["Cambio climático y cumbres internacionales", "IA y el futuro del trabajo", "Crisis de salud mental", "Economía digital", "Ciudades inteligentes"]
    }
    
    region_trends = trends_db.get(region, trends_db['Global'])
    return jsonify([{'topic': t, 'source': 'Tendencias ' + region, 'region': region} for t in region_trends[:limit]])

@app.route('/api/analyze', methods=['POST'])
def analyze():
    try:
        data = request.json
        topic = data.get('topic', '')
        category = data.get('category')
        region = data.get('region')
        
        if not topic:
            return jsonify({'error': 'Falta el tema'}), 400
        
        api_key = os.getenv('QWEN_API_KEY')
        if not api_key:
            return jsonify({'error': 'API key de Qwen no configurada en Railway'}), 500
        
        # Prompt profesional para análisis periodístico
        prompt = f"""Eres un editor jefe y analista de inteligencia informativa de un medio prestigioso. 
Analiza la siguiente tendencia periodística:

TEMA: {topic}
CATEGORÍA: {category or 'General'}
REGIÓN: {region or 'Global'}

Responde ÚNICAMENTE con un objeto JSON válido (sin markdown, sin texto extra) con esta estructura exacta:
{{
  "hipotesis": "Tu hipótesis principal de 2-3 oraciones sobre cómo evolucionará este tema.",
  "senales_clave": ["Señal 1", "Señal 2", "Señal 3"],
  "angulos_periodisticos": ["Ángulo 1", "Ángulo 2", "Ángulo 3"],
  "fuentes_sugeridas": ["Fuente 1", "Fuente 2", "Fuente 3"],
  "titulares_ejemplo": ["Ejemplo de titular 1", "Ejemplo de titular 2", "Ejemplo de titular 3"]
}}
Sé específico, práctico y con enfoque periodístico real."""

        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }
        
        # FORMATO CORRECTO PARA DASHSCOPE (API de Qwen)
        payload = {
            'model': 'qwen-plus',
            'input': {
                'messages': [
                    {'role': 'user', 'content': prompt}
                ]
            },
            'parameters': {
                'temperature': 0.7,
                'max_tokens': 1000
            }
        }
        
        # Llamada real a la API de Qwen (DashScope)
        response = requests.post(
            'https://dashscope-intl.aliyuncs.com/api/v1/services/aigc/text-generation/generation',
            headers=headers,
            json=payload,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            
            # DashScope devuelve la respuesta en output.choices[0].message.content
            analysis_text = result['output']['choices'][0]['message']['content']
            
            # Limpiar el texto por si la IA agrega ```json
            analysis_text = analysis_text.replace('```json', '').replace('```', '').strip()
            
            try:
                analysis = json.loads(analysis_text)
            except json.JSONDecodeError:
                # Fallback si el JSON falla
                analysis = {
                    'hipotesis': analysis_text,
                    'senales_clave': ['Verificar fuentes', 'Monitorear redes'],
                    'angulos_periodisticos': ['Impacto local', 'Perspectiva global'],
                    'fuentes_sugeridas': ['Expertos', 'Datos oficiales'],
                    'titulares_ejemplo': [f"Análisis en profundidad: {topic}"]
                }
        else:
            return jsonify({'error': f'Error en API de Qwen: {response.status_code} - {response.text}'}), 500
        
        # Guardar en base de datos
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO trends (topic, category, region, analysis) VALUES (?, ?, ?, ?)',
            (topic, category, region, json.dumps(analysis))
        )
        conn.commit()
        conn.close()
        
        return jsonify({
            'topic': topic,
            'category': category,
            'region': region,
            'analysis': analysis,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
