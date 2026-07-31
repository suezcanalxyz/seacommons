param(
    [ValidateSet('Mobile', 'Desktop')]
    [string]$Profile = 'Mobile',
    [string]$SignallingUrl = 'ws://127.0.0.1:8888',
    [string]$Executable = ''
)

$projectRoot = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($Executable)) {
    $Executable = Join-Path $projectRoot 'Packaged\Windows\SeaCommonsImmersive.exe'
}

$executablePath = [System.IO.Path]::GetFullPath($Executable)
if (-not (Test-Path -LiteralPath $executablePath -PathType Leaf)) {
    throw "Packaged renderer not found: $executablePath"
}

$profileArguments = if ($Profile -eq 'Mobile') {
    @(
        '-ForceRes',
        '-ResX=960',
        '-ResY=540',
        '-PixelStreamingWebRTCMaxFps=30',
        '-PixelStreamingWebRTCMinBitrate=750000',
        '-PixelStreamingWebRTCStartBitrate=3000000',
        '-PixelStreamingWebRTCMaxBitrate=5500000',
        '-PixelStreamingEncoderMaxQP=34',
        '-PixelStreamingWebRTCDegradationPreference=MAINTAIN_FRAMERATE'
    )
} else {
    @(
        '-ForceRes',
        '-ResX=1280',
        '-ResY=720',
        '-PixelStreamingWebRTCMaxFps=30',
        '-PixelStreamingWebRTCMinBitrate=2000000',
        '-PixelStreamingWebRTCStartBitrate=8000000',
        '-PixelStreamingWebRTCMaxBitrate=12000000',
        '-PixelStreamingEncoderMaxQP=30',
        '-PixelStreamingWebRTCDegradationPreference=BALANCED'
    )
}

$arguments = @(
    '-d3d11',
    '-RenderOffscreen',
    "-PixelStreamingURL=$SignallingUrl",
    '-AudioMixer',
    '-Unattended',
    '-NoSplash',
    '-StdOut',
    '-FullStdOutLogOutput'
) + $profileArguments

Write-Host "SeaCommons Pixel Streaming profile: $Profile"
Write-Host "Renderer: $executablePath"
Write-Host "Signalling: $SignallingUrl"
& $executablePath @arguments
exit $LASTEXITCODE
