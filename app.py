from flask import Flask, render_template, jsonify, request
from dotenv import load_dotenv
import os
import json
import psycopg2
from datetime import datetime
from ai_analyzer import analyze_trend_with_qwen

load_dotenv()

app = Flask(__name__)

# Configurar base de datos PostgreSQL (Railway la provee)
DATABASE_URL = os.getenv('DATABASE_URL')

def get_db_connection():
    conn = psycopg2.connect(DATABASE_URL)
    return conn

def init_db():
    """Inicializar base de datos"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trends (
            id SERIAL PRIMARY KEY,
            topic TEXT NOT NULL,
            analysis JSONB,
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
        'INSERT INTO trends (topic, analysis) VALUES (%s, %s)',
        (topic, json.dumps(analysis))
    )
    
    conn.commit()
    conn.close()

def get_trends(limit=20):
    """Obtener tendencias recientes"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        'SELECT topic, analysis, created_at FROM trends ORDER BY created_at DESC LIMIT %s',
        (limit,)
    )
    
    rows = cursor.fetchall()
    conn.close()
    
    return [
        {
            'topic': row[0],
            'analysis': row[1] if isinstance(row[1], dict) else json.loads(row[1]) if row[1] else {},
            'created_at': row[2].isoformat() if row[2] else None
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
    app.run(debug=True)