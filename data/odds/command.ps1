# 1. Define Links
$links = @(
     "https://www.oddsportal.com/football/england/premier-league/leeds-nottingham-raKBgwWA/"
     )

# 2. Define File Paths
$basePath = "C:\Users\Ryan\python\.vscode\fb_ai_bets\data\archive"
$finalFile = Join-Path -Path $basePath -ChildPath "odds_latest.csv"
$tempFile = Join-Path -Path $basePath -ChildPath "temp_odds.csv"

# 3. Ensure Directory Exists
if (-not (Test-Path $basePath)) { New-Item -ItemType Directory -Path $basePath | Out-Null }

# 4. Start Loop
for ($i = 0; $i -lt $links.Count; $i++) {
    $currentLink = $links[$i]

    Write-Host "------------------------------------------------------"
    Write-Host "Processing Task ($($i+1)/$($links.Count))..." -ForegroundColor Cyan
    Write-Host "Target: $currentLink"
    
    # Remove old temp file
    if ($tempFile -and (Test-Path $tempFile)) { Remove-Item $tempFile -ErrorAction SilentlyContinue }

    # Run Python Scraper (check if OddsHarvester exists)
    $scraperPath = "C:\Users\Ryan\python\.vscode\fb_ai_bets\OddsHarvester"
    $scraperVenv = "C:\Users\Ryan\python\.vscode\fb_ai_bets\OddsHarvester\.venv\Scripts\python.exe"
    $scraperSrcMain = "C:\Users\Ryan\python\.vscode\fb_ai_bets\OddsHarvester\src\main.py"
    if (Test-Path $scraperSrcMain) {
        # FIX: Explicitly set PYTHONPATH to OddsHarvester src, excluding fb_ai_bets/src
        $venvPython = if (Test-Path $scraperVenv) { $scraperVenv } else { "python" }
        $env:PYTHONPATH = $scraperPath  # Only OddsHarvester, not parent
        $env:PYTHONUNBUFFERED = "1"
        & $venvPython -m src.main scrape_upcoming `
            --sport football `
            --match_links "$currentLink" `
            --format csv `
            --markets "1x2" `
            --scrape_odds_history `
            --file_path "$tempFile" `
            --concurrency_tasks 5 `
            --target_bookmaker "1xBet" `
            --headless
        Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
    } else {
        Write-Host " [Warning] Scraper not found at: $scraperSrcMain" -ForegroundColor Yellow
        Write-Host " [Info] Trying alternative scraper..." -ForegroundColor Cyan
        # Try with the data module instead
        python "C:\Users\Ryan\python\.vscode\fb_ai_bets\scripts\TakeHistoryData.py" 2>$null
    }


    # 5. Merge Logic (Append)
    if ($tempFile -and (Test-Path $tempFile)) {
        if (-not (Test-Path $finalFile)) {
            # Case 1: Final file doesn't exist, simply move temp file
            Move-Item -Path $tempFile -Destination $finalFile
            Write-Host " [OK] Created new file: $finalFile" -ForegroundColor Green
        } else {
            # Case 2: Final file exists, append content (skipping header)
            Get-Content $tempFile -Encoding UTF8 | Select-Object -Skip 1 | Add-Content $finalFile -Encoding UTF8
            Remove-Item $tempFile
            Write-Host " [OK] Data appended to: $finalFile" -ForegroundColor Green
        }
    } else {
        Write-Host " [Error] Failed to scrape data. No temp file created." -ForegroundColor Red
    }

    Write-Host "Sleeping for 10 seconds..." -ForegroundColor Yellow
    Start-Sleep -Seconds 10
}

Write-Host "------------------------------------------------------"
Write-Host "All tasks completed! Saved to: $finalFile" -ForegroundColor Green