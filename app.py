from flask import Flask, render_template, jsonify, request
from dotenv import load_dotenv
import os
import json
import sqlite3
from datetime import datetime
from ai_analyzer import analyze_trend_with_qwen

load_dotenv()

app = Flask(__name__)

# Usar SQLite (archivo local)
DB_PATH = os.path.join(os.path.dirname(__file__), 'trends.db')

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Inicializar base de datos SQLite"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trends (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT NOT NULL,
            analysis TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

def save_trend(topic, analysis):
    """Guardar tendencia"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        'INSERT INTO trends (topic, analysis) VALUES (?, ?)',
        (topic, json.dumps(analysis))
    )
    
    conn.commit()
    conn.close()

def get_trends(limit=20):
    """Obtener tendencias recientes"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        'SELECT topic, analysis, created_at FROM trends ORDER BY created_at DESC LIMIT ?',
        (limit,)
    )
    
    rows = cursor.fetchall()
    conn.close()
    
    return [
        {
            'topic': row['topic'],
            'analysis': json.loads(row['analysis']) if row['analysis'] else {},
            'created_at': row['created_at']
        }
        for row in rows
    ]

# Inicializar DB al iniciar
init_db()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/analyze', methods=['POST'])
def analyze():
    """Endpoint para analizar una tendencia con IA"""
    data = request.json
    trend_topic = data.get('topic', '')
    
    if not trend_topic:
        return jsonify({'error': 'Topic is required'}), 400
    
    # Verificar que la API key esté configurada
    api_key = os.getenv('QWEN_API_KEY')
    if not api_key:
        return jsonify({'error': 'API key no configurada. Agrega QWEN_API_KEY en Variables de Railway'}), 500
    
    # Analizar con Qwen
    analysis = analyze_trend_with_qwen(trend_topic)
    
    # Guardar en base de datos
    save_trend(trend_topic, analysis)
    
    return jsonify({
        'topic': trend_topic,
        'analysis': analysis,
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/trends', methods=['GET'])
def trends():
    """Obtener tendencias analizadas"""
    return jsonify(get_trends())

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
