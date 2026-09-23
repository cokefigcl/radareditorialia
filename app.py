import traceback

@app.route('/api/analyze', methods=['POST'])
def analyze():
    """Endpoint para analizar una tendencia con IA"""
    try:
        data = request.json
        trend_topic = data.get('topic', '')
        
        if not trend_topic:
            return jsonify({'error': 'Topic is required'}), 400
        
        # Verificar que la API key esté configurada
        api_key = os.getenv('QWEN_API_KEY')
        print(f"DEBUG: API key configurada: {api_key is not None}")
        
        if not api_key:
            return jsonify({'error': 'API key no configurada. Agrega QWEN_API_KEY en Variables de Railway'}), 500
        
        # Analizar con Qwen
        print(f"DEBUG: Analizando tendencia: {trend_topic}")
        analysis = analyze_trend_with_qwen(trend_topic)
        print(f"DEBUG: Análisis completado: {analysis}")
        
        # Guardar en base de datos
        save_trend(trend_topic, analysis)
        
        return jsonify({
            'topic': trend_topic,
            'analysis': analysis,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        print(f"ERROR: {str(e)}")
        print(traceback.format_exc())
        return jsonify({'error': str(e)}), 500
