param(
    [int]$N = 5,
    [string]$ImageDir = "C:\Users\Cyrus\Downloads\New folder (33)\New folder (32)\New folder\Main2\md\drive\Answer papers-20260425T192317Z-3-001\Answer papers",
    [int]$Port = 8111
)

$ErrorActionPreference = "Stop"

$images = @(
    "IMG_1225.HEIC",
    "IMG_1226.HEIC",
    "IMG_1227.HEIC",
    "IMG_1228.HEIC",
    "IMG_1229.HEIC"
)

Write-Host "=== Task 9: Multi-Paper Sequential Grading Benchmark ==="
Write-Host "N: $N | Port: $Port"
Write-Host "Image directory: $ImageDir"
Write-Host ""

$results = @()
$totalStart = Get-Date

for ($i = 0; $i -lt $N; $i++) {
    $imgName = $images[$i]
    $imgPath = Join-Path $ImageDir $imgName
    $idx = $i + 1

    if (-not (Test-Path $imgPath)) {
        Write-Host "[$idx/$N] SKIP: $imgPath not found"
        $results += [PSCustomObject]@{
            Index     = $idx
            Image     = $imgName
            Status    = "SKIP"
            HttpCode  = 0
            Seconds   = 0
            ValidJSON = $false
            Message   = "File not found"
        }
        continue
    }

    Write-Host "[$idx/$N] Grading $imgName ..." -NoNewline
    $start = Get-Date

    try {
        $response = curl.exe -s -o "$env:TEMP\bench_$idx.json" -w "%{http_code}" `
            -X POST "http://localhost:$Port/grade" `
            -F "file=@$imgPath" `
            --max-time 600

        $elapsed = ((Get-Date) - $start).TotalSeconds
        $jsonFile = "$env:TEMP\bench_$idx.json"
        $jsonContent = Get-Content $jsonFile -Raw
        $valid = $false
        $msg = ""

        try {
            $parsed = $jsonContent | ConvertFrom-Json
            $valid = $true
            $msg = "marks=$($parsed.marks) confidence=$($parsed.confidence)"
        } catch {
            $msg = "Invalid JSON: $($jsonContent.Substring(0, [Math]::Min(100, $jsonContent.Length)))"
        }

        Write-Host " -> HTTP $response | ${elapsed}s | $msg"
        $results += [PSCustomObject]@{
            Index     = $idx
            Image     = $imgName
            Status    = "OK"
            HttpCode  = [int]$response
            Seconds   = [Math]::Round($elapsed, 2)
            ValidJSON = $valid
            Message   = $msg
        }
    } catch {
        $elapsed = ((Get-Date) - $start).TotalSeconds
        Write-Host " -> ERROR: $($_.Exception.Message) | ${elapsed}s"
        $results += [PSCustomObject]@{
            Index     = $idx
            Image     = $imgName
            Status    = "ERROR"
            HttpCode  = 0
            Seconds   = [Math]::Round($elapsed, 2)
            ValidJSON = $false
            Message   = $_.Exception.Message
        }
    }
}

$totalElapsed = ((Get-Date) - $totalStart).TotalSeconds

Write-Host ""
Write-Host "=== Benchmark Results ==="
Write-Host "Total time: $([Math]::Round($totalElapsed, 1))s"

$successes = $results | Where-Object { $_.Status -eq "OK" }
$errors = $results | Where-Object { $_.Status -ne "OK" }

$allHttp200 = ($successes | Where-Object { $_.HttpCode -ne 200 }).Count -eq 0
$allValid = ($successes | Where-Object { $_.ValidJSON -eq $false }).Count -eq 0

$avgTime = 0
if ($successes.Count -gt 0) {
    $avgTime = ($successes | Measure-Object -Property Seconds -Average).Average
}

Write-Host "Papers graded: $($successes.Count)/$N"
Write-Host "All HTTP 200: $allHttp200"
Write-Host "All valid JSON: $allValid"
Write-Host "Avg time per paper: $([Math]::Round($avgTime, 1))s"

Write-Host ""
Write-Host "=== Detail ==="
$results | Format-Table Index, Image, Status, HttpCode, Seconds, ValidJSON, Message -AutoSize

Write-Host ""
Write-Host "=== ollama ps ==="
ollama ps

Write-Host ""
Write-Host "=== Verdict ==="
if ($successes.Count -eq $N -and $allHttp200 -and $allValid) {
    Write-Host "PASS: All $N papers graded, all HTTP 200, all valid JSON"
    Write-Host "Avg processing time: $([Math]::Round($avgTime, 1))s per paper"
} else {
    Write-Host "FAIL: $($errors.Count) failures, $($N - $successes.Count - $errors.Count) skipped"
    $results | Where-Object { $_.Status -ne "OK" } | Format-Table Image, Status, Message -AutoSize
}

Write-Host ""
Write-Host "PROGRESS.md entry:"
Write-Host "---"
Write-Host "Task 9: Multi-Paper Sequential Grading Benchmark - DONE"
Write-Host ""
Write-Host "Submitted $N consecutive student answer sheets (IMG_1225-1229.HEIC) to POST /grade."
Write-Host "Results:"
$results | ForEach-Object { Write-Host "  [$($_.Index))/$N] $($_.Image): HTTP $($_.HttpCode) | $($_.Seconds)s | valid=$($_.ValidJSON) | $($_.Message)" }
Write-Host ""
Write-Host "Total time: $([Math]::Round($totalElapsed, 1))s"
Write-Host "All HTTP 200: $allHttp200"
Write-Host "All valid JSON: $allValid"
Write-Host "Avg time per paper: $([Math]::Round($avgTime, 1))s"
Write-Host "---"
