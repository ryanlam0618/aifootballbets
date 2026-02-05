# 1. Define Links
$links = @(
     "https://www.oddsportal.com/football/germany/regionalliga-west/wiedenbruck-rodinghausen-djheAVI5/#1X2;2"
     )

# 2. Define File Paths
$basePath = "C:\Users\Ryan\python\.vscode\fb_ai_bets\data\archive"
$finalFile = Join-Path -Path $basePath -ChildPath "20260204_011810_odds.csv"

# 3. Ensure Directory Exists
if (-not (Test-Path $basePath)) { New-Item -ItemType Directory -Path $basePath | Out-Null }

# 4. Start Loop
for ($i = 0; $i -lt $links.Count; $i++) {
    $currentLink = $links[$i]

    Write-Host "------------------------------------------------------"
    Write-Host "Processing Task ($($i+1)/$($links.Count))..." -ForegroundColor Cyan
    Write-Host "Target: $currentLink"
    
    # Remove old temp file
    if (Test-Path $tempFile) { Remove-Item $tempFile }

    # Run Python Scraper
    # FIX: Combined markets into a SINGLE string
    python -m uv run python src/main.py scrape_upcoming `
        --sport football `
        --match_links "$currentLink" `
        --format csv `
        --markets "1x2" `
        --scrape_odds_history `
        --file_path "$tempFile" `
        --concurrency_tasks 5 `
        --target_bookmaker "1xBet" `
        --headless


    # 5. Merge Logic (Append)
    if (Test-Path $tempFile) {
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