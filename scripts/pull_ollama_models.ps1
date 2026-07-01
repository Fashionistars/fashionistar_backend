# scripts/pull_ollama_models.ps1
# PowerShell script to ensure Ollama is installed, running, and pulls the required models.

$ErrorActionPreference = "Stop"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "   FASHIONISTAR AI: Ollama Model Provisioning Tool        " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Check if Ollama command is available
$OllamaPath = Get-Command ollama -ErrorAction SilentlyContinue
if (-not $OllamaPath) {
    Write-Host "[!] Ollama is not installed or not in system PATH." -ForegroundColor Yellow
    Write-Host "    Please download and install Ollama from: https://ollama.com/download" -ForegroundColor Green
    Write-Host "    After installation, restart your terminal and run this script again." -ForegroundColor Green
    Exit 1
}

Write-Host "[+] Ollama found at: $($OllamaPath.Source)" -ForegroundColor Green

# 2. Check if Ollama service/host is running
$OllamaHost = "http://localhost:11434"
Write-Host "[+] Checking if Ollama server is running at $OllamaHost..." -ForegroundColor Cyan
try {
    $Response = Invoke-RestMethod -Uri "$OllamaHost/api/tags" -Method Get -TimeoutSec 5
    Write-Host "[+] Ollama server is online and running." -ForegroundColor Green
} catch {
    Write-Host "[!] Ollama server is not running. Starting Ollama app..." -ForegroundColor Yellow
    
    # Try starting Ollama app on Windows
    $LocalAppData = [System.Environment]::GetFolderPath('LocalApplicationData')
    $OllamaAppPath = "$LocalAppData\Programs\Ollama\Ollama.exe"
    if (Test-Path $OllamaAppPath) {
        Start-Process -FilePath $OllamaAppPath
        Write-Host "[+] Starting Ollama.exe. Waiting 5 seconds..." -ForegroundColor Cyan
        Start-Sleep -Seconds 5
    } else {
        Write-Host "[!] Could not find Ollama.exe program to auto-start. Please launch Ollama manually." -ForegroundColor Red
        Exit 1
    }
}

# 3. Pull required models
Write-Host "[+] Pulling 'llama3.2:3b' (Sizing & text reasoning model)..." -ForegroundColor Cyan
& ollama pull llama3.2:3b

Write-Host "[+] Pulling 'nomic-embed-text' (Text similarity embedding model)..." -ForegroundColor Cyan
& ollama pull nomic-embed-text

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "[+] Ollama models pulled successfully!" -ForegroundColor Green
Write-Host "    - llama3.2:3b" -ForegroundColor Green
Write-Host "    - nomic-embed-text" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Cyan
