# PowerShell Script: Setup Portability Test Environment
# This automates all the steps to test browser data portability

Write-Host "`n" -NoNewline
Write-Host "=" * 80 -ForegroundColor Cyan
Write-Host "PORTABILITY TEST - Automated Setup" -ForegroundColor Cyan
Write-Host "=" * 80 -ForegroundColor Cyan

Write-Host "`n📋 This script will:"
Write-Host "   1. Create virtual environment (test_venv)"
Write-Host "   2. Install Playwright"
Write-Host "   3. Install Chromium browser"
Write-Host "   4. Copy browser_data/1 to test location"
Write-Host "   5. Run portability test"

Write-Host "`n⏳ This will take a few minutes (Chromium download ~350MB)..."
$continue = Read-Host "`nContinue? (yes/no)"

if ($continue -ne "yes") {
    Write-Host "`n❌ Cancelled by user"
    exit
}

# Step 1: Create venv
Write-Host "`n" -NoNewline
Write-Host "=" * 80 -ForegroundColor Yellow
Write-Host "STEP 1: Creating Virtual Environment" -ForegroundColor Yellow
Write-Host "=" * 80 -ForegroundColor Yellow

if (Test-Path "test_venv") {
    Write-Host "`n⚠ test_venv already exists. Removing..."
    Remove-Item -Recurse -Force test_venv
}

Write-Host "`n🔧 Creating venv..."
python -m venv test_venv

if ($LASTEXITCODE -ne 0) {
    Write-Host "`n❌ Failed to create venv!" -ForegroundColor Red
    exit 1
}

Write-Host "✅ Virtual environment created!" -ForegroundColor Green

# Step 2: Activate venv and install dependencies
Write-Host "`n" -NoNewline
Write-Host "=" * 80 -ForegroundColor Yellow
Write-Host "STEP 2: Installing Dependencies" -ForegroundColor Yellow
Write-Host "=" * 80 -ForegroundColor Yellow

Write-Host "`n🔧 Activating venv..."
& .\test_venv\Scripts\Activate.ps1

Write-Host "`n📦 Installing Playwright..."
pip install playwright

if ($LASTEXITCODE -ne 0) {
    Write-Host "`n❌ Failed to install Playwright!" -ForegroundColor Red
    deactivate
    exit 1
}

Write-Host "`n✅ Playwright installed!" -ForegroundColor Green

# Step 3: Install Chromium
Write-Host "`n" -NoNewline
Write-Host "=" * 80 -ForegroundColor Yellow
Write-Host "STEP 3: Installing Chromium Browser" -ForegroundColor Yellow
Write-Host "=" * 80 -ForegroundColor Yellow

Write-Host "`n🌐 Downloading Chromium (~350MB, this may take a while)..."
playwright install chromium

if ($LASTEXITCODE -ne 0) {
    Write-Host "`n❌ Failed to install Chromium!" -ForegroundColor Red
    deactivate
    exit 1
}

Write-Host "`n✅ Chromium installed!" -ForegroundColor Green

# Step 4: Copy browser data
Write-Host "`n" -NoNewline
Write-Host "=" * 80 -ForegroundColor Yellow
Write-Host "STEP 4: Copying Browser Data" -ForegroundColor Yellow
Write-Host "=" * 80 -ForegroundColor Yellow

$sourcePath = "browser_data\1"
$testPath = "test_portability"
$destPath = "$testPath\browser_data_copy"

if (-not (Test-Path $sourcePath)) {
    Write-Host "`n❌ No browser data found at $sourcePath" -ForegroundColor Red
    Write-Host "   Run setup_accounts.py first to create account 1!" -ForegroundColor Yellow
    deactivate
    exit 1
}

Write-Host "`n✅ Found browser data at: $sourcePath" -ForegroundColor Green

# Create test directory
if (-not (Test-Path $testPath)) {
    New-Item -ItemType Directory -Path $testPath -Force | Out-Null
}

# Copy browser data
if (Test-Path $destPath) {
    Write-Host "`n⚠ Removing old test data..."
    Remove-Item -Recurse -Force $destPath
}

Write-Host "`n📋 Copying browser data..."
Copy-Item -Recurse -Force $sourcePath $destPath

Write-Host "✅ Browser data copied to: $destPath" -ForegroundColor Green

# Step 5: Run test
Write-Host "`n" -NoNewline
Write-Host "=" * 80 -ForegroundColor Yellow
Write-Host "STEP 5: Running Portability Test" -ForegroundColor Yellow
Write-Host "=" * 80 -ForegroundColor Yellow

Write-Host "`n🚀 Launching test..."
Write-Host "`n📋 Watch for:"
Write-Host "   ✅ Gmail inbox (logged in) = PORTABLE!"
Write-Host "   ❌ Login page = NOT portable (browser-specific)"
Write-Host ""

python test_portability.py

# Cleanup prompt
Write-Host "`n" -NoNewline
Write-Host "=" * 80 -ForegroundColor Cyan
Write-Host "TEST COMPLETE" -ForegroundColor Cyan
Write-Host "=" * 80 -ForegroundColor Cyan

Write-Host "`n🧹 Clean up test files?"
Write-Host "   This will remove:"
Write-Host "   - test_venv/ (virtual environment)"
Write-Host "   - test_portability/ (copied browser data)"

$cleanup = Read-Host "`nClean up? (yes/no)"

if ($cleanup -eq "yes") {
    Write-Host "`n🧹 Cleaning up..."
    
    # Deactivate venv first
    deactivate
    
    if (Test-Path "test_venv") {
        Remove-Item -Recurse -Force test_venv
        Write-Host "✅ Removed test_venv/" -ForegroundColor Green
    }
    
    if (Test-Path "test_portability") {
        Remove-Item -Recurse -Force test_portability
        Write-Host "✅ Removed test_portability/" -ForegroundColor Green
    }
    
    Write-Host "`n✅ Cleanup complete!" -ForegroundColor Green
} else {
    Write-Host "`n📝 Test files kept. To clean up manually:"
    Write-Host "   Remove-Item -Recurse -Force test_venv"
    Write-Host "   Remove-Item -Recurse -Force test_portability"
}

Write-Host ""
