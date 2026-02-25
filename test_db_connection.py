"""
Test PostgreSQL connection
"""
import json
import time
import os
import sys

LOG_PATH = r'c:\Users\eduar\Desktop\Проект\schedule\.cursor\debug.log'

def log(hyp_id, msg, data=None):
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, 'a', encoding='utf-8') as f:
        f.write(json.dumps({
            'hypothesisId': hyp_id,
            'message': msg,
            'data': data,
            'timestamp': int(time.time() * 1000)
        }, ensure_ascii=False) + '\n')

log('START', 'Test script started')

# Check if .env exists
env_exists = os.path.exists('.env')
log('H1', '.env file check', {'exists': env_exists})

# Check DATABASE_URL - read .env manually
db_url = None
if env_exists:
    try:
        with open('.env', 'r', encoding='utf-8') as f:
            for line in f:
                if line.startswith('DATABASE_URL='):
                    db_url = line.split('=', 1)[1].strip()
                    break
    except Exception as e:
        log('H1b', '.env read error', {'error': str(e)})

if not db_url:
    db_url = os.environ.get('DATABASE_URL')
log('H2', 'DATABASE_URL', {
    'is_set': db_url is not None,
    'value_preview': db_url[:50] if db_url else 'NOT SET (using default)'
})

# Test connection
db_url = db_url or 'postgresql://postgres:password@localhost:5432/school_schedule'
log('H3', 'Attempting connection', {'url_start': db_url[:40]})

try:
    import psycopg2
    log('H4', 'psycopg2 imported OK')
    
    # Parse URL manually to avoid encoding issues
    # Format: postgresql://user:password@host:port/database
    from urllib.parse import urlparse
    parsed = urlparse(db_url)
    log('H5', 'URL parsed', {
        'scheme': parsed.scheme,
        'hostname': parsed.hostname,
        'port': parsed.port,
        'database': parsed.path[1:] if parsed.path else None,
        'username': parsed.username
    })
    
    # #region agent log - H1: Test with PGCLIENTENCODING for Windows locale fix
    import locale
    log('H1_LOCALE', 'System locale info', {
        'preferred_encoding': locale.getpreferredencoding(),
        'default_encoding': sys.getdefaultencoding(),
        'filesystem_encoding': sys.getfilesystemencoding()
    })
    # #endregion
    
    # #region agent log - H2: First try standard connection
    log('H2_CONNECT', 'Attempting standard connection')
    try:
        conn = psycopg2.connect(
            host=parsed.hostname,
            port=parsed.port or 5432,
            database=parsed.path[1:] if parsed.path else 'school_schedule',
            user=parsed.username or 'postgres',
            password=parsed.password or 'password'
        )
        log('H6', 'Connection SUCCESS!')
        conn.close()
        print("SUCCESS: Database connection works!")
    except UnicodeDecodeError as ude:
        # #region agent log - H1: Catch encoding error details
        log('H1_ENCODING_ERR', 'UnicodeDecodeError caught - likely Windows locale issue', {
            'encoding': ude.encoding,
            'reason': ude.reason,
            'start': ude.start,
            'end': ude.end,
            'object_bytes': ude.object[max(0,ude.start-10):ude.end+10].hex() if isinstance(ude.object, bytes) else str(ude.object)[:100]
        })
        # #endregion
        print(f"UnicodeDecodeError: {ude}")
        
        # #region agent log - H3: Try with client_encoding
        log('H3_RETRY', 'Retrying with client_encoding=utf8')
        try:
            os.environ['PGCLIENTENCODING'] = 'UTF8'
            conn2 = psycopg2.connect(
                host=parsed.hostname,
                port=parsed.port or 5432,
                database=parsed.path[1:] if parsed.path else 'school_schedule',
                user=parsed.username or 'postgres',
                password=parsed.password or 'password',
                client_encoding='utf8'
            )
            log('H3_SUCCESS', 'Connection with client_encoding=utf8 SUCCESS')
            conn2.close()
            print("SUCCESS with client_encoding fix!")
        except Exception as e2:
            log('H3_FAIL', 'Retry also failed', {'error': str(e2)[:200]})
            print(f"Retry also failed: {e2}")
        # #endregion
        raise
    # #endregion
    
except Exception as e:
    log('H7', 'Connection FAILED', {
        'error_type': type(e).__name__,
        'error_msg': str(e)[:200],
        'error_repr': repr(e)[:300]
    })
    print(f"ERROR: {type(e).__name__}: {e}")
    
    # Additional info
    log('H8', 'System info', {
        'python_version': sys.version,
        'cwd': os.getcwd(),
        'encoding': sys.getdefaultencoding()
    })

log('END', 'Test script finished')
print(f"\nLogs written to: {LOG_PATH}")
