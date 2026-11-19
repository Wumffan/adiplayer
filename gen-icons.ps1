Add-Type -AssemblyName System.Drawing
$outDir = "c:\Users\wumff\Desktop\一些文档\python文件\test\public"
$tmpDir = "$env:TEMP\folia-icons"
if (-not (Test-Path $tmpDir)) { New-Item $tmpDir -ItemType Directory | Out-Null }

function New-Icon($size, $name) {
    $bmp = New-Object System.Drawing.Bitmap($size, $size)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $g.Clear([System.Drawing.Color]::FromArgb(15,15,20))
    $cx = [int]($size/2)
    $cy = [int]($size/2)
    $r = [int]($size*0.3)
    $red = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(224,80,80))
    $g.FillEllipse($red, $cx-$r, $cy-$r, $r*2, $r*2)
    $dotR = [int]($size*0.03)
    $white = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(255,255,255))
    $g.FillEllipse($white, $cx-$dotR, $cy-$dotR, $dotR*2, $dotR*2)
    $pen = New-Object System.Drawing.Pen($white, [Math]::Max(2, [int]($size*0.025)))
    $pen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
    $g.DrawLine($pen, $cx, [int]($cy-$r*0.7), $cx, [int]($cy-$r*0.2))
    $tmpPath = Join-Path $tmpDir $name
    $bmp.Save($tmpPath, [System.Drawing.Imaging.ImageFormat]::Png)
    $g.Dispose()
    $bmp.Dispose()
    $dst = Join-Path $outDir $name
    Copy-Item $tmpPath $dst -Force
    Write-Host "OK: $name ($size x $size)"
}

New-Icon 192 "icon-192.png"
New-Icon 512 "icon-512.png"
Write-Host ""
Write-Host "Generated:"
Get-ChildItem "$outDir\icon-*.png" | Select-Object Name, Length
