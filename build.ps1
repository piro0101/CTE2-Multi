$ErrorActionPreference='Stop'
$root=$PSScriptRoot
$framework=Join-Path ([Runtime.InteropServices.RuntimeEnvironment]::GetRuntimeDirectory()) 'csc.exe'
if(!(Test-Path -LiteralPath $framework)){$framework=Join-Path $env:WINDIR 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'}
if(!(Test-Path -LiteralPath $framework)){throw 'Windows .NET Framework C# compiler was not found.'}
$dist=Join-Path $root 'dist'
New-Item -ItemType Directory -Path $dist -Force|Out-Null
$references=@('/r:System.Windows.Forms.dll','/r:System.Drawing.dll','/r:System.Web.Extensions.dll','/r:System.IO.Compression.dll','/r:System.IO.Compression.FileSystem.dll')
& $framework /nologo /utf8output /target:winexe /optimize+ /platform:anycpu ($references) (('/out:')+(Join-Path $dist 'CTE2-Patcher.exe')) (Join-Path $root 'src/Patcher.cs')
if($LASTEXITCODE-ne 0){throw 'Patcher compilation failed.'}
if(Test-Path -LiteralPath (Join-Path $root 'tests/EngineTests.cs')){
 & $framework /nologo /utf8output /target:exe /optimize+ /main:Cte2Patcher.EngineTests ($references) (('/out:')+(Join-Path $dist 'EngineTests.exe')) (Join-Path $root 'src/Patcher.cs') (Join-Path $root 'tests/EngineTests.cs')
 if($LASTEXITCODE-ne 0){throw 'Test compilation failed.'}
 & (Join-Path $dist 'EngineTests.exe') (Join-Path $dist 'test-work')
 if($LASTEXITCODE-ne 0){throw 'Patcher engine tests failed.'}
}
Write-Output 'PASS Windows patcher build and engine tests.'
