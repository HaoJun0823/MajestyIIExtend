$gameFontDir = "I:\SteamLibrary\steamapps\common\Majesty 2 Collection\update\resource.mod\Fonts"
$cnFontDir = "I:\SteamLibrary\steamapps\common\Majesty 2 Collection\汉化\Majesty2-CN\fonts\New_Fonts_CHS"
$origFontDir = "I:\SteamLibrary\steamapps\common\Majesty 2 Collection\汉化\Majesty2-CN\fonts\Original_Fonts"
$release2FontDir = "I:\SteamLibrary\steamapps\common\Majesty 2 Collection\汉化\线索2\release包简体\update\resource.mod\Fonts"

$files = @("font12a.dds", "font12b.dds", "font14a.dds", "font14b.dds", "font18a.dds", "font18b.dds")

Write-Output "=== DDS Hash Comparison ==="
foreach ($f in $files) {
    $gameHash = (Get-FileHash "$gameFontDir\$f" -Algorithm MD5 -ErrorAction SilentlyContinue).Hash
    $cnHash = (Get-FileHash "$cnFontDir\$f" -Algorithm MD5 -ErrorAction SilentlyContinue).Hash
    $origHash = (Get-FileHash "$origFontDir\$f" -Algorithm MD5 -ErrorAction SilentlyContinue).Hash
    $rel2Hash = (Get-FileHash "$release2FontDir\$f" -Algorithm MD5 -ErrorAction SilentlyContinue).Hash
    
    if ($gameHash -eq $cnHash) { $gameMatch = "CJK" }
    elseif ($gameHash -eq $origHash) { $gameMatch = "ORIG" }
    else { $gameMatch = "UNKNOWN" }
    
    Write-Output ("{0}: game={1}" -f $f, $gameMatch)
    Write-Output ("  game={0}" -f $gameHash)
    Write-Output ("  cn  ={0}" -f $cnHash)
    Write-Output ("  orig={0}" -f $origHash)
    Write-Output ("  rel2={0}" -f $rel2Hash)
}

# Also compare .tuv files
Write-Output ""
Write-Output "=== TUV Hash Comparison ==="
$tuvFiles = @("font12.tuv", "font14.tuv", "font18.tuv")
foreach ($f in $tuvFiles) {
    $gameHash = (Get-FileHash "$gameFontDir\$f" -Algorithm MD5 -ErrorAction SilentlyContinue).Hash
    $origHash = (Get-FileHash "$origFontDir\$f" -Algorithm MD5 -ErrorAction SilentlyContinue).Hash
    $rel2Hash = (Get-FileHash "$release2FontDir\$f" -Algorithm MD5 -ErrorAction SilentlyContinue).Hash
    
    if ($gameHash -eq $origHash) { $gameMatch = "ORIG" }
    else { $gameMatch = "UNKNOWN" }
    
    Write-Output ("{0}: game={1}" -f $f, $gameMatch)
    Write-Output ("  game={0}" -f $gameHash)
    Write-Output ("  orig={0}" -f $origHash)
    Write-Output ("  rel2={0}" -f $rel2Hash)
}

# Also check CJK tuv files
Write-Output ""
Write-Output "=== CJK TUV files (a/b split) ==="
$cjkTuv = @("font12a.tuv", "font12b.tuv", "font14a.tuv", "font14b.tuv", "font18a.tuv", "font18b.tuv")
foreach ($f in $cjkTuv) {
    $cnHash = (Get-FileHash "$cnFontDir\$f" -Algorithm MD5 -ErrorAction SilentlyContinue).Hash
    $gameHash = (Get-FileHash "$gameFontDir\$f" -Algorithm MD5 -ErrorAction SilentlyContinue).Hash
    $rel2Hash = (Get-FileHash "$release2FontDir\$f" -Algorithm MD5 -ErrorAction SilentlyContinue).Hash
    Write-Output ("{0}: cn={1} game={2} rel2={3}" -f $f, $cnHash, $gameHash, $rel2Hash)
}
