$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
$dir = "c:\Users\wumff\Desktop\一些文档\python文件\test"
$port = 3000
$o = "$env:TEMP\fo_out.log"
$e = "$env:TEMP\fo_err.log"

function Start-Server {
    Write-Host "[$(Get-Date -Format HH:mm:ss)] 启动服务..."
    Start-Process -FilePath "node" -ArgumentList "server.js" -WorkingDirectory $dir -RedirectStandardOutput $o -RedirectStandardError $e -WindowStyle Hidden
}

function Test-Server {
    try {
        Invoke-WebRequest -Uri "http://localhost:$port/api/ping" -UseBasicParsing -TimeoutSec 3 | Out-Null
        return $true
    } catch { return $false }
}

# 初始启动
Get-Process node -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep 1
Start-Server
Start-Sleep 4

# 守护循环
while ($true) {
    if (-not (Test-Server)) {
        Write-Host "[$(Get-Date -Format HH:mm:ss)] 服務掛了，重啟中..."
        Get-Process node -ErrorAction SilentlyContinue | Stop-Process -Force
        Start-Sleep 2
        Start-Server
        Start-Sleep 4
    }
    Start-Sleep 15
}
