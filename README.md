# DNA2Diet - Personalized Nutrition Based on Genetics

A comprehensive web application that analyzes your genome file and provides personalized nutrition recommendations based on your genetic profile.

## Features

- **User Authentication**: Secure registration and login system
- **Profile Management**: Store demographic and health information (height, weight, age, medical history, etc.)
- **Genome Analysis**: Upload genome files and process them through a multi-step pipeline
- **Disease Risk Assessment**: Identify potential disease risks based on SNP analysis
- **Ingredient Recommendations**: Get personalized ingredient recommendations (prefer/avoid) based on your genetic profile
- **Healthcare-Style UI**: Modern, responsive interface designed for healthcare applications
- **User-Specific File Organization**: Each user's data is stored in separate folders

## Technology Stack

- **Backend**: Flask (Python web framework)
- **Database**: MySQL (user: root, password: 1234)
- **Frontend**: HTML5, CSS3, Bootstrap 5
- **Data Processing**: Pandas, NumPy
- **NLP**: spaCy, scispaCy
- **API Integration**: MeSH API for disease mapping

## Installation

### Prerequisites

- Python 3.8 or higher
- MySQL Server
- pip (Python package manager)

### Setup Steps

1. **Clone or download the project**
   ```bash
   cd test
   ```

2. **Install Python dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Install scispaCy model** (optional - can skip if you encounter build errors)
   ```bash
   pip install https://s3-us-west-2.amazonaws.com/ai2-s2-scispacy/releases/v0.5.3/en_core_sci_sm-0.5.3.tar.gz
   ```
   **Note:** 
   - On Windows, this requires Microsoft Visual C++ Build Tools. If installation fails, you can skip this step.
   - The application works perfectly without this model - it will just use direct MeSH API lookups instead of NLP-enhanced matching.

4. **Set up MySQL database**
   ```bash
   mysql -u root -p1234 < database/schema.sql
   ```
   Or on Windows PowerShell:
   ```powershell
   cmd /c "mysql -u root -p1234 < database/schema.sql"
   ```

## Running the Application

### Quick Start (Easiest Way)

You can run the application directly using any of these methods:

#### Method 1: Using the launcher script (Recommended)
```bash
# Windows
run.bat

# Linux/Mac
python3 run.py
# or
chmod +x run.sh && ./run.sh
```

#### Method 2: Direct Python command
```bash
# Simple - just run app.py directly
python app.py

# Or use the launcher
python run.py
```

#### Method 3: Using Flask CLI
```bash
# Set Flask app
export FLASK_APP=app.py  # Linux/Mac
set FLASK_APP=app.py     # Windows

# Run Flask
flask run
```

### Configuration Options

You can customize the server settings using environment variables:

```bash
# Linux/Mac
export FLASK_HOST=0.0.0.0
export FLASK_PORT=5000
export FLASK_DEBUG=True

# Windows
set FLASK_HOST=0.0.0.0
set FLASK_PORT=5000
set FLASK_DEBUG=True

python app.py
```

### Access the Application

Once started, open your browser and navigate to:
- **Local**: http://localhost:5000
- **Network**: http://your-ip-address:5000

The application will display the login/registration page.

### Additional Configuration

1. **Ensure required files are in place:**
   - `gwas.tsv` file in the root directory
   - `prevalences.json` file in the root directory (optional)
   - Update API URL in `processing/mesh_processor.py` if needed

2. **For recipe recommendations:**
   - Ensure `recipe_recommendations.csv` exists (or run `recipe_extraction.py` separately to populate it)

## Project Structure

```
.
├── app.py                          # Main Flask application
├── requirements.txt                # Python dependencies
├── database/
│   └── schema.sql                  # MySQL database schema
├── processing/                     # Processing modules
│   ├── __init__.py
│   ├── genome_processor.py        # Step 1: Process genome file
│   ├── disease_estimator.py       # Step 2: Estimate diseases
│   ├── disease_finalizer.py       # Step 3: Finalize disease ranking
│   ├── mesh_processor.py          # Step 4: Process MESH data
│   └── ingredient_extractor.py    # Step 5: Extract ingredients
├── templates/                      # HTML templates
│   ├── base.html
│   ├── login.html
│   ├── register.html
│   ├── dashboard.html
│   ├── profile.html
│   ├── upload.html
│   └── results.html
└── user_data/                      # User-specific data folders (auto-created)
```

## Processing Pipeline

1. **Genome Processing** (`genome_processor.py`)
   - Input: Genome file (.txt)
   - Process: Match SNPs with GWAS data, filter nutritional traits
   - Output: `nutritional_snp_final.csv`

2. **Disease Estimation** (`disease_estimator.py`)
   - Input: `nutritional_snp_final.csv`
   - Process: Calculate PRS, percentiles, absolute probabilities
   - Output: `disease_candidates.csv`

3. **Disease Finalization** (`disease_finalizer.py`)
   - Input: `disease_candidates.csv` + `nutritional_snp_final.csv`
   - Process: Filter high-risk diseases, rank by risk score
   - Output: `selected_diseases_ranked.csv` and `.json`

4. **MESH Processing** (`mesh_processor.py`)
   - Input: `selected_diseases_ranked.json`
   - Process: Fetch disease-ingredient associations from API
   - Output: `disease.json`

5. **Ingredient Extraction** (`ingredient_extractor.py`)
   - Input: `disease.json`
   - Process: Aggregate ingredient recommendations (prefer/avoid)
   - Output: `ingredient_recommendations.json` and `.csv`

## Usage

1. **Register/Login**: Create an account or login
2. **Complete Profile**: Add your demographic and health information
3. **Upload Genome**: Upload your genome file (.txt or .csv format)
4. **Wait for Processing**: The analysis runs in the background (5-15 minutes)
5. **View Results**: Check your personalized disease risks and ingredient recommendations

## File Format Requirements

Genome files should be tab-separated with the following columns:
- `rsid`: SNP identifier
- `chromosome`: Chromosome number
- `position`: Position on chromosome
- `genotype`: Genotype (e.g., AA, AG, GG)

Comments starting with `#` will be ignored.

## Database Configuration

Default MySQL configuration:
- Host: localhost
- User: root
- Password: 1234
- Database: dna2diet

To change these settings, edit `app.py`:
```python
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = '1234'
app.config['MYSQL_DB'] = 'dna2diet'
```

## Notes

- All user files are stored in `user_data/{user_id}/` folders
- Processing happens asynchronously in background threads
- The application requires the GWAS file (`gwas.tsv`) to be present
- MESH API URL can be configured in `processing/mesh_processor.py`
- This tool is for informational purposes only - consult healthcare professionals for medical advice

## Troubleshooting

1. **Database Connection Error**: Ensure MySQL is running and credentials are correct
2. **Missing spaCy Model**: Run `python -m spacy download en_core_sci_sm`
3. **Processing Fails**: Check that `gwas.tsv` exists in the root directory
4. **API Errors**: Verify MESH API URL is accessible in `processing/mesh_processor.py`

## License

This project is for research and educational purposes.

