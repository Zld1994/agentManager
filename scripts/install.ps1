# agentManager installer for Windows PowerShell
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path))
python scripts/install.py @args
