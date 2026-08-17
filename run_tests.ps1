$Python = if (Test-Path ".\.venv\Scripts\python.exe") {
  ".\.venv\Scripts\python.exe"
} elseif (Test-Path ".\.venv\bin\python") {
  ".\.venv\bin\python"
} else {
  "python"
}

& $Python run_tests.py

if ($LASTEXITCODE -ne 0) {
  exit $LASTEXITCODE
}
