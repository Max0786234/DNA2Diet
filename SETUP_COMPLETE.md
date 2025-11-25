# ✅ DNA2Diet Application Setup Complete!

## Setup Summary

### ✅ Completed Steps:

1. **Database Setup**
   - ✅ MySQL database `dna2diet` created
   - ✅ All tables created (users, user_profiles, analyses)
   - ✅ Database connection configured

2. **Dependencies Installed**
   - ✅ Flask and Flask-MySQLdb
   - ✅ Pandas, NumPy
   - ✅ Thefuzz, python-Levenshtein
   - ✅ Requests, aiohttp
   - ✅ tqdm, scispacy
   - ✅ All required packages

3. **Files Verified**
   - ✅ gwas.tsv found
   - ✅ All Python modules created
   - ✅ Templates created
   - ✅ Processing modules ready

4. **Application Status**
   - ✅ Application is running on port 5000
   - ✅ Server is responding to requests

## 🚀 How to Use

### Start the Application (if not already running)

```powershell
# Option 1: Direct start
python app.py

# Option 2: Use the startup script
.\start_server.ps1
```

### Access the Application

Open your web browser and navigate to:
```
http://localhost:5000
```

### First Steps

1. **Register** a new account
   - Click "Register" on the login page
   - Fill in your details (First Name, Last Name, Email, Password)

2. **Complete Your Profile**
   - After logging in, go to "Profile"
   - Add demographic information (height, weight, age, etc.)
   - Add medical history, allergies, medications (optional)

3. **Upload Your Genome File**
   - Go to "Upload Genome"
   - Select your genome file (.txt or .csv format)
   - Wait for processing to complete (5-15 minutes)

4. **View Results**
   - Once processing is complete, view your results
   - See disease risk analysis
   - Get ingredient recommendations (prefer/avoid)

## 📋 File Structure

```
.
├── app.py                      # Main Flask application
├── database/
│   └── schema.sql              # MySQL database schema
├── processing/                 # Processing modules
│   ├── genome_processor.py    # Step 1: Process genome
│   ├── disease_estimator.py   # Step 2: Estimate diseases
│   ├── disease_finalizer.py   # Step 3: Finalize diseases
│   ├── mesh_processor.py      # Step 4: Process MESH
│   └── ingredient_extractor.py # Step 5: Extract ingredients
├── templates/                  # HTML templates
├── user_data/                  # User-specific data (auto-created)
├── gwas.tsv                    # GWAS data file (required)
└── requirements.txt            # Python dependencies
```

## 🔧 Configuration

### MySQL Database
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

### MESH API Configuration
If your MESH API URL is different, edit `processing/mesh_processor.py`:
```python
BASE_URL = "http://your-api-url:port/api/disease/"
```

## 📝 Notes

- The application processes files in the background
- Each user's data is stored in `user_data/{user_id}/`
- Processing typically takes 5-15 minutes depending on file size
- The scispacy model is optional - the app works without it
- All processing happens asynchronously in background threads

## 🆘 Troubleshooting

### Application won't start
- Check if MySQL is running: `mysql -u root -p1234 -e "SELECT 1;"`
- Verify port 5000 is not in use by another application
- Check that `gwas.tsv` exists in the root directory

### Database connection errors
- Ensure MySQL service is running
- Verify credentials in `app.py`
- Check that database exists: `mysql -u root -p1234 -e "SHOW DATABASES;"`

### Processing errors
- Check that `gwas.tsv` file exists and is readable
- Verify file format matches expected structure
- Check logs in the terminal where the app is running

## ✨ Features

- ✅ User authentication (register/login)
- ✅ Profile management (demographics, health data)
- ✅ Genome file upload
- ✅ Background processing pipeline
- ✅ Disease risk analysis
- ✅ Ingredient recommendations
- ✅ Healthcare-style UI
- ✅ User-specific file organization

## 🎉 You're All Set!

The application is ready to use. Start uploading genome files and getting personalized nutrition recommendations!

