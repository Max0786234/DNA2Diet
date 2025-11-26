"""
DNA2Diet Web Application
Main Flask application file
"""

import pymysql
pymysql.install_as_MySQLdb()


from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_file
from flask_mysqldb import MySQL
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
import json
from pathlib import Path
from datetime import datetime
import uuid
import threading
from functools import wraps
import shutil

# Import processing modules
from processing.genome_processor import process_genome_file
from processing.disease_estimator import estimate_diseases
from processing.disease_finalizer import finalize_diseases
from processing.mesh_processor import process_mesh
from processing.ingredient_extractor import extract_ingredients
from processing.recipe_processor import get_recipes_for_analysis
import csv

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-in-production'
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max file size

# MySQL Configuration
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = '1234'
app.config['MYSQL_DB'] = 'dna2diet'
app.config['MYSQL_CURSORCLASS'] = 'DictCursor'

mysql = MySQL(app)

# Base directory for user files
UPLOAD_FOLDER = Path('user_data')
UPLOAD_FOLDER.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {'txt', 'csv'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def delete_path(path_str):
    """Safely remove a file or directory."""
    if not path_str:
        return
    try:
        path = Path(path_str)
        if not path.exists():
            return
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
    except Exception as e:
        print(f"Warning: failed to remove {path_str}: {e}")

def get_user_folder(user_id):
    """Get or create user-specific folder"""
    user_folder = UPLOAD_FOLDER / str(user_id)
    user_folder.mkdir(exist_ok=True)
    return user_folder

def login_required(f):
    """Decorator to require login"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Routes
@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        first_name = request.form.get('first_name')
        last_name = request.form.get('last_name')
        
        if not email or not password or not first_name or not last_name:
            flash('All fields are required.', 'danger')
            return render_template('register.html')
        
        cur = mysql.connection.cursor()
        
        # Check if user exists
        cur.execute("SELECT id FROM users WHERE email = %s", (email,))
        if cur.fetchone():
            flash('Email already registered. Please login.', 'danger')
            return render_template('register.html')
        
        # Create user
        hashed_password = generate_password_hash(password)
        cur.execute(
            "INSERT INTO users (email, password, first_name, last_name, created_at) VALUES (%s, %s, %s, %s, NOW())",
            (email, hashed_password, first_name, last_name)
        )
        mysql.connection.commit()
        user_id = cur.lastrowid
        cur.close()
        
        # Create user folder
        get_user_folder(user_id)
        
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cur.fetchone()
        cur.close()
        
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['user_name'] = f"{user['first_name']} {user['last_name']}"
            session['user_email'] = user['email']
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password.', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    user_id = session['user_id']
    cur = mysql.connection.cursor()
    
    # Get user's analysis history
    cur.execute("""
        SELECT id, genome_filename, status, progress_step, progress_percent, 
               created_at, completed_at, error_message
        FROM analyses 
        WHERE user_id = %s 
        ORDER BY created_at DESC 
        LIMIT 10
    """, (user_id,))
    analyses = cur.fetchall()
    
    # Get profile completion status
    cur.execute("SELECT * FROM user_profiles WHERE user_id = %s", (user_id,))
    profile = cur.fetchone()
    
    cur.close()
    
    return render_template('dashboard.html', analyses=analyses, profile=profile)

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    user_id = session['user_id']
    cur = mysql.connection.cursor()
    
    if request.method == 'POST':
        age = request.form.get('age')
        gender = request.form.get('gender')
        height = request.form.get('height')  # in cm
        weight = request.form.get('weight')  # in kg
        blood_type = request.form.get('blood_type')
        activity_level = request.form.get('activity_level')
        medical_history = request.form.get('medical_history')
        allergies = request.form.get('allergies')
        medications = request.form.get('medications')
        
        # Calculate BMI if height and weight provided
        bmi = None
        if height and weight:
            try:
                height_m = float(height) / 100  # convert cm to m
                weight_kg = float(weight)
                bmi = round(weight_kg / (height_m ** 2), 2)
            except:
                pass
        
        # Check if profile exists
        cur.execute("SELECT id FROM user_profiles WHERE user_id = %s", (user_id,))
        exists = cur.fetchone()
        
        if exists:
            cur.execute("""
                UPDATE user_profiles 
                SET age=%s, gender=%s, height=%s, weight=%s, bmi=%s, blood_type=%s, 
                    activity_level=%s, medical_history=%s, allergies=%s, medications=%s, updated_at=NOW()
                WHERE user_id = %s
            """, (age, gender, height, weight, bmi, blood_type, activity_level, 
                  medical_history, allergies, medications, user_id))
        else:
            cur.execute("""
                INSERT INTO user_profiles 
                (user_id, age, gender, height, weight, bmi, blood_type, activity_level, 
                 medical_history, allergies, medications, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
            """, (user_id, age, gender, height, weight, bmi, blood_type, activity_level,
                  medical_history, allergies, medications))
        
        mysql.connection.commit()
        cur.close()
        flash('Profile updated successfully!', 'success')
        return redirect(url_for('profile'))
    
    # GET request - show profile
    cur.execute("SELECT * FROM user_profiles WHERE user_id = %s", (user_id,))
    profile = cur.fetchone()
    cur.close()
    
    return render_template('profile.html', profile=profile)

@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    if request.method == 'POST':
        if 'genome_file' not in request.files:
            flash('No file selected.', 'danger')
            return redirect(request.url)
        
        file = request.files['genome_file']
        
        if file.filename == '':
            flash('No file selected.', 'danger')
            return redirect(request.url)
        
        if file and allowed_file(file.filename):
            user_id = session['user_id']
            user_folder = get_user_folder(user_id)
            
            # Generate unique filename
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = secure_filename(file.filename)
            unique_filename = f"{timestamp}_{filename}"
            filepath = user_folder / unique_filename
            
            file.save(str(filepath))
            
            # Save analysis record
            cur = mysql.connection.cursor()
            cur.execute("""
                INSERT INTO analyses (user_id, genome_filename, filepath, status, created_at)
                VALUES (%s, %s, %s, 'processing', NOW())
            """, (user_id, filename, str(filepath)))
            analysis_id = cur.lastrowid
            mysql.connection.commit()
            cur.close()
            
            # Process in background
            thread = threading.Thread(
                target=process_analysis_background,
                args=(analysis_id, user_id, str(filepath), user_folder)
            )
            thread.daemon = True
            thread.start()
            
            flash('Genome file uploaded successfully! Processing started.', 'success')
            return redirect(url_for('results', analysis_id=analysis_id))
    
    return render_template('upload.html')

@app.route('/analysis/<int:analysis_id>/delete', methods=['POST'])
@login_required
def delete_analysis(analysis_id):
    """Allow users to delete their analysis and associated files."""
    user_id = session['user_id']
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM analyses WHERE id = %s AND user_id = %s", (analysis_id, user_id))
    analysis = cur.fetchone()
    if not analysis:
        flash('Analysis not found.', 'danger')
        cur.close()
        return redirect(url_for('dashboard'))

    # Remove files associated with the analysis
    file_keys = [
        'filepath',
        'nutritional_snp_path',
        'disease_candidates_path',
        'selected_diseases_path',
        'disease_json_path',
        'ingredient_json_path'
    ]
    for key in file_keys:
        delete_path(analysis.get(key))

    # Remove disease details directory if present
    user_folder = get_user_folder(user_id)
    details_dir = user_folder / f"disease_details_{analysis_id}"
    delete_path(details_dir)

    cur.execute("DELETE FROM analyses WHERE id = %s", (analysis_id,))
    mysql.connection.commit()
    cur.close()

    flash('Analysis deleted.', 'info')
    return redirect(url_for('dashboard'))

def update_progress(analysis_id, step, progress_percent):
    """Update analysis progress"""
    try:
        # Create new connection for background thread
        import pymysql
        conn = pymysql.connect(
            host=app.config['MYSQL_HOST'],
            user=app.config['MYSQL_USER'],
            password=app.config['MYSQL_PASSWORD'],
            database=app.config['MYSQL_DB']
        )
        cur = conn.cursor()
        cur.execute("""
            UPDATE analyses 
            SET progress_step = %s, progress_percent = %s 
            WHERE id = %s
        """, (step, progress_percent, analysis_id))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Error updating progress: {e}")

def process_analysis_background(analysis_id, user_id, genome_filepath, user_folder):
    """Process analysis in background thread"""
    import pymysql
    try:
        # Create MySQL connection for background thread
        conn = pymysql.connect(
            host=app.config['MYSQL_HOST'],
            user=app.config['MYSQL_USER'],
            password=app.config['MYSQL_PASSWORD'],
            database=app.config['MYSQL_DB']
        )
        cur = conn.cursor()
        cur.execute("UPDATE analyses SET status = 'processing', progress_step = 'Starting...', progress_percent = 0 WHERE id = %s", (analysis_id,))
        conn.commit()
        cur.close()
        conn.close()
        
        # Step 1: Process genome file (20%)
        update_progress(analysis_id, 'Processing genome file...', 10)
        nutritional_snp_path = process_genome_file(
            genome_filepath,
            user_folder,
            analysis_id,
            progress_callback=lambda step, percent: update_progress(analysis_id, step, percent)
        )
        update_progress(analysis_id, 'Genome processed', 32)
        
        # Step 2: Estimate diseases (40%)
        update_progress(analysis_id, 'Estimating diseases...', 35)
        disease_candidates_path = estimate_diseases(nutritional_snp_path, user_folder, analysis_id)
        update_progress(analysis_id, 'Diseases estimated', 50)
        
        # Step 3: Finalize diseases (60%)
        update_progress(analysis_id, 'Finalizing disease analysis...', 60)
        selected_diseases_path = finalize_diseases(
            disease_candidates_path, nutritional_snp_path, user_folder, analysis_id
        )
        update_progress(analysis_id, 'Diseases finalized', 65)
        
        # Step 4: Process MESH (80%) - Skip if API is slow, use mock data
        update_progress(analysis_id, 'Fetching disease details...', 70)
        try:
            disease_json_path = process_mesh(selected_diseases_path, user_folder, analysis_id)
        except Exception as e:
            print(f"Warning: MESH processing failed: {e}. Using simplified results.")
            # Create a simplified disease.json if MESH fails
            import json
            disease_json_path = user_folder / f"disease_{analysis_id}.json"
            with open(selected_diseases_path, 'r') as f:
                diseases = json.load(f)
            simplified = [{"trait": d["trait"], "result": {"foodDiseases": []}} for d in diseases[:10]]
            with open(disease_json_path, 'w') as f:
                json.dump(simplified, f)
        update_progress(analysis_id, 'Disease details processed', 85)
        
        # Step 5: Extract ingredients (100%)
        update_progress(analysis_id, 'Extracting ingredients...', 90)
        ingredient_json_path = extract_ingredients(disease_json_path, user_folder, analysis_id)
        update_progress(analysis_id, 'Complete!', 100)
        
        # Update analysis status
        conn = pymysql.connect(
            host=app.config['MYSQL_HOST'],
            user=app.config['MYSQL_USER'],
            password=app.config['MYSQL_PASSWORD'],
            database=app.config['MYSQL_DB']
        )
        cur = conn.cursor()
        cur.execute("""
            UPDATE analyses 
            SET status = 'completed', 
                progress_step = 'Complete!',
                progress_percent = 100,
                nutritional_snp_path = %s,
                disease_candidates_path = %s,
                selected_diseases_path = %s,
                disease_json_path = %s,
                ingredient_json_path = %s,
                completed_at = NOW()
            WHERE id = %s
        """, (str(nutritional_snp_path), str(disease_candidates_path), 
              str(selected_diseases_path), str(disease_json_path), 
              str(ingredient_json_path), analysis_id))
        conn.commit()
        cur.close()
        conn.close()
            
    except Exception as e:
        import traceback
        error_msg = f"{str(e)}\n{traceback.format_exc()}"
        try:
            # Create new connection for error update
            conn = pymysql.connect(
                host=app.config['MYSQL_HOST'],
                user=app.config['MYSQL_USER'],
                password=app.config['MYSQL_PASSWORD'],
                database=app.config['MYSQL_DB']
            )
            cur = conn.cursor()
            cur.execute("""
                UPDATE analyses 
                SET status = 'failed', 
                    error_message = %s,
                    progress_step = 'Failed',
                    progress_percent = 0
                WHERE id = %s
            """, (error_msg[:500], analysis_id))
            conn.commit()
            cur.close()
            conn.close()
        except Exception as db_error:
            print(f"Database error updating failure: {db_error}")
        print(f"Error processing analysis {analysis_id}: {error_msg}")

@app.route('/results/<int:analysis_id>')
@login_required
def results(analysis_id):
    user_id = session['user_id']
    cur = mysql.connection.cursor()
    
    # Verify analysis belongs to user
    cur.execute("SELECT * FROM analyses WHERE id = %s AND user_id = %s", (analysis_id, user_id))
    analysis = cur.fetchone()
    
    if not analysis:
        flash('Analysis not found.', 'danger')
        return redirect(url_for('dashboard'))
    
    cur.close()
    
    # Load results if available
    results_data = {}
    if analysis['status'] == 'completed':
        try:
            if analysis['selected_diseases_path'] and os.path.exists(analysis['selected_diseases_path']):
                with open(analysis['selected_diseases_path'], 'r') as f:
                    results_data['diseases'] = json.load(f)
            
            if analysis['ingredient_json_path'] and os.path.exists(analysis['ingredient_json_path']):
                with open(analysis['ingredient_json_path'], 'r') as f:
                    results_data['ingredients'] = json.load(f)
        except Exception as e:
            print(f"Error loading results: {e}")
    
    return render_template('results.html', analysis=analysis, results=results_data)

@app.route('/api/analysis_status/<int:analysis_id>')
@login_required
def analysis_status(analysis_id):
    user_id = session['user_id']
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT status, error_message, progress_step, progress_percent 
        FROM analyses WHERE id = %s AND user_id = %s
    """, (analysis_id, user_id))
    result = cur.fetchone()
    cur.close()
    
    if not result:
        return jsonify({'error': 'Not found'}), 404
    
    return jsonify({
        'status': result['status'],
        'error_message': result.get('error_message'),
        'progress_step': result.get('progress_step', 'Processing...'),
        'progress_percent': result.get('progress_percent', 0)
    })

@app.route('/recipes/<int:analysis_id>')
@login_required
def recipes(analysis_id):
    """Display recipes page for an analysis"""
    user_id = session['user_id']
    cur = mysql.connection.cursor()
    
    # Verify analysis belongs to user
    cur.execute("SELECT * FROM analyses WHERE id = %s AND user_id = %s", (analysis_id, user_id))
    analysis = cur.fetchone()
    
    if not analysis:
        flash('Analysis not found.', 'danger')
        return redirect(url_for('dashboard'))
    
    cur.close()
    
    # Load ingredient recommendations to get positive ingredients info
    ingredient_data = {}
    if analysis['status'] == 'completed' and analysis.get('ingredient_json_path'):
        try:
            if os.path.exists(analysis['ingredient_json_path']):
                with open(analysis['ingredient_json_path'], 'r') as f:
                    ingredient_data = json.load(f)
        except Exception as e:
            print(f"Error loading ingredient data: {e}")
    
    return render_template('recipes.html', analysis=analysis, ingredient_data=ingredient_data)

@app.route('/api/recipes/<int:analysis_id>')
@login_required
def api_recipes(analysis_id):
    """API endpoint to fetch paginated recipes"""
    user_id = session['user_id']
    cur = mysql.connection.cursor()
    
    # Verify analysis belongs to user
    cur.execute("SELECT * FROM analyses WHERE id = %s AND user_id = %s", (analysis_id, user_id))
    analysis = cur.fetchone()
    
    if not analysis:
        return jsonify({'error': 'Not found'}), 404
    
    cur.close()
    
    # Get pagination parameters
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 12, type=int)
    source = request.args.get('source', 'csv')  # 'csv' or 'api'
    
    # Check if ingredient recommendations exist
    if not analysis.get('ingredient_json_path') or not os.path.exists(analysis['ingredient_json_path']):
        return jsonify({
            'recipes': [],
            'total': 0,
            'page': page,
            'per_page': per_page,
            'total_pages': 0,
            'has_next': False,
            'has_prev': False,
            'error': 'Ingredient recommendations not available'
        })
    
    # Get recipes from CSV first
    try:
        csv_path = "recipe_recommendations.csv"  # Default path, can be made configurable
        result = get_recipes_for_analysis(
            analysis_id,
            analysis['ingredient_json_path'],
            csv_path,
            page,
            per_page
        )
        
        # If CSV has recipes, return them
        if result['total'] > 0:
            return jsonify(result)
        
        # If CSV is empty and source is 'api', fetch from API dynamically
        # For now, we'll stick with CSV-based approach
        # Dynamic API fetching can be added later as a background job
        return jsonify(result)
        
    except Exception as e:
        print(f"Error fetching recipes: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'recipes': [],
            'total': 0,
            'page': page,
            'per_page': per_page,
            'total_pages': 0,
            'has_next': False,
            'has_prev': False,
            'error': str(e)
        }), 500

@app.route('/recipe/<int:recipe_id>')
@login_required
def recipe_detail(recipe_id):
    """Display individual recipe detail page"""
    user_id = session['user_id']
    
    # Load recipe from CSV
    csv_path = "recipe_recommendations.csv"
    recipe = None
    
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('recipe_id') == str(recipe_id):
                    # Parse JSON fields
                    ingredient_phrases_str = row.get('ingredient_phrases', '[]')
                    ingredients_json_str = row.get('ingredients_json', '[]')
                    raw_json_str = row.get('raw_json', '{}')
                    
                    try:
                        ingredient_phrases = json.loads(ingredient_phrases_str)
                    except:
                        ingredient_phrases = []
                    
                    try:
                        ingredients_json = json.loads(ingredients_json_str)
                    except:
                        ingredients_json = []
                    
                    try:
                        raw_json = json.loads(raw_json_str)
                    except:
                        raw_json = {}
                    
                    recipe = {
                        'recipe_id': row.get('recipe_id'),
                        'recipe_title': row.get('recipe_title'),
                        'url': row.get('url'),
                        'img_url': row.get('img_url'),
                        'region': row.get('region'),
                        'sub_region': row.get('sub_region'),
                        'continent': row.get('continent'),
                        'source': row.get('source'),
                        'servings': row.get('servings'),
                        'calories': row.get('calories'),
                        'energy_kcal': row.get('energy_kcal'),
                        'carbohydrate_by_difference_g': row.get('carbohydrate_by_difference_g'),
                        'protein_g': row.get('protein_g'),
                        'total_lipid_fat_g': row.get('total_lipid_fat_g'),
                        'cook_time_min': row.get('cook_time_min'),
                        'prep_time_min': row.get('prep_time_min'),
                        'total_time_min': row.get('total_time_min'),
                        'processes': row.get('processes'),
                        'vegan': row.get('vegan'),
                        'pescetarian': row.get('pescetarian'),
                        'ovo_vegetarian': row.get('ovo_vegetarian'),
                        'lacto_vegetarian': row.get('lacto_vegetarian'),
                        'ovo_lacto_vegetarian': row.get('ovo_lacto_vegetarian'),
                        'utensils': row.get('utensils'),
                        'calorie_partition': row.get('calorie_partition'),
                        'ingredient_phrases': ingredient_phrases,
                        'ingredients_json': ingredients_json,
                        'raw_json': raw_json
                    }
                    break
    except Exception as e:
        print(f"Error loading recipe: {e}")
        flash('Error loading recipe details.', 'danger')
        return redirect(url_for('dashboard'))
    
    if not recipe:
        flash('Recipe not found.', 'danger')
        return redirect(url_for('dashboard'))
    
    return render_template('recipe_detail.html', recipe=recipe)

if __name__ == '__main__':
    # Configuration from environment variables or defaults
    import os
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

