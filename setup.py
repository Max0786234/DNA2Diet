"""
Setup script for DNA2Diet application
This script helps initialize the database and verify dependencies
"""

import subprocess
import sys
import os
from pathlib import Path

def check_python_version():
    """Check if Python version is 3.8 or higher"""
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        print("❌ Python 3.8 or higher is required")
        print(f"   Current version: {version.major}.{version.minor}.{version.micro}")
        return False
    print(f"✅ Python version: {version.major}.{version.minor}.{version.micro}")
    return True

def check_mysql():
    """Check if MySQL is accessible"""
    try:
        import pymysql
        print("✅ PyMySQL is installed")
        return True
    except ImportError:
        print("⚠️  PyMySQL not installed. Install with: pip install PyMySQL")
        return False

def check_dependencies():
    """Check if required files exist"""
    print("\n📋 Checking required files...")
    
    gwas_file = Path("gwas.tsv")
    if gwas_file.exists():
        print(f"✅ GWAS file found: {gwas_file}")
    else:
        print(f"❌ GWAS file not found: {gwas_file}")
        print("   Please ensure gwas.tsv is in the root directory")
        return False
    
    prevalences_file = Path("prevalences.json")
    if prevalences_file.exists():
        print(f"✅ Prevalences file found: {prevalences_file}")
    else:
        print(f"⚠️  Prevalences file not found: {prevalences_file}")
        print("   (Optional - will work without it)")
    
    return True

def create_directories():
    """Create necessary directories"""
    print("\n📁 Creating directories...")
    
    dirs = ['user_data', 'templates', 'processing', 'database']
    for dir_name in dirs:
        dir_path = Path(dir_name)
        dir_path.mkdir(exist_ok=True)
        print(f"✅ Directory created/verified: {dir_path}")
    
    return True

def print_next_steps():
    """Print next steps for setup"""
    print("\n" + "="*60)
    print("📝 Next Steps:")
    print("="*60)
    print("\n1. Install Python dependencies:")
    print("   pip install -r requirements.txt")
    print("\n2. Install scispaCy model (optional - can skip if build errors occur):")
    print("   pip install https://s3-us-west-2.amazonaws.com/ai2-s2-scispacy/releases/v0.5.3/en_core_sci_sm-0.5.3.tar.gz")
    print("   Note:")
    print("   - On Windows, requires Microsoft Visual C++ Build Tools")
    print("   - Application works fine without it - just uses direct API lookups")
    print("   - Skip this step if installation fails - core functionality doesn't depend on it")
    print("\n3. Set up MySQL database:")
    print("   mysql -u root -p1234 < database/schema.sql")
    print("   (Or import schema.sql manually into MySQL)")
    print("\n4. Configure MySQL connection in app.py if needed:")
    print("   app.config['MYSQL_HOST'] = 'localhost'")
    print("   app.config['MYSQL_USER'] = 'root'")
    print("   app.config['MYSQL_PASSWORD'] = '1234'")
    print("\n5. Run the application:")
    print("   python app.py")
    print("\n6. Access the application:")
    print("   http://localhost:5000")
    print("\n" + "="*60)

def main():
    print("="*60)
    print("DNA2Diet Setup Script")
    print("="*60)
    
    # Check Python version
    if not check_python_version():
        sys.exit(1)
    
    # Check dependencies
    if not check_dependencies():
        print("\n⚠️  Some required files are missing. Please ensure all files are present.")
        sys.exit(1)
    
    # Create directories
    create_directories()
    
    # Print next steps
    print_next_steps()

if __name__ == "__main__":
    main()

