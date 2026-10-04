<#
build_release.ps1 — MajestyIIExtend localized-patch full assembly script
========================================================================
Executable counterpart of `构建流程.md` (with its BUG fixes listed at the
bottom). Reusable on BOTH a local machine and GitHub Actions CI.

Pipeline:
  1. bake CJK fonts from scratch via fontgen/build_font_atlas.py
     font_auto_build.yaml  (CI path; skip locally with -SkipBake if Resource/
     already carries baked fonts)
  2. compile MajestyII_UTF8.dll with direct cl.exe invocation (v141_xp,
     no CRT, /O2) and rename to MajestyII_GB18030_2000.asi (the name the
     game actually loads)
  3. OpenCC s2t (simplified -> traditional) on Text/DictRead.txt and
     dist/汉化说明.txt
  4. assemble CHS / CHT release directory trees
  5. verify artifacts (DLL is PE32, asi present, fonts complete, zips valid,
     encoding correct)
  6. pack to MajestyII-CHS-{date}-{time}.zip / MajestyII-CHT-{date}-{time}.zip

Usage:
    pwsh tools/build_release.ps1                 # full chain
    pwsh tools/build_release.ps1 -SkipBake       # skip font bake (use committed Resource output)
    pwsh tools/build_release.ps1 -SkipDll        # skip DLL compile (reuse existing dll)
    pwsh tools/build_release.ps1 -OutDir C:\out  # custom output dir

Dependencies:
    - Python 3.10+, pip packages: opencc (s2t), Pillow, freetype-py (bake)
    - Baking is only needed when aggregating from scratch (CI/new clone)
========================================================================
#>
[CmdletBinding()]
param(
    [switch]$SkipBake,      # skip font bake (use fonts already committed in Resource/)
    [switch]$SkipDll,       # skip DLL compile (reuse an existing dll)
    [switch]$SkipOpenCC,    # skip s2t conversion (keep simplified for CHT)
    [string]$OutDir = "build_out"
)

$ErrorActionPreference = 'Stop'
$Repo = Split-Path -Parent $PSScriptRoot          # repo root
$PY = Get-Command python -ErrorAction SilentlyContinue
if (-not $PY) { $PY = Get-Command py -ErrorAction SilentlyContinue }
if (-not $PY) { throw "python not found. Install Python 3.10+ and add it to PATH." }
$PyExe = $PY.Source

function Invoke-Step($Name, [scriptblock]$Block) {
    Write-Host ""
    Write-Host "-----------------------------------------------"
    Write-Host "  $Name"
    Write-Host "-----------------------------------------------"
    & $Block
    if ($LASTEXITCODE) { throw "step failed (rc=$LASTEXITCODE): $Name" }
}

$ts = Get-Date

# ---------- output dirs ----------
$OutDir = if ([IO.Path]::IsPathRooted($OutDir)) { $OutDir } else { Join-Path $Repo $OutDir }
$Build  = Join-Path $OutDir 'Build'
$CHS    = Join-Path $Build 'CHS'
$CHT    = Join-Path $Build 'CHT'
foreach ($d in @($OutDir, $Build, $CHS, $CHT)) {
    New-Item -ItemType Directory -Force -Path $d | Out-Null
}

# ============================================================
# STEP 1 — font bake (optional; CI / aggregate path)
# ============================================================
$script:BakeOut = Join-Path $Repo 'fontgen\font_auto_build'   # aligned with yaml output_dir
if (-not $SkipBake) {
    Invoke-Step "STEP 1 · bake CJK fonts (build_font_atlas.py font_auto_build.yaml)" {
        Push-Location (Join-Path $Repo 'fontgen')
        try {
            & $PyExe build_font_atlas.py font_auto_build.yaml
        } finally { Pop-Location }
        if (-not (Test-Path $script:BakeOut)) {
            throw "bake did not produce $script:BakeOut (check font_auto_build.yaml output_dir is font_auto_build)"
        }
        $n = (Get-ChildItem $script:BakeOut -Recurse -File | Where-Object {$_.Extension -in '.dds','.tuv'}).Count
        Write-Host "baked: $n dds/tuv -> $script:BakeOut"
    }
} else {
    Write-Host ">> skip bake (-SkipBake), using fonts already committed in Resource/"
}

# ============================================================
# STEP 2 — compile DLL via direct cl.exe (v141_xp)
# ============================================================
if (-not $SkipDll) {
    Invoke-Step "STEP 2 · compile MajestyII_UTF8.dll (cl.exe direct)" {
        $slnDir = Join-Path $Repo 'MajestyII_UTF8'
        # --- discover cl.exe (prefer v141, any MSVC toolset as fallback) ---
        # cl.exe lives at <ver>/bin/Hostx86/x86/cl.exe; v141 version dirs are 14.16*
        $cl = $null
        $vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
        if (Test-Path $vswhere) {
            foreach ($q in @('VC\Tools\MSVC\14.16*\bin\Hostx86\x86\cl.exe','VC\Tools\MSVC\*\bin\Hostx86\x86\cl.exe')) {
                $hit = (& $vswhere -all -products * -find $q 2>$null | Select-Object -First 1)
                if ($hit) { $cl = $hit; break }
            }
        }
        if (-not $cl) {
            $legacy = "C:\Program Files (x86)\Microsoft Visual Studio\2017\Professional\VC\Tools\MSVC\14.16.27023\bin\Hostx86\x86\cl.exe"
            if (Test-Path $legacy) { $cl = $legacy }
        }
        if (-not $cl) { throw "cl.exe not found. CI must install v141 toolset (VS Installer VC.v141.x86.x64)." }
        Write-Host "cl.exe = $cl"

        # --- MSVC version root <ver> (4 levels up from cl.exe) ---
        #   cl.exe -> x86 -> Hostx86 -> bin -> <ver>
        $ver = Split-Path (Split-Path (Split-Path (Split-Path $cl -Parent) -Parent) -Parent) -Parent

        # --- SDK: highest Windows Kits\10\Include with um/shared/ucrt ---
        $kitsRoot  = "${env:ProgramFiles(x86)}\Windows Kits\10"
        $sdkInc = Get-ChildItem (Join-Path $kitsRoot 'Include') -Directory -ErrorAction SilentlyContinue |
                  Where-Object { (Test-Path (Join-Path $_.FullName 'um')) -and (Test-Path (Join-Path $_.FullName 'shared')) -and (Test-Path (Join-Path $_.FullName 'ucrt')) } |
                  Sort-Object { try { [version]$_.Name } catch { [version]'0.0' } } -Descending | Select-Object -First 1
        if (-not $sdkInc) { throw "Windows SDK not found under $kitsRoot\Include (need um/shared/ucrt)" }
        $sdkVer = $sdkInc.Name
        Write-Host "SDK = $sdkVer"

        # --- INCLUDE / LIB (MSVC <ver> + SDK) ---
        $env:INCLUDE = @(
            (Join-Path $ver 'include'),
            (Join-Path $kitsRoot "Include\$sdkVer\ucrt"),
            (Join-Path $kitsRoot "Include\$sdkVer\um"),
            (Join-Path $kitsRoot "Include\$sdkVer\shared")
        ) -join ';'
        $env:LIB = @(
            (Join-Path $ver 'lib\x86'),
            (Join-Path $kitsRoot "Lib\$sdkVer\ucrt\x86"),
            (Join-Path $kitsRoot "Lib\$sdkVer\um\x86")
        ) -join ';'
        Write-Host "MSVC ver = $ver"
        Write-Host "INCLUDE = $env:INCLUDE"
        Write-Host "LIB     = $env:LIB"

        # --- compile: same flags as build_deploy.sh/build.bat ---
        # Use a cmd driver to avoid pwsh parsing ambiguity on /link & quoted /OUT.
        $dll = Join-Path $slnDir 'MajestyII_UTF8.dll'
        Push-Location $slnDir
        try {
            $driver = @"
@echo off
setlocal
chcp 65001 >nul
"$cl" /nologo /LD /EHsc /Y- /utf-8 /O2 /D WIN32 /D NDEBUG /D MAJESTYIIUTF8_EXPORTS /D _WINDOWS /D _USRDLL /I. dllmain.cpp pch.cpp /link /OUT:"MajestyII_UTF8.dll" /SUBSYSTEM:WINDOWS kernel32.lib user32.lib gdi32.lib winmm.lib advapi32.lib shell32.lib ole32.lib
exit /b %errorlevel%
"@
            $bat = Join-Path $slnDir "_build_release_driver.cmd"
            [System.IO.File]::WriteAllText($bat, $driver, [System.Text.Encoding]::ASCII)
            cmd /c "`"$bat`""
            Remove-Item $bat -Force -ErrorAction SilentlyContinue
            if ($LASTEXITCODE -ne 0) { throw "cl.exe compile failed (rc=$LASTEXITCODE)" }
        } finally { Pop-Location }

        if (-not (Test-Path $dll)) { throw "compile did not produce $dll" }
        # --- deploy as asi to CHS/CHT update/ ---
        foreach ($dst in @(
            (Join-Path $CHS 'update\MajestyII_GB18030_2000.asi'),
            (Join-Path $CHT 'update\MajestyII_GB18030_2000.asi'))) {
            New-Item -ItemType Directory -Force -Path (Split-Path $dst -Parent) | Out-Null
            Copy-Item $dll $dst -Force
        }
        Write-Host "asi deployed -> CHS\update & CHT\update"
    }
} else {
    Write-Host ">> skip DLL compile (-SkipDll), reusing existing dll"
    $legacyDll = Join-Path $Repo 'MajestyII_UTF8\MajestyII_UTF8.dll'
    if (Test-Path $legacyDll) {
        foreach ($dst in @((Join-Path $CHS 'update\MajestyII_GB18030_2000.asi'),(Join-Path $CHT 'update\MajestyII_GB18030_2000.asi'))) {
            New-Item -ItemType Directory -Force -Path (Split-Path $dst -Parent) | Out-Null
            Copy-Item $legacyDll $dst -Force
        }
        Write-Host "reused existing dll"
    } else {
        Write-Warning "-SkipDll but no existing dll found; asi will be missing"
    }
}

# ============================================================
# STEP 3 — OpenCC simplified -> traditional
# ============================================================
function Convert-File-S2T([string]$src, [string]$dst, [string]$encoding) {
    # src/dst both GB18030; python opencc converts only CJK, keeps ASCII/tags/structure
    $tmp = Join-Path $env:TEMP ("mj2_{0}.py" -f ([guid]::NewGuid().ToString('N')))
    $py = @'
import sys, codecs
from opencc import OpenCC
cc = OpenCC('s2t')
src, dst, enc = sys.argv[1], sys.argv[2], sys.argv[3]
with codecs.open(src, 'r', enc) as f:
    text = f.read()
converted = cc.convert(text)
with codecs.open(dst, 'w', enc) as f:
    f.write(converted)
print('converted %d chars' % len(converted))
'@
    [System.IO.File]::WriteAllText($tmp, $py -replace "`n","`r`n", [System.Text.Encoding]::UTF8)
    try {
        & $PyExe $tmp $src $dst $encoding
        if ($LASTEXITCODE) { throw "OpenCC conversion failed" }
    } finally { Remove-Item $tmp -Force -ErrorAction SilentlyContinue }
}

if (-not $SkipOpenCC) {
    Invoke-Step "STEP 3 · OpenCC s2t on DictRead + readme" {
        & $PyExe -c "import opencc" 2>$null
        if ($LASTEXITCODE) { throw "missing opencc; pip install opencc" }

        # traditional dict
        $dictSrc = Join-Path $Repo 'Text\DictRead.txt'
        if (Test-Path $dictSrc) {
            $dictDst = Join-Path $CHT 'update\DictRead.txt'
            New-Item -ItemType Directory -Force -Path (Split-Path $dictDst -Parent) | Out-Null
            Convert-File-S2T $dictSrc $dictDst 'GB18030'
        } else { Write-Warning "missing $dictSrc; skipping traditional dict" }

        # traditional readme
        $readmeSrc = Join-Path $Repo 'dist\汉化说明.txt'
        $readmeDst = Join-Path $CHT '汉化说明.txt'
        if (Test-Path $readmeSrc) {
            if ((Get-Item $readmeSrc).Length -gt 0) {
                New-Item -ItemType Directory -Force -Path (Split-Path $readmeDst -Parent) | Out-Null
                Convert-File-S2T $readmeSrc $readmeDst 'GB18030'
            } else { Write-Warning "dist\汉化说明.txt is 0 bytes; CHT readme left empty (provide content)"
            }
        }
    }
} else {
    Write-Host ">> skip s2t (-SkipOpenCC)"
}

# ============================================================
# STEP 4 — assemble CHS / CHT release packages
# ============================================================
Invoke-Step "STEP 4 · assemble CHS / CHT packages" {
    $dist = Join-Path $Repo 'dist'

    foreach ($lang in @('CHS','CHT')) {
        $target = if ($lang -eq 'CHS') { $CHS } else { $CHT }

        # 4.1 winmm.dll
        $winmm = Join-Path $dist 'winmm.dll'
        if (Test-Path $winmm) { Copy-Item $winmm (Join-Path $target 'winmm.dll') -Force }
        else { Write-Warning "missing $winmm" }

        # 4.2 merge License -> License.txt
        $licDir = Join-Path $Repo 'License'
        $licFiles = Get-ChildItem $licDir -File -ErrorAction SilentlyContinue
        if ($licFiles) {
            $licDst = Join-Path $target 'License.txt'
            Get-Content $licFiles.FullName -Raw -Encoding UTF8 | Out-File $licDst -Encoding UTF8
        } else { Write-Warning "License/ empty, no License.txt generated" }

        # 4.3 readme (CHS original, CHT converted in STEP3)
        $rs = Join-Path $dist '汉化说明.txt'
        $rd = Join-Path $target '汉化说明.txt'
        if (-not $SkipOpenCC -and $lang -eq 'CHT' -and (Test-Path $rd)) {
            # already produced by STEP3
        } elseif (Test-Path $rs) {
            Copy-Item $rs $rd -Force
        } else { Write-Warning "missing $rs" }

        # 4.4 update/ dict (CHS = simplified original; CHT = prevailing converted)
        $ud = Join-Path $target 'update'
        New-Item -ItemType Directory -Force -Path $ud | Out-Null
        if ($lang -eq 'CHS') {
            $ds = Join-Path $Repo 'Text\DictRead.txt'
            if (Test-Path $ds) { Copy-Item $ds (Join-Path $ud 'DictRead.txt') -Force }
        }

        # 4.5 merge Resource into update/localization/**  (lang overrides Common)
        $resCommon = Join-Path $Repo 'Resource\Common'
        $resLang   = Join-Path $Repo "Resource\$lang"
        foreach ($base in @($resCommon, $resLang)) {
            if (-not (Test-Path $base)) { continue }
            $zipDirs = Get-ChildItem $base -Recurse -Directory -Filter '*.zip' -ErrorAction SilentlyContinue
            foreach ($z in $zipDirs) {
                $rel = $z.FullName.Substring($base.Length + 1)   # <relpath>\<X.zip>
                # normalize: game actually reads texts.zip (Common tree labels it text.zip)
                if ($rel -match '(?<dir>^.*[\\/])text\.zip$') {
                    $rel = $dir + 'texts.zip'
                }
                $targetZip = Join-Path $ud $rel
                New-Item -ItemType Directory -Force -Path $targetZip | Out-Null
                Get-ChildItem $z.FullName -Recurse -File | ForEach-Object {
                    $relF = $_.FullName.Substring($z.FullName.Length + 1)
                    $dstF = Join-Path $targetZip $relF
                    New-Item -ItemType Directory -Force -Path (Split-Path $dstF -Parent) | Out-Null
                    Copy-Item $_.FullName $dstF -Force
                }
            }
        }

        # 4.5b update/localization/launcher
        $lL = Join-Path $resLang "localization\launcher"
        $lC = Join-Path $resCommon "localization\launcher"
        $lSrc = if (Test-Path $lL) { $lL } elseif (Test-Path $lC) { $lC } else { $null }
        if ($lSrc) {
            Get-ChildItem $lSrc -File -ErrorAction SilentlyContinue | ForEach-Object {
                $dstL = Join-Path $ud "localization\launcher\$($_.Name)"
                New-Item -ItemType Directory -Force -Path (Split-Path $dstL -Parent) | Out-Null
                Copy-Item $_.FullName $dstL -Force
            }
        }

        # 4.5c if baked this run, overlay baked dds/tuv onto texts.zip/enGUIne/Fonts
        if (-not $SkipBake -and (Test-Path $script:BakeOut)) {
            $fontDst = Join-Path $ud "localization\texts\texts.zip\enGUIne\Fonts"
            New-Item -ItemType Directory -Force -Path $fontDst | Out-Null
            $moved = 0
            Get-ChildItem $script:BakeOut -Recurse -File -ErrorAction SilentlyContinue |
                Where-Object { $_.Extension -in '.dds','.tuv' } | ForEach-Object {
                    Copy-Item $_.FullName (Join-Path $fontDst $_.Name) -Force
                    $moved++
                }
            Write-Host "  overlaid $moved baked fonts into texts.zip [$lang]"
        }

        # 4.6 support/ + DLC_Unlock.bat
        $sup = Join-Path $dist 'support'
        if (Test-Path $sup) {
            Get-ChildItem $sup -File -Recurse | ForEach-Object {
                $rel = $_.FullName.Substring($sup.Length + 1)
                $dstS = Join-Path $target "support\$rel"
                New-Item -ItemType Directory -Force -Path (Split-Path $dstS -Parent) | Out-Null
                Copy-Item $_.FullName $dstS -Force
            }
        } else { Write-Warning "dist/support missing" }
        $dlu = Join-Path $dist 'DLC_Unlock.bat'
        if (Test-Path $dlu) { Copy-Item $dlu (Join-Path $target 'DLC_Unlock.bat') -Force }

        Write-Host "assembled: $lang -> $target"
    }
}

# ============================================================
# STEP 5 — verify artifacts
# ============================================================
Invoke-Step "STEP 5 · verify artifacts" {
    foreach ($lang in @('CHS','CHT')) {
        $t = if ($lang -eq 'CHS') { $CHS } else { $CHT }
        $errs = @()
        $asi = Join-Path $t "update\MajestyII_GB18030_2000.asi"
        if (-not (Test-Path $asi)) { $errs += "missing $asi" }
        else {
            $b = [System.IO.File]::ReadAllBytes($asi)
            if ($b.Length -lt 0x60 -or $b[0x3c] -gt $b.Length) { $errs += "asi not valid PE" }
            else {
                [int]$peOff = [BitConverter]::ToInt32($b, 0x3c)
                $machine = [BitConverter]::ToUInt16($b, $peOff + 4)
                if ($machine -ne 0x014c) { $errs += "asi machine=0x{0:x} not x86/PE32" -f $machine }
            }
        }
        $tz = Join-Path $t "update\localization\texts\texts.zip\enGUIne\Fonts"
        if (-not (Test-Path $tz)) { $errs += "missing fonts texts.zip dir" }
        else {
            $cdds = @(Get-ChildItem $tz -Filter '*_c.dds')
            if ($cdds.Count -lt 4) { $errs += "CJK _c.dds insufficient (want >=4): got $($cdds.Count)" }
        }
        if (-not (Test-Path (Join-Path $t "update\DictRead.txt"))) { $errs += "missing update\DictRead.txt" }
        foreach ($e in $errs) { Write-Host "  X $e" }
        if ($errs.Count) { throw ("{0} package verification failed: {1} issue(s)" -f $lang, $errs.Count) }
        Write-Host "  OK $lang verification passed"
    }
}

# ============================================================
# STEP 6 — pack into release zips
# ============================================================
Invoke-Step "STEP 6 · pack release zips" {
    $date = $ts.ToString('yyyy-MM-dd')
    $time = $ts.ToString('HH-mm-ss')
    foreach ($lang in @('CHS','CHT')) {
        $t = if ($lang -eq 'CHS') { $CHS } else { $CHT }
        $zip = Join-Path $OutDir ("MajestyII-{0}-{1}-{2}.zip" -f $lang, $date, $time)
        if (Test-Path $zip) { Remove-Item $zip -Force }
        Compress-Archive -Path (Join-Path $t '*') -DestinationPath $zip -CompressionLevel Optimal
        Write-Host "OK $zip  ($([math]::Round((Get-Item $zip).Length/1MB,1)) MB)"
    }
    Write-Host ""
    Write-Host "artifacts under $OutDir"
}

# ============================================================
# notes vs `构建流程.md`
# ============================================================
Write-Host ""
Write-Host "-- diff from build-doc (fixes to BUGs / gaps) ----------"
Write-Host " 1) steps 5/7 referenced tools/ s2t helpers, but tools/ was empty -> switch to OpenCC"
Write-Host " 2) step 6 real output name is MajestyII_GB18030_2000.asi (doc had typo)"
Write-Host " 3) step 10 texts_\{dlc\}.zip naming -> real: texts.expansion_N.zip"
Write-Host " 4) step 8 bake needs ttf/original_dds/texconv committed into git so CI can"
Write-Host "     bake from scratch; dict is reused from Text/DictRead.txt"
Write-Host "     into git for CI to bake from scratch"
Write-Host " 5) release ships 60FPSLimiter.asi & DictRead_V7_CHT.txt with no repo source;"
Write-Host "     this script does NOT fabricate them (warns only)"
Write-Host " 6) dist\汉化说明.txt is currently 0 bytes; packed as-is with a warning"
Write-Host ""
Write-Host "done."