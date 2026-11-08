$ErrorActionPreference = 'Stop'
$src = 'C:\Users\SMYqy\D13_论文写作\07_五篇SCI\docx'
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
$ok = 0
Get-ChildItem $src -Filter *.docx | ForEach-Object {
    $doc = $word.Documents.Open($_.FullName, $false, $true)
    $pdf = [System.IO.Path]::ChangeExtension($_.FullName, '.pdf')
    $doc.SaveAs([ref]$pdf, [ref]17)
    $doc.Close($false)
    $ok++
    Write-Output ("OK " + $_.Name)
}
$word.Quit()
Write-Output ("DONE " + $ok)
