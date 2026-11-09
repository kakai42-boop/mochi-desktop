Unicode true
!include "MUI2.nsh"
!include "x64.nsh"
!ifndef BUNDLE
  !error "Define BUNDLE as the assembled Mochi folder"
!endif
!ifndef OUTPUT
  !define OUTPUT "Mochi-Windows11-Setup.exe"
!endif
Name "Mochi pour Windows 11 (préversion)"
OutFile "${OUTPUT}"
InstallDir "$LOCALAPPDATA\Programs\Mochi"
InstallDirRegKey HKCU "Software\MochiDesktopWindows" "InstallDir"
RequestExecutionLevel user
SetCompressor /SOLID lzma
!define MUI_ABORTWARNING
!define MUI_FINISHPAGE_RUN "$INSTDIR\Mochi.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Lancer Mochi"
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "..\..\LICENSE"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "French"

Function .onInit
  ${IfNot} ${RunningX64}
    MessageBox MB_ICONSTOP "Cette version de Mochi nécessite Windows 11 x64."
    Abort
  ${EndIf}
  SetShellVarContext current
FunctionEnd

Section "Mochi" SEC_MAIN
  SetShellVarContext current
  IfFileExists "$INSTDIR\Mochi.exe" 0 install
  ClearErrors
  FileOpen $0 "$INSTDIR\Mochi.exe" a
  IfErrors running
  FileClose $0
  Goto install
  running:
    MessageBox MB_ICONEXCLAMATION "Ferme Mochi avant de relancer cet installateur." /SD IDOK
    SetErrorLevel 2
    Abort
  install:
  SetOutPath "$INSTDIR"
  File /r "${BUNDLE}\*"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  CreateDirectory "$SMPROGRAMS\Mochi"
  CreateShortcut "$SMPROGRAMS\Mochi\Mochi.lnk" "$INSTDIR\Mochi.exe"
  CreateShortcut "$DESKTOP\Mochi.lnk" "$INSTDIR\Mochi.exe"
  WriteRegStr HKCU "Software\MochiDesktopWindows" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\MochiDesktopWindows" "DisplayName" "Mochi pour Windows 11 (préversion)"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\MochiDesktopWindows" "UninstallString" '$\"$INSTDIR\Uninstall.exe$\"'
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\MochiDesktopWindows" "DisplayIcon" "$INSTDIR\Mochi.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\MochiDesktopWindows" "DisplayVersion" "0.4.1-win-preview1"
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\MochiDesktopWindows" "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\MochiDesktopWindows" "NoRepair" 1
SectionEnd

Section "Uninstall"
  SetShellVarContext current
  IfFileExists "$INSTDIR\Mochi.exe" 0 un_install
  ClearErrors
  FileOpen $0 "$INSTDIR\Mochi.exe" a
  IfErrors un_running
  FileClose $0
  Goto un_install
  un_running:
    MessageBox MB_ICONEXCLAMATION "Ferme Mochi avant de le désinstaller." /SD IDOK
    SetErrorLevel 2
    Abort
  un_install:
  Delete "$DESKTOP\Mochi.lnk"
  Delete "$SMPROGRAMS\Mochi\Mochi.lnk"
  RMDir "$SMPROGRAMS\Mochi"
  Delete "$INSTDIR\Mochi.exe"
  Delete "$INSTDIR\bootstrap.py"
  Delete "$INSTDIR\native_checks.py"
  Delete "$INSTDIR\LICENSE"
  Delete "$INSTDIR\LISEZ-MOI.txt"
  Delete "$INSTDIR\build-info.json"
  RMDir /r "$INSTDIR\runtime"
  RMDir /r "$INSTDIR\src"
  RMDir /r "$INSTDIR\assets"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"
  DeleteRegKey HKCU "Software\MochiDesktopWindows"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\MochiDesktopWindows"
  ; User configuration, Bond and Pocket are deliberately retained outside INSTDIR.
SectionEnd
