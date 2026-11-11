$ErrorActionPreference='Stop'
$root=$PSScriptRoot
$csc=Join-Path $env:WINDIR 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
$references=@('/r:System.Windows.Forms.dll','/r:System.Drawing.dll','/r:System.Web.Extensions.dll','/r:System.IO.Compression.dll','/r:System.IO.Compression.FileSystem.dll')
& $csc /nologo /utf8output /target:exe /main:Cte2Patcher.PackageTests ($references) (('/out:')+(Join-Path $root 'dist/PackageTests.exe')) (Join-Path $root 'src/Patcher.cs') (Join-Path $root 'tests/PackageTests.cs')
if($LASTEXITCODE-ne 0){throw 'Package test compilation failed'}
& (Join-Path $root 'dist/PackageTests.exe') (Join-Path $root 'dist/release/update.json') (Join-Path $root 'dev/package-tests')
if($LASTEXITCODE-ne 0){throw 'Full release installation test failed'}
