param(
  [string]$Target = "auto",
  [ValidateSet("rules", "skill")]
  [string]$Mode = "skill",
  [string]$GlobalSkillsDir = "",
  [string]$SkillsDir = "",
  [string]$SkillDirPreset = "",
  [switch]$Overwrite,
  [switch]$Apply
)
$ErrorActionPreference = "Stop"
$DryRun = -not $Apply
$ProjectRoot = (Get-Location).Path
$Tmp = New-Item -ItemType Directory -Force -Path ([System.IO.Path]::Combine([System.IO.Path]::GetTempPath(), "mre-install-" + [System.Guid]::NewGuid().ToString()))
try {
  $Url = "https://github.com/wenxi96/model-regression-eval/archive/refs/heads/main.zip"
  if (-not $Url) { throw "No source URL embedded. Clone the repository and run python -m model_regression_eval.cli skill install-skill." }
  $Zip = Join-Path $Tmp "source.zip"
  Invoke-WebRequest -Uri $Url -OutFile $Zip
  Expand-Archive -Path $Zip -DestinationPath (Join-Path $Tmp "source") -Force
  $Project = Get-ChildItem -Path (Join-Path $Tmp "source") -Filter pyproject.toml -Recurse | Where-Object { Test-Path (Join-Path $_.DirectoryName "model_regression_eval") } | Select-Object -First 1
  if (-not $Project) { throw "could not locate project root in archive" }
  Push-Location $Project.DirectoryName
  $Subcommand = if ($Mode -eq "skill") { "install-skill" } else { "install" }
  $Args = @("-m", "model_regression_eval.cli", "skill", $Subcommand, "--target", $Target, "--project-root", $ProjectRoot)
  if ($Mode -eq "skill") {
    if ($GlobalSkillsDir) { $Args += @("--global-skills-dir", $GlobalSkillsDir) }
    if ($SkillsDir) { $Args += @("--skills-dir", $SkillsDir) }
    if ($SkillDirPreset) { $Args += @("--skill-dir-preset", $SkillDirPreset) }
  }
  if ($DryRun) { $Args += "--dry-run" }
  if ($Overwrite) { $Args += "--overwrite" }
  python @Args
  Pop-Location
} finally {
  Remove-Item -Recurse -Force $Tmp -ErrorAction SilentlyContinue
}
