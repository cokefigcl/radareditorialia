def get_google_trends_chile():
    """Obtiene tendencias desde Google Trends Chile (scraping con filtros)"""
    try:
        print("[TRENDS] Consultando Google Trends Chile...")
        
        url = 'https://trends.google.com/trends/trendingsearches/daily?geo=CL'
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'es-CL,es;q=0.9'
        }
        
        response = requests.get(url, timeout=20, headers=headers)
        
        if response.status_code != 200:
            print(f"[TRENDS] Google Trends falló: {response.status_code}")
            return []
        
        html_content = response.text
        topics = []
        seen = set()
        
        # Buscar en el HTML usando patrones más específicos
        # Google Trends pone los títulos en attributes o en divs específicos
        
        # Patrón 1: Buscar en divs con title attribute
        pattern = r'title="([^"]+)"'
        matches = re.findall(pattern, html_content)
        
        for match in matches:
            # Filtrar: mínimo 10 chars, máximo 150, no sea código JS
            if (match and 
                len(match) > 10 and 
                len(match) < 150 and 
                not match.startswith(('window', 'function', 'var', 'let', 'const', 'document', 'gtm')) and
                'dataLayer' not in match and
                'gtag' not in match and
                not match.startswith('{') and
                not match.startswith('[') and
                match.lower() not in seen):
                
                seen.add(match.lower())
                topics.append({
                    'topic': match,
                    'source': 'Google Trends',
                    'is_realtime': True
                })
        
        # Patrón 2: Buscar en spans o divs con clases específicas
        if len(topics) < 5:
            pattern2 = r'<(?:span|div)[^>]*>([^<]{10,150}?)</(?:span|div)>'
            matches2 = re.findall(pattern2, html_content)
            
            for match in matches2:
                clean = match.strip()
                if (clean and 
                    len(clean) > 10 and 
                    len(clean) < 150 and
                    not clean.startswith(('window', 'function', 'var', 'let', 'const')) and
                    'dataLayer' not in clean and
                    'gtag' not in clean and
                    clean.lower() not in seen and
                    any(word in clean.lower() for word in ['chile', 'santiago', 'gobierno', 'presidente', 'ley', 'nuevo', 'más', 'hoy', 'ayer'])):
                    
                    seen.add(clean.lower())
                    topics.append({
                        'topic': clean,
                        'source': 'Google Trends',
                        'is_realtime': True
                    })
        
        print(f"[TRENDS] ✅ Google Trends: {len(topics)} temas válidos encontrados")
        return topics[:15]
        
    except Exception as e:
        print(f"[TRENDS] ⚠️ Error Google Trends: {str(e)}")
        return []
