#!/bin/bash

#check for many routes at least 10 are considered connected
ROUTES=$(sudo route | grep wlan2 -c | awk '{print $1}')
if [ $ROUTES -gt 10 ]; then
	echo "ok" > $1
else
	echo "fail" > $1
fi
