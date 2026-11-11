python -c '
for p in [
    r"E:\HOST_VSCODE\host-simulator\frontend\src\pages\KeyCeremonyWorkbenchPage.tsx",
    r"E:\HOST_VSCODE\host-simulator\tools\install_lmk_key_mgmt_part3_ui_and_tests.py"
]:
    try:
        txt = open(p, "r", encoding="utf-8").read()
        txt = txt.replace("A0 -> A1", "A0 \u2192 A1").replace("A6 -> A7", "A6 \u2192 A7").replace("A8 -> A9", "A8 \u2192 A9")
        open(p, "w", encoding="utf-8", newline="\n").write(txt)
        print("[OK] Fixed JSX arrows in:", p)
    except FileNotFoundError:
        pass
'