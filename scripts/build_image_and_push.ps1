
Write-Output "[1/2] Building docker image..."
docker build -t h4ckerxx44/pornhub_archiver:latest .
Write-Output "[1/2] Built docker image."


Write-Output "[2/2] Pushing docker image..."
docker push h4ckerxx44/pornhub_archiver:latest
Write-Output "[2/2] Built docker image."

Write-Output "Done."
