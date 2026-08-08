#requires -Version 5.1
<#
.SYNOPSIS
  本地 Windows OCR 图片文字提取（中文优先）
.DESCRIPTION
  基于 Windows 内置 OCR 引擎（zh-Hans-CN）识别图片中的文字，
  供不支持图片输入的模型（如 DeepSeek）读取用户截图。
  支持格式：png / jpg / jpeg / bmp / gif（首帧）/ webp。
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts/ocr_image.ps1 "C:\path\截图.png"
  powershell -ExecutionPolicy Bypass -File scripts/ocr_image.ps1 a.png b.jpg -Json
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory = $true, Position = 0, ValueFromRemainingArguments = $true)]
  [string[]]$ImagePath,
  [switch]$Json
)

$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

Add-Type -AssemblyName System.Runtime.WindowsRuntime

# WinRT IAsyncOperation -> .NET Task 的 await 辅助函数
$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() |
  Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
if ($null -eq $asTaskGeneric) { throw '无法初始化 WinRT AsTask 辅助函数' }

function Await-WinRt {
  param($WinRtTask, $ResultType)
  $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
  $netTask = $asTask.Invoke($null, @($WinRtTask))
  $null = $netTask.Wait(-1)
  $netTask.Result
}

# 加载 WinRT 类型
[Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime] | Out-Null
[Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime] | Out-Null
[Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType = WindowsRuntime] | Out-Null
[Windows.Globalization.Language, Windows.Globalization, ContentType = WindowsRuntime] | Out-Null

# 中文优先，其次用户配置文件语言
$engine = $null
try {
  $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new('zh-Hans-CN'))
} catch { }
if ($null -eq $engine) { $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages() }
if ($null -eq $engine) { throw '系统没有可用的 OCR 识别语言' }

$results = @()
foreach ($raw in $ImagePath) {
  $item = [ordered]@{ path = $raw; ok = $false; text = ''; error = '' }
  try {
    if (-not (Test-Path -LiteralPath $raw)) { throw "文件不存在: $raw" }
    $abs = (Resolve-Path -LiteralPath $raw).Path
    $file = Await-WinRt ([Windows.Storage.StorageFile]::GetFileFromPathAsync($abs)) ([Windows.Storage.StorageFile])
    $stream = Await-WinRt ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
    $decoder = Await-WinRt ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
    $bitmap = Await-WinRt ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
    $ocrResult = Await-WinRt ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
    $lines = @()
    foreach ($line in $ocrResult.Lines) { $lines += $line.Text }
    $item.text = $lines -join "`n"
    $item.ok = $true
  } catch {
    $item.error = $_.Exception.Message
  }
  $results += [pscustomobject]$item
}

if ($Json) {
  $results | ConvertTo-Json -Depth 4
} else {
  foreach ($r in $results) {
    Write-Output ('=== ' + $r.path + ' ===')
    if ($r.ok) {
      if ($r.text) { Write-Output $r.text } else { Write-Output '(未识别到文字)' }
    } else {
      Write-Output ('[识别失败] ' + $r.error)
    }
  }
}
