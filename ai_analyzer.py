import requests
import os
import json
from datetime import datetime

def analyze_trend_with_qwen(topic):
    """Analizar una tendencia usando la API de Qwen"""
    api_key = os.getenv('QWEN_API_KEY')
    
    if not api_key:
        return {'error': 'API key no configurada'}
    
    prompt = f"""Eres un analista de inteligencia informativa experto. Analiza la siguiente tendencia periodística:

TEMA: {topic}

Proporciona un análisis estructurado en formato JSON con:
1. "hipotesis": Tu hipótesis principal sobre cómo evolucionará esta tendencia
2. "senales_clave": Lista de 3-5 señales que deberían monitorearse
3. "angulos_periodisticos": Lista de 3 ángulos periodísticos interesantes para investigar
4. "fuentes_sugeridas": Tipos de fuentes que deberían consultarse
5. "riesgos": Posibles riesgos o aspectos controvertidos

Sé específico y práctico. Formato JSON puro."""

    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    
    data = {
        'model': 'qwen-plus',
        'messages': [
            {'role': 'user', 'content': prompt}
        ],
        'temperature': 0.7,
        'max_tokens': 1000
    }
    
    try:
        response = requests.post(
            'https://dashscope-intl.aliyuncs.com/api/v1/services/aigc/text-generation/generation',
            headers=headers,
            json=data,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            analysis_text = result['output']['text']
            
            try:
                analysis = json.loads(analysis_text)
            except:
                analysis = {'raw_analysis': analysis_text}
            
            return analysis
        else:
            return {
                'error': f'API error: {response.status_code}',
                'details': response.text
            }
            
    except Exception as e:
        return {
            'error': str(e),
            'status': 'failed'
        }
