# Wait for one Offline Studio permission dialog with the given title and press Yes.
# Stands in for the user approving a single, displayed request during QA.
param([string]$Title = "Allow web research", [int]$TimeoutSec = 120)
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
$root = [System.Windows.Automation.AutomationElement]::RootElement
$deadline = (Get-Date).AddSeconds($TimeoutSec)
while ((Get-Date) -lt $deadline) {
  $cond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty, $Title)
  $dialog = $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $cond)
  if ($dialog) {
    $yesCond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty, "Yes")
    $yes = $dialog.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $yesCond)
    if ($yes) {
      $text = ($dialog.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition) | ForEach-Object { $_.Current.Name } | Where-Object { $_ }) -join " | "
      ($yes.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)).Invoke()
      Write-Output ("approved: " + $text.Substring(0, [Math]::Min(400, $text.Length)))
      exit 0
    }
  }
  Start-Sleep -Milliseconds 300
}
Write-Output "no dialog"
