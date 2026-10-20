# SPDX-License-Identifier: MIT
<# Deterministic catalogue order; rights-filtered, never filtered by engine results.
   Native HTTPS uses the OS trust store. Every attempt and RDF snapshot is retained. #>
param(
    [Parameter(Mandatory=$true)][string]$Output,
    [ValidateRange(1,10000)][int]$Count = 500,
    [ValidateRange(1,100000)][int]$MaxId = 5000
)
$ErrorActionPreference = 'Stop'
$corpusRoot = [IO.Path]::GetFullPath($Output)
[IO.Directory]::CreateDirectory($corpusRoot) | Out-Null
[IO.Directory]::CreateDirectory((Join-Path $corpusRoot 'metadata')) | Out-Null
[IO.Directory]::CreateDirectory((Join-Path $corpusRoot 'books')) | Out-Null
$manifestPath = Join-Path $corpusRoot 'manifest.json'
$records = [Collections.Generic.List[object]]::new()
$attempts = [Collections.Generic.List[object]]::new()
$nextId = 1
if (Test-Path -LiteralPath $manifestPath) {
    $prior = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    if ($prior.schema -ne 1 -or $prior.selection -ne 'ascending catalogue IDs; EPUB3 with images; USA public domain') {
        throw 'Existing manifest has a different collection policy'
    }
    foreach ($record in $prior.files) {
        $book = Join-Path $corpusRoot $record.path
        if ((Get-FileHash -LiteralPath $book -Algorithm SHA256).Hash.ToLowerInvariant() -ne $record.sha256) {
            throw 'Existing input changed; preserve this dataset and choose a new directory'
        }
        $rdf = Join-Path $corpusRoot $record.metadata_path
        if ((Get-FileHash -LiteralPath $rdf -Algorithm SHA256).Hash.ToLowerInvariant() -ne $record.metadata_sha256) {
            throw 'Existing metadata changed'
        }
        $records.Add($record)
    }
    foreach ($attempt in $prior.attempts) { $attempts.Add($attempt) }
    $nextId = [int]$prior.next_id
}
function Save-Manifest {
    $snapshot = [ordered]@{
        schema=1; selection='ascending catalogue IDs; EPUB3 with images; USA public domain'
        rights_scope='Public domain in the USA; original embedded Gutenberg terms retained'
        downloaded_utc=[DateTime]::UtcNow.ToString('o'); target=$Count; next_id=$script:nextId
        collected=$records.Count; complete=($records.Count -ge $Count)
        files=@($records.ToArray()); attempts=@($attempts.ToArray())
    }
    $temporary = $manifestPath+'.new'
    $snapshot | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $temporary -Encoding utf8
    [IO.File]::Move($temporary,$manifestPath,$true)
}
for ($catalogueId=$nextId; $catalogueId -le $MaxId -and $records.Count -lt $Count; $catalogueId++) {
    $rdfUrl = "https://www.gutenberg.org/cache/epub/$catalogueId/pg$catalogueId.rdf"
    $bookUrl = "https://www.gutenberg.org/cache/epub/$catalogueId/pg$catalogueId-images-3.epub"
    $rdfRelative = "metadata/$catalogueId.rdf"
    $bookRelative = "books/pg$catalogueId.epub"
    $rdfPath = Join-Path $corpusRoot $rdfRelative
    $bookPath = Join-Path $corpusRoot $bookRelative
    $attempt = [ordered]@{id=$catalogueId;metadata_url=$rdfUrl;source=$bookUrl;status='started'}
    try {
        if ((Test-Path -LiteralPath $rdfPath) -or (Test-Path -LiteralPath $bookPath)) {
            throw 'Unindexed evidence already exists; inspect it before resuming'
        }
        Start-Sleep -Milliseconds 500
        Invoke-WebRequest -Uri $rdfUrl -OutFile $rdfPath -TimeoutSec 45
        $xml = [Xml.XmlDocument]::new()
        $xml.XmlResolver = $null
        $xml.Load($rdfPath)
        $ns = [Xml.XmlNamespaceManager]::new($xml.NameTable)
        $ns.AddNamespace('dcterms','http://purl.org/dc/terms/')
        $ns.AddNamespace('pgterms','http://www.gutenberg.org/2009/pgterms/')
        $ns.AddNamespace('rdf','http://www.w3.org/1999/02/22-rdf-syntax-ns#')
        $rights = $xml.SelectSingleNode('//pgterms:ebook/dcterms:rights',$ns).InnerText
        $title = $xml.SelectSingleNode('//pgterms:ebook/dcterms:title',$ns).InnerText
        if ($rights -ne 'Public domain in the USA.') {
            $attempt.status='rights_not_selected'; $attempt.rights=$rights
        } elseif (-not $xml.SelectSingleNode("//pgterms:file[@rdf:about='https://www.gutenberg.org/ebooks/$catalogueId.epub3.images']",$ns)) {
            $attempt.status='epub3_not_available'
        } else {
            Start-Sleep -Milliseconds 500
            Invoke-WebRequest -Uri $bookUrl -OutFile $bookPath -TimeoutSec 90
            Add-Type -AssemblyName System.IO.Compression
            $archive = [IO.Compression.ZipFile]::OpenRead($bookPath)
            try {
                if (-not $archive.GetEntry('mimetype') -or -not $archive.GetEntry('META-INF/container.xml')) {
                    throw 'Downloaded archive is missing EPUB declarations'
                }
            } finally { $archive.Dispose() }
            $records.Add([ordered]@{
                id=$catalogueId;path=$bookRelative;source=$bookUrl;title=$title;rights=$rights
                bytes=(Get-Item -LiteralPath $bookPath).Length
                sha256=(Get-FileHash -LiteralPath $bookPath -Algorithm SHA256).Hash.ToLowerInvariant()
                metadata_path=$rdfRelative;metadata_source=$rdfUrl
                metadata_sha256=(Get-FileHash -LiteralPath $rdfPath -Algorithm SHA256).Hash.ToLowerInvariant()
                expected=@{status=0;complete=$true}
                expected_scope='all-page pipeline only; fidelity and saving not evaluated'
            })
            $attempt.status='collected'
        }
    } catch {
        $attempt.status='collection_failed'
        $attempt.error=$_.Exception.Message
    }
    $attempts.Add($attempt)
    $script:nextId=$catalogueId+1
    Save-Manifest
    if ($catalogueId % 25 -eq 0) { Write-Output "catalogue=$catalogueId collected=$($records.Count)" }
}
Save-Manifest
Write-Output "collected=$($records.Count) target=$Count"
if ($records.Count -lt $Count) { exit 1 }
