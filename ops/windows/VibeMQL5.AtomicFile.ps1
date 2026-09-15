Set-StrictMode -Version Latest

function Test-VibeTransientAtomicError {
    [CmdletBinding()]
    param([Parameter(Mandatory)][System.Exception]$Exception)

    # PowerShell 5.1 wraps static .NET invocation failures in
    # MethodInvocationException. Walk the inner-exception chain so the
    # originating Win32 HRESULT (for example sharing violation 32) drives
    # the bounded retry policy instead of the wrapper HRESULT.
    $current = $Exception
    while ($null -ne $current) {
        $code = [int]($current.HResult -band 0xFFFF)
        if ($code -in @(5,32,80,183)) {
            return $true
        }
        $current = $current.InnerException
    }
    return $false
}

function Write-VibeAtomicBytes {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][byte[]]$Bytes,
        [ValidateRange(1,16)][int]$MaxAttempts = 8,
        [ValidateRange(1,1000)][int]$BaseDelayMilliseconds = 10
    )

    $full = [IO.Path]::GetFullPath($Path)
    $directory = Split-Path -Parent $full
    if (-not (Test-Path -LiteralPath $directory)) {
        New-Item -ItemType Directory -Path $directory -Force | Out-Null
    }

    $token = '{0}.{1}' -f $PID,[guid]::NewGuid().ToString('N')
    $tmp = Join-Path $directory ('.{0}.{1}.tmp' -f [IO.Path]::GetFileName($full),$token)
    $backup = Join-Path $directory ('.{0}.{1}.bak' -f [IO.Path]::GetFileName($full),$token)

    try {
        $stream = New-Object IO.FileStream(
            $tmp,
            [IO.FileMode]::CreateNew,
            [IO.FileAccess]::Write,
            [IO.FileShare]::None,
            4096,
            [IO.FileOptions]::WriteThrough
        )
        try {
            $stream.Write($Bytes,0,$Bytes.Length)
            $stream.Flush($true)
        }
        finally {
            $stream.Dispose()
        }

        for ($attempt=0; $attempt -lt $MaxAttempts; $attempt++) {
            try {
                if (Test-Path -LiteralPath $full) {
                    # .NET Framework / Windows PowerShell 5.1 rejects a null
                    # destinationBackupFileName for File.Replace. Use a unique
                    # same-directory backup path and remove it after the atomic
                    # replacement. This preserves File.Replace semantics while
                    # remaining compatible with the deployed CLR 4.x runtime.
                    Remove-Item -LiteralPath $backup -Force -ErrorAction SilentlyContinue
                    [IO.File]::Replace($tmp,$full,$backup,$true)
                }
                else {
                    [IO.File]::Move($tmp,$full)
                }
                return
            }
            catch {
                if (-not (Test-VibeTransientAtomicError -Exception $_.Exception) -or $attempt -eq ($MaxAttempts-1)) {
                    throw
                }
                $delay = [Math]::Min(2000,[int]($BaseDelayMilliseconds * [Math]::Pow(2,$attempt)))
                [Threading.Thread]::Sleep($delay)
            }
        }

        throw 'VIBE_ATOMIC_REPLACE_EXHAUSTED'
    }
    finally {
        Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $backup -Force -ErrorAction SilentlyContinue
    }
}

function Write-VibeAtomicJson {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][object]$Value,
        [ValidateRange(2,100)][int]$Depth = 10,
        [ValidateRange(1,16)][int]$MaxAttempts = 8,
        [ValidateRange(1,1000)][int]$BaseDelayMilliseconds = 10
    )

    $json = $Value | ConvertTo-Json -Depth $Depth
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    $bytes = $utf8.GetBytes($json)
    Write-VibeAtomicBytes -Path $Path -Bytes $bytes -MaxAttempts $MaxAttempts -BaseDelayMilliseconds $BaseDelayMilliseconds
}
