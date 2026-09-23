from flask import Flask, render_template, jsonify, request
import os
from dotenv import load_dotenv
import requests
import json
import sqlite3
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
    
    # Tabla de tendencias
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

# ==================== CATEGORÍAS Y REGIONES ====================
CATEGORIES = [
    {'name': 'Eléctrico', 'icon': '⚡'},
    {'name': 'Automotriz', 'icon': ''},
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

@app.route('/api/trends', methods=['GET'])
def get_trends():
    """Obtener últimas tendencias"""
    category = request.args.get('category')
    region = request.args.get('region')
    limit = int(request.args.get('limit', 3))
    
    conn = get_db()
    cursor = conn.cursor()
    
    query = 'SELECT * FROM trends WHERE 1=1'
    params = []
    
    if category and category != 'all':
        query += ' AND category = ?'
        params.append(category)
    
    if region and region != 'all':
        query += ' AND region = ?'
        params.append(region)
    
    query += ' ORDER BY created_at DESC LIMIT ?'
    params.append(limit)
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    
    trends = []
    for row in rows:
        try:
            analysis = json.loads(row['analysis']) if row['analysis'] else {}
        except:
            analysis = {}
        
        trends.append({
            'id': row['id'],
            'topic': row['topic'],
            'category': row['category'],
            'region': row['region'],
            'analysis': analysis,
            'created_at': row['created_at']
        })
    
    return jsonify(trends)

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
            return jsonify({'error': 'API key no configurada'}), 500
        
        # Aquí iría la llamada real a Qwen (la agregamos en el Paso 3)
        # Por ahora, respuesta de prueba
        analysis = {
            'hipotesis': f'Análisis de "{topic}" en categoría {category or "general"} y región {region or "global"}. La tendencia muestra crecimiento en el sector.',
            'senales_clave': [
                f'Aumento de búsquedas sobre {topic}',
                'Nuevas regulaciones en el sector',
                'Cambios en el comportamiento del consumidor'
            ],
            'angulos_periodisticos': [
                f'Impacto económico de {topic}',
                'Perspectivas de los expertos',
                'Casos de éxito y fracaso'
            ],
            'fuentes_sugeridas': [
                'Expertos del sector',
                'Estadísticas oficiales',
                'Empresas del rubro'
            ]
        }
        
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
