param(
    [int]$GamePid,
    [ValidateSet('status','shot','key','hold','rel','click','pov','text','focus')]
    [string]$Action = 'status',
    [int[]]$Scan = @(),
    [int]$Milliseconds = 250,
    [int]$Dx = 0,
    [int]$Dy = 0,
    [string]$Text = '',
    [string]$Output = '',
    [int]$Frames = 0
)
$ErrorActionPreference = 'Stop'
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class SkateDrive {
    [StructLayout(LayoutKind.Sequential)] public struct INPUT { public uint type; public UNION data; }
    // INPUT's union must include MOUSEINPUT: keyboard-only unions give the wrong
    // sizeof(INPUT) on x64 and SendInput silently returns zero (ERROR_INVALID_PARAMETER).
    [StructLayout(LayoutKind.Explicit)] public struct UNION {
        [FieldOffset(0)] public KEYBDINPUT keyboard;
        [FieldOffset(0)] public MOUSEINPUT mouse;
    }
    [StructLayout(LayoutKind.Sequential)] public struct KEYBDINPUT {
        public ushort vk, scan; public uint flags, time; public UIntPtr extra;
    }
    [StructLayout(LayoutKind.Sequential)] public struct MOUSEINPUT {
        public int dx,dy; public uint mouseData,flags,time; public UIntPtr extra;
    }
    [StructLayout(LayoutKind.Sequential)] public struct RECT { public int left,top,right,bottom; }
    [StructLayout(LayoutKind.Sequential)] struct LASTINPUTINFO { public uint size,time; }
    [DllImport("user32.dll",SetLastError=true)] static extern uint SendInput(uint count,INPUT[] inputs,int size);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr window);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr window,out RECT rect);
    [DllImport("user32.dll")] static extern bool GetLastInputInfo(ref LASTINPUTINFO info);
    [DllImport("user32.dll")] static extern short VkKeyScan(char value);
    [DllImport("user32.dll")] static extern short VkKeyScanEx(char value,IntPtr layout);
    [DllImport("user32.dll")] static extern IntPtr LoadKeyboardLayout(string name,uint flags);
    [DllImport("user32.dll")] static extern IntPtr GetKeyboardLayout(uint thread);
    [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr window,IntPtr process);
    [DllImport("user32.dll")] static extern bool PostMessage(IntPtr window,uint message,IntPtr wParam,IntPtr lParam);
    [DllImport("user32.dll")] static extern uint MapVirtualKey(uint value,uint map);
    public static uint IdleSeconds() { var i=new LASTINPUTINFO();i.size=(uint)Marshal.SizeOf(i);GetLastInputInfo(ref i);return ((uint)Environment.TickCount-i.time)/1000; }
    public static int InputSize() { return Marshal.SizeOf(typeof(INPUT)); }
    static void Send(INPUT value) {
        uint sent=SendInput(1,new INPUT[]{value},InputSize());
        if(sent!=1) throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error(),"SendInput sent "+sent+" events; INPUT size="+InputSize());
    }
    public static void Key(ushort scan,bool down) {
        var i=new INPUT();i.type=1;i.data.keyboard.scan=scan;i.data.keyboard.flags=(uint)(down?8:10);Send(i);
    }
    public static void Mouse(int dx,int dy,uint flags) {
        var i=new INPUT();i.type=0;i.data.mouse.dx=dx;i.data.mouse.dy=dy;i.data.mouse.flags=flags;Send(i);
    }
    static void Character(char value,IntPtr layout) {
        short vk=VkKeyScanEx(value,layout);if(vk==-1)throw new Exception("Cannot type character: "+value);
        bool shift=(vk&0x100)!=0;ushort scan=(ushort)MapVirtualKey((uint)(vk&0xff),0);
        if(shift)Key(42,true);Key(scan,true);System.Threading.Thread.Sleep(25);Key(scan,false);if(shift)Key(42,false);
    }
    public static void Text(IntPtr window,string text) {
        var old=GetKeyboardLayout(GetWindowThreadProcessId(window,IntPtr.Zero));
        var english=LoadKeyboardLayout("00000409",0);
        try {
            PostMessage(window,0x50,IntPtr.Zero,english);System.Threading.Thread.Sleep(100);
            foreach(char value in text) {
                if(GetForegroundWindow()!=window)throw new Exception("Game lost foreground while typing");
                Character(value,english);
            }
            System.Threading.Thread.Sleep(100);
        } finally { PostMessage(window,0x50,IntPtr.Zero,old); }
    }
}
'@
function Assert-Game {
    $script:gameProcess = Get-Process -Id $GamePid -ErrorAction Stop
    if ($script:gameProcess.ProcessName -ne 'FalloutNV') { throw "PID $GamePid is not FalloutNV" }
    $script:gameProcess.Refresh()
    if ($script:gameProcess.MainWindowHandle -eq 0) { throw 'FalloutNV has no window' }
    if ([SkateDrive]::GetForegroundWindow() -ne $script:gameProcess.MainWindowHandle) { throw 'FalloutNV is not foreground; input stopped' }
}
function Save-Shot([string]$Path) {
    Assert-Game
    Add-Type -AssemblyName System.Drawing
    $rect = New-Object SkateDrive+RECT
    [SkateDrive]::GetWindowRect($script:gameProcess.MainWindowHandle,[ref]$rect) | Out-Null
    $width=$rect.right-$rect.left; $height=$rect.bottom-$rect.top
    $bitmap=New-Object Drawing.Bitmap $width,$height
    $graphics=[Drawing.Graphics]::FromImage($bitmap)
    try {
        $graphics.CopyFromScreen($rect.left,$rect.top,0,0,[Drawing.Size]::new($width,$height))
        $bitmap.Save($Path,[Drawing.Imaging.ImageFormat]::Png)
    } finally { $graphics.Dispose(); $bitmap.Dispose() }
    Write-Output "SHOT=$Path"
}
if ($Action -eq 'status') {
    Get-Process FalloutNV,ModOrganizer -ErrorAction SilentlyContinue | Select-Object Id,ProcessName,MainWindowHandle,MainWindowTitle
    Write-Output "USER_IDLE_SECONDS=$([SkateDrive]::IdleSeconds()) INPUT_SIZE=$([SkateDrive]::InputSize())"
    exit
}
if ($Action -eq 'focus') {
    $p=Get-Process -Id $GamePid -ErrorAction Stop
    if ($p.ProcessName -ne 'FalloutNV') { throw 'Wrong process' }
    [SkateDrive]::SetForegroundWindow($p.MainWindowHandle) | Out-Null
    Start-Sleep -Milliseconds 300
}
Assert-Game
switch ($Action) {
    'shot' { Save-Shot $Output }
    'key' {
        foreach($s in $Scan) {
            Assert-Game; [SkateDrive]::Key($s,$true)
            try { Start-Sleep -Milliseconds $Milliseconds } finally { [SkateDrive]::Key($s,$false) }
        }
    }
    'hold' {
        try {
            foreach($s in $Scan) { Assert-Game; [SkateDrive]::Key($s,$true) }
            if($Frames -gt 0) {
                for($i=0;$i -lt $Frames;$i++) {
                    Start-Sleep -Milliseconds ([int]($Milliseconds/$Frames))
                    Save-Shot ("{0}_{1:D2}.png" -f $Output,$i)
                }
            } else { Start-Sleep -Milliseconds $Milliseconds }
        } finally { foreach($s in $Scan) { [SkateDrive]::Key($s,$false) } }
    }
    'rel' { [SkateDrive]::Mouse($Dx,$Dy,1) }
    'click' {
        [SkateDrive]::Mouse(0,0,2)
        try { Start-Sleep -Milliseconds 100 } finally { [SkateDrive]::Mouse(0,0,4) }
    }
    # Active MO2 profile maps POV to middle mouse. F is not the POV key here;
    # Tab opens Pip-Boy. Verify the visible scene after toggling, before testing.
    'pov' {
        [SkateDrive]::Mouse(0,0,32)
        try { Start-Sleep -Milliseconds 180 } finally { [SkateDrive]::Mouse(0,0,64) }
        Start-Sleep -Milliseconds 500
    }
    'text' { [SkateDrive]::Text($script:gameProcess.MainWindowHandle,$Text) }
}
Write-Output "DONE=$Action PID=$GamePid INPUT_SIZE=$([SkateDrive]::InputSize())"
