# Inspect the real Offline Studio window: DWM caption attributes + full-window capture.
#   powershell -File qa\window.ps1 [-Out after\x.png]
param([string]$Out = "")
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System; using System.Runtime.InteropServices;
public class StudioWin {
  [DllImport("dwmapi.dll")] public static extern int DwmGetWindowAttribute(IntPtr h, int attr, out int value, int size);
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr dc, uint flags);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  public struct RECT { public int L, T, R, B; }
}
"@
$p = Get-Process -Name "Offline Studio" -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
if (-not $p) { Write-Output '{"running":false}'; exit 1 }
$h = $p.MainWindowHandle
$dark = 0; $caption = 0; $text = 0
[void][StudioWin]::DwmGetWindowAttribute($h, 20, [ref]$dark, 4)
[void][StudioWin]::DwmGetWindowAttribute($h, 35, [ref]$caption, 4)
[void][StudioWin]::DwmGetWindowAttribute($h, 36, [ref]$text, 4)
$result = [ordered]@{ running = $true; pid = $p.Id; title = $p.MainWindowTitle; immersiveDark = $dark; captionColor = ('0x{0:X8}' -f $caption); textColor = ('0x{0:X8}' -f $text) }
if ($Out) {
  $r = New-Object StudioWin+RECT; [void][StudioWin]::GetWindowRect($h, [ref]$r)
  $bmp = New-Object Drawing.Bitmap ($r.R - $r.L), ($r.B - $r.T); $g = [Drawing.Graphics]::FromImage($bmp)
  $dc = $g.GetHdc(); [void][StudioWin]::PrintWindow($h, $dc, 2); $g.ReleaseHdc($dc)
  $px = $bmp.GetPixel([int]($bmp.Width / 2), 8); $result.captionPixel = ('#{0:X2}{1:X2}{2:X2}' -f $px.R, $px.G, $px.B)
  $bmp.Save($Out); $result.capture = $Out
}
$result | ConvertTo-Json -Compress
