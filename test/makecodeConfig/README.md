# makecodeConfig
- This folder is specifically to allow for the pulling and refreshing of the static makecode files used by the dockerfile 
- this is to avoid runtime deps by not having to install all the packages that makecode uses to compile
- the static files used by the launcher reside at ```src\debian-base1\widgets\makecode\makecode-static```
- if you wish to update this folder and the static file, run the command ```./build.ps1``` when cd'd into this directory ```test\makecodeConfig```
- this will override the existing static files in the base1 folder so be careful if this is used