from flask import Flask, render_template, jsonify, request
import os
from dotenv import load_dotenv
import json
import sqlite3
from datetime import datetime

# 1. Cargar variables de entorno
load_dotenv()

# 2. DEFINIR LA APP (ESTA LÍNEA ES LA QUE BUSCA GUNICORN)
app = Flask(__name__)

# 3. Base de datos simple
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

# 4. Datos de filtros
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

REGIONS = ['Chile', 'Sudamérica', 'Norteamérica', 'América Latina', 'Europa', 'Asia', 'Global']

# 5. Rutas
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
        'Chile': ["Reforma de pensiones", "Precio del cobre", "Sequía zona central", "Electromovilidad", "Comercio electrónico"],
        'Global': ["Inteligencia Artificial", "Cambio climático", "Salud mental", "Economía digital", "Movilidad sostenible"]
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
        
        analysis = {
            'hipotesis': f'La tendencia "{topic}" muestra crecimiento en {region or "el ámbito global"}.',
            'senales_clave': ['Aumento de menciones en medios', 'Nuevas regulaciones', 'Cambio en el consumo'],
            'angulos_periodisticos': ['Impacto económico', 'Perspectivas de expertos', 'Casos de éxito'],
            'fuentes_sugeridas': ['Organismos oficiales', 'Académicos', 'Cámaras de comercio']
        }
        
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('INSERT INTO trends (topic, category, region, analysis) VALUES (?, ?, ?, ?)',
                       (topic, category, region, json.dumps(analysis)))
        conn.commit()
        conn.close()
        
        return jsonify({'topic': topic, 'category': category, 'region': region, 'analysis': analysis})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# 6. INICIO DEL SERVIDOR
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
