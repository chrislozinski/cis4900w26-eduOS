# This is the current working directory of files.

## debian-base1 - debian using debootstrap

To build the debian image and container using the dockerfile in the debian-base1 folder, you run this command 
- docker-compose up -d --build

To login, the hardcoded username and password are : 
- testuser
- 1234

The following shortcuts work: 
- Alt + d: opens dmenu at the top of your screen. type the name of a program, like xterm or python3, and press enter to launch
- Alt + Enter: this opens an xterm window. if you used alt+d before to open another tab you'll see i3 automatically tile both of them side by side
- Alt + Shift + q: this closes your focused window, which is the one with the blue border
- Alt + Shift + e: prompts you for exiting i3 and logging out.


## IMPORTANT: MAKE SURE THE IP-CONFIG FILE IS LF FORMAT OR ELSE IT WONT WORK!
