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
    {'name': 'Eléctrico', 'icon': '⚡', 'type': 'tema'},
    {'name': 'Automotriz', 'icon': '🚗', 'type': 'tema'},
    {'name': 'Belleza', 'icon': '💄', 'type': 'tema'},
    {'name': 'Minería', 'icon': '⛏️', 'type': 'tema'},
    {'name': 'IA', 'icon': '🤖', 'type': 'tema'},
    {'name': 'Tendencias', 'icon': '📈', 'type': 'tema'},
    {'name': 'Tecnología', 'icon': '💻', 'type': 'tema'},
    {'name': 'Economía', 'icon': '💰', 'type': 'tema'},
    {'name': 'Nacional', 'icon': '🇨🇱', 'type': 'region'},
    {'name': 'Internacional', 'icon': '🌍', 'type': 'region'},
    {'name': 'Valparaíso', 'icon': '🏖️', 'type': 'region'},
    {'name': 'Metropolitana', 'icon': '🏙️', 'type': 'region'},
    {'name': 'Biobío', 'icon': '🌲', 'type': 'region'},
    {'name': 'Araucanía', 'icon': '🌳', 'type': 'region'},
    {'name': 'Los Ríos', 'icon': '🌊', 'type': 'region'},
    {'name': 'Los Lagos', 'icon': '🏔️', 'type': 'region'},
    {'name': 'Deportes', 'icon': '⚽', 'type': 'seccion'},
    {'name': 'Ciencia y Tecnología', 'icon': '🔬', 'type': 'seccion'},
    {'name': 'Cultura', 'icon': '🎭', 'type': 'seccion'},
    {'name': 'Dopamina', 'icon': '🧠', 'type': 'seccion'},
    {'name': 'Salud', 'icon': '🏥', 'type': 'seccion'},
    {'name': 'Sociedad', 'icon': '👥', 'type': 'seccion'},
    {'name': 'TV y Espectáculos', 'icon': '📺', 'type': 'seccion'}
]

SEARCH_KEYWORDS = {
    'Eléctrico': 'electromovilidad OR energía solar',
    'Automotriz': 'autos OR vehículos',
    'Belleza': 'belleza OR cosmética',
    'Minería': 'minería OR cobre OR litio',
    'IA': 'inteligencia artificial OR IA',
    'Tendencias': 'tendencias Chile',
    'Tecnología': 'tecnología OR 5G',
    'Economía': 'economía OR dólar OR inflación',
    'Nacional': 'Chile',
    'Internacional': 'internacional',
    'Valparaíso': 'Valparaíso',
    'Metropolitana': 'Santiago',
    'Biobío': 'Biobío OR Concepción',
    'Araucanía': 'Araucanía OR Temuco',
    'Los Ríos': 'Valdivia',
    'Los Lagos': 'Puerto Montt',
    'Deportes': 'deportes OR fútbol',
    'Ciencia y Tecnología': 'ciencia OR tecnología',
    'Cultura': 'cultura OR arte',
    'Dopamina': 'redes sociales OR viral',
    'Salud': 'salud OR medicina',
    'Sociedad': 'sociedad',
    'TV y Espectáculos': 'televisión OR espectáculos'
}

# ==================== DATOS DE RESPALDO (SIEMPRE FUNCIONAN) ====================
FALLBACK_PREDICTIONS = [
    {'topic': 'Reforma de pensiones en Chile: nuevo debate en el Congreso', 'score': 85, 'category': 'Nacional', 'news_count': 12, 'news': [{'titulo': 'Congreso discute nueva reforma de pensiones', 'fuente': 'La Tercera', 'url': '', 'fecha': '2026-09-25'}], 'alert_level': 'high', 'source': 'Datos de respaldo', 'is_realtime': False, 'timestamp': datetime.now().isoformat()},
    {'topic': 'Crisis de seguridad en Santiago: nuevas medidas gubernamentales', 'score': 80, 'category': 'Sociedad', 'news_count': 10, 'news': [{'titulo': 'Gobierno anuncia plan de seguridad para Santiago', 'fuente': 'BioBio Chile', 'url': '', 'fecha': '2026-09-25'}], 'alert_level': 'high', 'source': 'Datos de respaldo', 'is_realtime': False, 'timestamp': datetime.now().isoformat()},
    {'topic': 'Precio del dólar alcanza nuevo máximo histórico', 'score': 75, 'category': 'Economía', 'news_count': 8, 'news': [{'titulo': 'Dólar supera los $950 pesos chilenos', 'fuente': 'DF', 'url': '', 'fecha': '2026-09-25'}], 'alert_level': None, 'source': 'Datos de respaldo', 'is_realtime': False, 'timestamp': datetime.now().isoformat()},
    {'topic': 'Selección chilena de fútbol: preparativos para eliminatorias', 'score': 70, 'category': 'Deportes', 'news_count': 7, 'news': [{'titulo': 'La Roja se prepara para próximo partido eliminatorio', 'fuente': 'AS Chile', 'url': '', 'fecha': '2026-09-25'}], 'alert_level': None, 'source': 'Datos de respaldo', 'is_realtime': False, 'timestamp': datetime.now().isoformat()},
    {'topic': 'Avance de inteligencia artificial en empresas chilenas', 'score': 65, 'category': 'Tecnología', 'news_count': 6, 'news': [{'titulo': 'Startups chilenas lideran adopción de IA', 'fuente': 'Pulso', 'url': '', 'fecha': '2026-09-25'}], 'alert_level': None, 'source': 'Datos de respaldo', 'is_realtime': False, 'timestamp': datetime.now().isoformat()},
    {'topic': 'Crisis habitacional: nuevos proyectos de vivienda social', 'score': 60, 'category': 'Sociedad', 'news_count': 5, 'news': [{'titulo': 'MINVU anuncia construcción de 10.000 nuevas viviendas', 'fuente': 'La Tercera', 'url': '', 'fecha': '2026-09-25'}], 'alert_level': None, 'source': 'Datos de respaldo', 'is_realtime': False, 'timestamp': datetime.now().isoformat()},
    {'topic': 'Precio del cobre: impacto en economía chilena', 'score': 55, 'category': 'Economía', 'news_count': 4, 'news': [{'titulo': 'Cobre alcanza máximos de 6 meses', 'fuente': 'DF', 'url': '', 'fecha': '2026-09-25'}], 'alert_level': None, 'source': 'Datos de respaldo', 'is_realtime': False, 'timestamp': datetime.now().isoformat()},
    {'topic': 'Listas de espera en salud pública: nuevas soluciones', 'score': 50, 'category': 'Salud', 'news_count': 3, 'news': [{'titulo': 'MINSAL implementa sistema digital para reducir listas', 'fuente': '24 Horas', 'url': '', 'fecha': '2026-09-25'}], 'alert_level': None, 'source': 'Datos de respaldo', 'is_realtime': False, 'timestamp': datetime.now().isoformat()}
]

FALLBACK_TRENDS = [
    {'topic': 'Reforma de pensiones genera debate en el Congreso Nacional', 'source': 'La Tercera', 'region': 'Chile'},
    {'topic': 'Nuevas medidas de seguridad para Santiago Centro', 'source': 'BioBio Chile', 'region': 'Chile'},
    {'topic': 'Dólar cierra al alza y alcanza nuevo récord histórico', 'source': 'El Mercurio', 'region': 'Chile'},
    {'topic': 'Selección chilena se prepara para eliminatorias mundialistas', 'source': 'AS Chile', 'region': 'Chile'},
    {'topic': 'Inteligencia artificial transforma empresas chilenas', 'source': 'Pulso', 'region': 'Chile'}
]

# ==================== GDELT (GRATIS, SIN LÍMITES) ====================

def get_gdelt_predictions():
    try:
        print("[PREDICT] Consultando GDELT...")
        url = 'https://api.gdeltproject.org/api/v2/doc/doc'
        params = {
            'query': 'Chile',
            'mode': 'artlist',
            'format': 'json',
            'startdatetime': (datetime.now() - timedelta(days=1)).strftime('%Y%m%d%H%M%S'),
            'enddatetime': datetime.now().strftime('%
