# Runs in the VM. Looks for a closed dialog's text anywhere a screen reader could read it from the
# Scores main window: every top-level/owned HWND of the process, the MSAA tree from OBJID_CLIENT and
# OBJID_WINDOW (accChildren, recursive), and the UIA raw view. Prints whatever matches -Find.
param([string]$Find = 'Statistics|headline|News Headlines')
Add-Type -ReferencedAssemblies Accessibility, UIAutomationClient, UIAutomationTypes, WindowsBase @'
using System; using System.Text; using System.Collections.Generic; using System.Runtime.InteropServices; using Accessibility;
using System.Windows.Automation;
public static class P {
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc f, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumChildWindows(IntPtr p, EnumProc f, IntPtr l);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassName(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern IntPtr GetWindow(IntPtr h, uint cmd);
  [DllImport("user32.dll")] public static extern IntPtr GetLastActivePopup(IntPtr h);
  [DllImport("oleacc.dll")] public static extern int AccessibleObjectFromWindow(IntPtr h, int id, ref Guid iid, [MarshalAs(UnmanagedType.Interface)] out object o);
  [DllImport("oleacc.dll")] public static extern int AccessibleChildren(IAccessible p, int start, int count, [Out] object[] kids, out int got);
  public static List<string> Out = new List<string>();
  public static string T(IntPtr h) { var s = new StringBuilder(512); GetWindowText(h, s, 512); return s.ToString(); }
  public static string C(IntPtr h) { var s = new StringBuilder(256); GetClassName(h, s, 256); return s.ToString(); }
  public static List<IntPtr> Windows(uint pid) {
    var r = new List<IntPtr>();
    EnumWindows((h, l) => { uint p; GetWindowThreadProcessId(h, out p); if (p == pid) r.Add(h); return true; }, IntPtr.Zero);
    return r;
  }
  public static int Walk(IntPtr h, int objid, string find) {
    Guid iid = new Guid("618736e0-3c3d-11cf-810c-00aa00389b71"); object o;
    if (AccessibleObjectFromWindow(h, objid, ref iid, out o) != 0 || o == null) return -1;
    var cnt = new int[] { 0 }; Msaa((IAccessible)o, 0, 0, "obj" + objid, find, cnt); return cnt[0];
  }
  public static void Msaa(IAccessible a, object child, int depth, string path, string find, int[] count) {
    if (depth > 25 || count[0] > 4000) return; count[0]++;
    string name = "", role = "", desc = "", val = "";
    try { name = a.get_accName(child) ?? ""; } catch {}
    try { role = Convert.ToString(a.get_accRole(child)); } catch {}
    try { desc = a.get_accDescription(child) ?? ""; } catch {}
    try { val = a.get_accValue(child) ?? ""; } catch {}
    string all = name + " | " + desc + " | " + val;
    if (System.Text.RegularExpressions.Regex.IsMatch(all, find, System.Text.RegularExpressions.RegexOptions.IgnoreCase))
      Out.Add("MSAA match depth=" + depth + " role=" + role + " name='" + name + "' desc='" + desc + "' path=" + path);
    if (!(child is int) || (int)child != 0) return;
    int n = 0; try { n = a.accChildCount; } catch {}
    if (n <= 0) return;
    var kids = new object[n]; int got;
    if (AccessibleChildren(a, 0, n, kids, out got) != 0) return;
    for (int i = 0; i < got; i++) {
      var k = kids[i];
      if (k is IAccessible) Msaa((IAccessible)k, 0, depth + 1, path + "/" + i, find, count);
      else if (k is int) Msaa(a, k, depth + 1, path + "/#" + k, find, count);
    }
  }
}
'@
$app = Get-Process Scores | Where-Object MainWindowHandle -ne 0 | Select-Object -First 1
if (-not $app) { 'no Scores window'; exit 1 }
$main = $app.MainWindowHandle
"main hwnd 0x{0:X} '{1}'  lastActivePopup 0x{2:X}" -f [long]$main, [P]::T($main), [long][P]::GetLastActivePopup($main)
'--- top-level windows of the process:'
foreach ($h in [P]::Windows([uint32]$app.Id)) {
  "  0x{0:X} class={1} visible={2} owner=0x{3:X} title='{4}'" -f [long]$h, [P]::C($h), [P]::IsWindowVisible($h), [long][P]::GetWindow($h, 4), [P]::T($h)
}
foreach ($objid in @(-4, 0)) {   # OBJID_CLIENT, OBJID_WINDOW
  "MSAA walk from objid {0}: {1} objects" -f $objid, [P]::Walk($main, $objid, $Find)
}
[P]::Out | Select-Object -Unique
'--- UIA raw view:'
$root = [System.Windows.Automation.AutomationElement]::FromHandle($main)
$walker = [System.Windows.Automation.TreeWalker]::RawViewWalker
$stack = New-Object System.Collections.Stack; $stack.Push(@($root, 0)); $n = 0
while ($stack.Count -and $n -lt 5000) {
  $e, $d = $stack.Pop(); $n++
  try { $c = $e.Current; $s = "$($c.Name) | $($c.HelpText)"; if ($s -match $Find) { "  UIA match depth=$d $($c.ControlType.ProgrammaticName) name='$($c.Name)' help='$($c.HelpText)' offscreen=$($c.IsOffscreen)" } } catch {}
  $k = $walker.GetFirstChild($e); while ($k) { $stack.Push(@($k, ($d + 1))); $k = $walker.GetNextSibling($k) }
}
"UIA elements: $n"
