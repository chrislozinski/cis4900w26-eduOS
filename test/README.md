# Docker Desktop Dev Environment - Documentation
## This folder is to experiment with arch and debian desktop enviroments on docker for windows. below is an explanation of each

## Debian - debootstrap
To build the debian image using the dockerfile in the debian folder, you run this command 
- docker build -t debian-i3 .

Then when going to run the docker container from this image map the RDC localhost port to the port on the image just put in : 
- 3389
into the port setting 

To login, the hardcoded username and password are : 
- testuser
- 1234

If theres a black screen, the following shortcuts will work: 
- Alt + d:  opens dmenu at the top of your screen. type the name of a program, like xterm or python3, and press enter to launch
- Alt + Enter: this opens an xterm window. if you used alt+d before to open another tab you'll see i3 automatically tile both of them side by side
- Alt + Shift + q: this closes your focused window, which is the one with the blue border
- Alt + j or k or l or ;  : this switches your focus window, each is to move left, down, up, right, respectively 
- Alt + Shift + e: prompts you for exiting i3 and logging out.


## Arch
To build the Arch image using the Dockerfile in the Arch folder, run:
- docker build -t arch-i3 .

then run the container the same way as before, mapping the port 3389 on your host to 3389 in the container.

Login
The hardcoded username and password are:
- Username: testuser
- Password: test

