# DNA2Diet Server Startup Script for PowerShell

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Starting DNA2Diet Web Application" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check if MySQL is running
Write-Host "Checking MySQL connection..." -ForegroundColor Yellow
try {
    $result = mysql -u root -p1234 -e "SELECT 1;" 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ MySQL connection OK" -ForegroundColor Green
    } else {
        Write-Host "❌ MySQL connection failed" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "❌ MySQL not found in PATH" -ForegroundColor Red
    exit 1
}

# Check required files
Write-Host "Checking required files..." -ForegroundColor Yellow
if (Test-Path "gwas.tsv") {
    Write-Host "✅ gwas.tsv found" -ForegroundColor Green
} else {
    Write-Host "❌ gwas.tsv not found!" -ForegroundColor Red
    exit 1
}

# Start the application
Write-Host ""
Write-Host "Starting Flask application..." -ForegroundColor Yellow
Write-Host "Application will be available at: http://localhost:5000" -ForegroundColor Cyan
Write-Host "Press Ctrl+C to stop the server" -ForegroundColor Yellow
Write-Host ""

python app.py

