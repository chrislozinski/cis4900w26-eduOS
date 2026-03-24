$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$outputDir = Join-Path $scriptDir "..\..\src\debian-base1\widgets\makecode\makecode-static"

Write-Host "=== Building MakeCode static package inside Docker ===" -ForegroundColor Cyan

# Build the builder image
Write-Host "`n[1/4] Building Docker image (this takes 10-20 minutes)..." -ForegroundColor Yellow
docker build -t makecode-builder "$scriptDir"

# Create a temp container
Write-Host "`n[2/4] Extracting static files..." -ForegroundColor Yellow
docker create --name mc-extract makecode-builder | Out-Null

# Remove old output if it exists
if (Test-Path $outputDir) {
    Remove-Item -Recurse -Force $outputDir
}
New-Item -ItemType Directory -Path $outputDir -Force | Out-Null

# cloned directly into /build/pxt-microbit
docker cp mc-extract:/build/pxt-arcade/built/packaged/. "$outputDir"

# Clean up Docker artifacts
Write-Host "`n[3/4] Cleaning up Docker artifacts..." -ForegroundColor Yellow
docker rm mc-extract | Out-Null
docker rmi makecode-builder | Out-Null

# Verify
Write-Host "`n[4/4] Verifying output..." -ForegroundColor Yellow
$fileCount = (Get-ChildItem -Recurse $outputDir | Measure-Object).Count
$sizeMB = [math]::Round((Get-ChildItem -Recurse $outputDir | Measure-Object -Property Length -Sum).Sum / 1MB, 1)

if (Test-Path (Join-Path $outputDir "index.html")) {
    Write-Host "`nSUCCESS: MakeCode static files extracted" -ForegroundColor Green
    Write-Host "  Location: $outputDir"
    Write-Host "  Files:    $fileCount"
    Write-Host "  Size:     ${sizeMB}MB"
    Write-Host "`nNext steps:" -ForegroundColor Cyan
    Write-Host "  1. Rebuild your main image: docker-compose up -d --build"
    Write-Host "  2. MakeCode will be available in the sidebar"
} else {
    Write-Host "`nFAILED: index.html not found in output" -ForegroundColor Red
    exit 1
}