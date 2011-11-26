#!/bin/sh
# script to launch GRASS commands

#DEBUG:
#print_args "$@"

# change console title to name of module
if [ "$TERM" = "xterm" ] && [ -n "$BASH" ] ; then
   TITLE="GRASS: $1"
   echo -e "\033]0;${TITLE}\007\c"
fi


# force command line startup mode
GRASS_UI_TERM=1
export GRASS_UI_TERM


# workaround for systems with xterm is setuid/setgid
#  http://grass.itc.it/pipermail/grass5/2004-September/015409.html
PATH=$GRASS_LD_LIBRARY_PATH
export PATH

echo
echo "================================================================="
echo "If you wish to resize the X monitor, do so now. Window size is"
echo "locked while interactive modules are running."
echo "================================================================="
echo

# run command
"$@"

EXIT_VAL=$?
if [ $EXIT_VAL -ne 0 ] ; then
   echo
   echo "ERROR: \"$1\" exited abnormally. Press <enter> to continue."
   read dummy_var
else
   echo
   echo "\"$1\" complete. Press <enter> to continue."
   read dummy_var
fi

exit $EXIT_VAL
