# AutoGrader — Database & Artifacts Reset Script (PowerShell)
Write-Host "Clearing AutoGrader SQLite databases and artifacts..." -ForegroundColor Yellow

$PathsToDelete = @(
    "backend/data/autograder.db",
    "backend/data/test_autograder.db",
    "data/autograder.db",
    "data/test_autograder.db"
)

foreach ($file in $PathsToDelete) {
    if (Test-Path $file) {
        Remove-Item $file -Force
        Write-Host "  Deleted: $file" -ForegroundColor Green
    }
}

$ArtifactDirs = @(
    "backend/data/artifacts",
    "backend/data/test-artifacts",
    "data/artifacts",
    "data/test-artifacts"
)

foreach ($dir in $ArtifactDirs) {
    if (Test-Path $dir) {
        Remove-Item "$dir/*" -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "  Cleaned: $dir" -ForegroundColor Green
    }
}

Write-Host "AutoGrader database and artifacts have been completely cleared!" -ForegroundColor Cyan
Write-Host "When you run or restart the server, clean empty tables will be initialized automatically." -ForegroundColor Gray

