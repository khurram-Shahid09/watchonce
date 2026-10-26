# Draft voice-over for the main demo video, read by the built-in Windows voice.
# One WAV per line (demo/out/voice/NN.wav) plus captions (demo/out/voice/captions.srt),
# so the edit can be timed before the real voice is recorded.
#   powershell -ExecutionPolicy Bypass -File demo/scripts/voiceover.ps1
Add-Type -AssemblyName System.Speech

$lines = @(
  "Every company has a system like this: an old web portal, no API, and a team that types into it all day.",
  "At Acme, Accounts Payable enters four hundred invoices a month into it. Four minutes each. By hand.",
  "So Sara shows WatchOnce how to do it. Once. She just does her job while the extension watches.",
  "A minute later it's a workflow: every step named, with a screenshot. The vendor, amount and dates became inputs. It even wrote the procedure document.",
  "Now it runs by itself, in a real browser. And before it submits anything, it stops and asks a human.",
  "October's backlog: twenty invoices from a spreadsheet. Sara approves once, and WatchOnce does the rest, with a results file at the end.",
  "Then IT ships a new version of the portal: new labels, new layout. Old automation breaks here. WatchOnce finds the same buttons, finishes the job, and shows the manager exactly what changed, for one-click approval.",
  "And when a page tries to trick the AI into deleting every vendor, it does its job and nothing else.",
  "Hours saved, every run audited, and no AI cost per run, because AI is only used to learn and to heal.",
  "WatchOnce. Show it once."
)

$out = Join-Path $PSScriptRoot "..\out\voice"
New-Item -ItemType Directory -Force $out | Out-Null
$voice = New-Object System.Speech.Synthesis.SpeechSynthesizer
$voice.Rate = -1
$srt = New-Object System.Text.StringBuilder
$clock = [TimeSpan]::Zero

for ($i = 0; $i -lt $lines.Count; $i++) {
  $file = Join-Path $out ("{0:D2}.wav" -f ($i + 1))
  $voice.SetOutputToWaveFile($file)
  $voice.Speak($lines[$i])
  $voice.SetOutputToNull()
  $head = [IO.File]::ReadAllBytes($file)[0..43]
  $bytesPerSecond = [BitConverter]::ToInt32($head, 28)  # from the WAV header
  $seconds = ((Get-Item $file).Length - 44) / $bytesPerSecond
  $end = $clock + [TimeSpan]::FromSeconds($seconds)
  [void]$srt.AppendLine($i + 1)
  [void]$srt.AppendLine(("{0:hh\:mm\:ss\,fff} --> {1:hh\:mm\:ss\,fff}" -f $clock, $end))
  [void]$srt.AppendLine($lines[$i])
  [void]$srt.AppendLine()
  $clock = $end + [TimeSpan]::FromMilliseconds(400)
  Write-Host ("{0:D2}.wav  {1:N1}s" -f ($i + 1), $seconds)
}
$voice.Dispose()
[IO.File]::WriteAllText((Join-Path $out "captions.srt"), $srt.ToString())
Write-Host ("Total {0:mm\:ss}. Files in {1}" -f $clock, (Resolve-Path $out))
