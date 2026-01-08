# 1. Define Seasons
$seasons = @(
    "2024-2025",
    "2023-2024",
    "2022-2023",
    "2021-2022",
    "2020-2021"
)

# 2. Define Base Path
$basePath = "c:\Users\Ryan\python\.vscode\fb_ai_bets\data"

# 3. Define Leagues (Using correct OddsPortal slugs)
$leagues = @(
    "saudi-professional-league",
    "france-ligue-1",
    "germany-bundesliga",
    "italy-serie-a",
    "spain-laliga"
)

# 4. Start Scraping Loop
foreach ($league in $leagues) {
    foreach ($season in $seasons) {
        $fileName = "${league}_${season}.csv"
        $currentFile = Join-Path -Path $basePath -ChildPath $fileName

        Write-Host "------------------------------------------------------"
        Write-Host "Scraping Season: $season" -ForegroundColor Cyan
        Write-Host "Target League: $league"
        Write-Host "Output File: $currentFile"

        # Run Python Scraper (Removed --headless to prevent 403 Forbidden)
        python -m uv run python src/main.py scrape_historic `
            --headless `
            --sport football `
            --leagues "$league" `
            --season "$season" `
            --format csv `
            --markets "1x2,over_under_2_5,asian_handicap_0,asian_handicap_-0_5,asian_handicap_+0_5" `
            --file_path "$currentFile" `
            --concurrency_tasks 5 `
            --max_pages 100 `
            --browser_user_agent "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            --target_bookmaker "bet365" `
        Write-Host "Season $season done. Sleeping for 30s..." -ForegroundColor Yellow
        Start-Sleep -Seconds 30
    }
}

Write-Host "All scraping tasks completed!" -ForegroundColor Green
/'
Write-Host "Starting file merger..." -ForegroundColor Yellow

# 5. Start Merging Loop
foreach ($league in $leagues) {
    Write-Host "------------------------------------------------------"
    Write-Host "Processing League: $league" -ForegroundColor Cyan

    # Find all CSV files for this league, excluding already merged files
    $files = Get-ChildItem -Path $basePath -Filter "$league*.csv" | 
             Where-Object { $_.Name -notlike "*combined.csv" -and $_.Name -notlike "*history.csv" } | 
             Sort-Object Name

    if ($files.Count -eq 0) {
        Write-Host "  [!] No data files found for this league. Skipping." -ForegroundColor Red
        continue
    }

    # Set output filename
    $outputFile = Join-Path -Path $basePath -ChildPath "${league}_history.csv"
    
    # Remove old merged file if exists
    if (Test-Path $outputFile) { Remove-Item $outputFile }

    $isFirstFile = $true
    
    # Merging Logic
    foreach ($file in $files) {
        if ($isFirstFile) {
            # First file: Keep header
            Get-Content $file.FullName -Encoding UTF8 | Set-Content $outputFile -Encoding UTF8
            $isFirstFile = $false
        } else {
            # Subsequent files: Skip header
            Get-Content $file.FullName -Encoding UTF8 | Select-Object -Skip 1 | Add-Content $outputFile -Encoding UTF8
        }
        Write-Host "  Merged: $($file.Name)"
    }

    Write-Host "  [OK] Successfully created: $outputFile" -ForegroundColor Green
}

Write-Host "------------------------------------------------------"
Write-Host "All operations completed successfully!" -ForegroundColor Yellow'/