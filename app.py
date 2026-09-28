def predict_trends(articles, top: int = 8):
    """Predicción: mostrar titulares más relevantes y recientes"""
    if not articles:
        print("[PREDICT]  Sin artículos")
        return []
    
    print(f"[PREDICT] Procesando {len(articles)} artículos...")
    now = datetime.now(timezone.utc)
    
    # Calcular score para cada artículo individual
    scored = []
    for a in articles:
        title = a['title']
        source = a['source']
        
        # Recencia
        try:
            fs = a.get('first_seen')
            if isinstance(fs, str):
                fs = datetime.fromisoformat(fs.replace('Z', '+00:00'))
            age_hours = (now - fs).total_seconds() / 3600
            recency_score = max(0, 100 - (age_hours * 5))  # Pierde 5 puntos por hora
        except:
            recency_score = 50
        
        # Bonus por fuente confiable
        source_bonus = 0
        if source == 'biobio':
            source_bonus = 10
        elif source == 'latercera':
            source_bonus = 8
        elif source == 'cooperativa':
            source_bonus = 6
        elif source == 'df':
            source_bonus = 5
        
        # Longitud del titular (ni muy corto ni muy largo)
        length = len(title)
        length_score = 0
        if 40 <= length <= 100:
            length_score = 10
        
        total_score = recency_score + source_bonus + length_score
        
        scored.append({
            'topic': title,
            'source': source,
            'score': round(min(100, total_score)),
            'first_seen': a.get('first_seen')
        })
    
    # Ordenar por score
    scored.sort(key=lambda x: x['score'], reverse=True)
    
    # Tomar los top y eliminar duplicados muy similares
    result = []
    seen_topics = set()
    
    for s in scored:
        # Normalizar para detectar duplicados
        norm = _norm(s['topic'])
        is_duplicate = False
        
        for seen in seen_topics:
            # Verificar similitud
            if norm in seen or seen in norm:
                is_duplicate = True
                break
        
        if not is_duplicate and len(result) < top:
            seen_topics.add(norm)
            result.append({
                'topic': s['topic'],
                'score': s['score'],
                'category': guess_category(s['topic']),
                'news_count': 1,
                'news': [{'titulo': s['topic'], 'fuente': s['source'], 'url': '', 'fecha': now.strftime('%Y-%m-%d')}],
                'alert_level': 'critical' if s['score'] >= 90 else ('high' if s['score'] >= 75 else None),
                'source': 'Algoritmo de Tendencias',
                'is_realtime': True,
                'timestamp': now.isoformat()
            })
    
    print(f"[PREDICT] ✅ Generadas {len(result)} predicciones")
    return result
