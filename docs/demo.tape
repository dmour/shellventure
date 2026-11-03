# Shellventure demo. Re-record: see docs/Dockerfile.demo
Output docs/demo.gif
Set Shell bash
Set FontSize 18
Set Width 1200
Set Height 720
Set Padding 24
Set Theme "Catppuccin Mocha"
Set TypingSpeed 40ms

Hide
Type "export HOME=/tmp/demo PATH=/vhs/bin:$PATH PS1='$ ' && mkdir -p $HOME && cd $HOME && clear"
Enter
Show

Type "sv play bash"
Sleep 300ms
Enter
Sleep 4s
Type "find . -type f -name '.*'"
Enter
Sleep 2s
Type "find . -type f -name '.*' -exec cat {} +"
Enter
Sleep 2.5s
Type "check $(find . -type f -name '.*' -exec cat {} + | grep KEY= | cut -d= -f2)"
Enter
Sleep 6s
Type "exit"
Enter
Sleep 1s
Type "sv"
Enter
Sleep 3s
Down
Sleep 500ms
Down
Sleep 500ms
Down
Sleep 600ms
Enter
Sleep 4s
