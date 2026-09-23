# ==================== GDELT TRENDS ====================

def get_gdelt_trends(region='Global', limit=5):
    """Obtener tendencias desde GDELT (noticias reales)"""
    try:
        # Mapeo de regiones a códigos GDELT
        region_codes = {
            'Chile': 'Chile',
            'Sudamérica': 'South America',
            'Norteamérica': 'United States',
            'América Latina': 'Latin America',
            'Europa': 'Europe',
            'Asia': 'Asia',
            'Global': 'World'
        }
        
        country = region_codes.get(region, 'World')
        
        # API de GDELT para tendencias
        url = f'https://api.gdeltproject.org/api/v2/doc/doc?query={country}&mode=artlist&format=json'
        
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            # Extraer temas de las noticias
            trends = []
            seen_topics = set()
            
            for article in data.get('articles', [])[:limit * 2]:
                title = article.get('title', '')
                if title and title not in seen_topics:
                    seen_topics.add(title)
                    trends.append({
                        'topic': title,
                        'source': 'GDELT News',
                        'region': region,
                        'url': article.get('url', '')
                    })
                
                if len(trends) >= limit:
                    break
            
            return trends
        else:
            return []
            
    except Exception as e:
        print(f"Error GDELT: {e}")
        return []

# También agrega una función de respaldo con tendencias populares
def get_trending_fallback(limit=5):
    """Tendencias populares por defecto si GDELT falla"""
    default_trends = [
        "Inteligencia Artificial y su impacto laboral",
        "Cambio climático y energías renovables",
        "Economía digital y criptomonedas",
        "Salud mental en el trabajo",
        "Movilidad eléctrica"
    ]
    
    return [
        {'topic': topic, 'source': 'Trending Global', 'region': 'Global'}
        for topic in default_trends[:limit]
    ]

# Actualiza la función get_google_trends para usar GDELT
def get_google_trends(region='Global', limit=5):
    """Wrapper que usa GDELT como fuente principal"""
    trends = get_gdelt_trends(region, limit)
    
    # Si GDELT no devuelve nada, usar fallback
    if not trends:
        trends = get_trending_fallback(limit)
    
    return trends
