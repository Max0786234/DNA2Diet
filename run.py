"""
DNA2Diet Web Application Launcher
Simple entry point to run the Flask application
"""

import os
import sys

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app

if __name__ == '__main__':
    # Get configuration from environment variables or use defaults
    host = os.getenv('FLASK_HOST', '0.0.0.0')
    port = int(os.getenv('FLASK_PORT', 5000))
    debug = os.getenv('FLASK_DEBUG', 'True').lower() == 'true'
    
    print("=" * 60)
    print("🚀 DNA2Diet Web Application Starting...")
    print("=" * 60)
    print(f"📍 Server: http://{host}:{port}")
    print(f"🐛 Debug Mode: {debug}")
    print("=" * 60)
    print("\nPress CTRL+C to stop the server\n")
    
    app.run(debug=debug, host=host, port=port)

