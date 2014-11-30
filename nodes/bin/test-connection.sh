#!/bin/sh

NODE=${1}

if ! (ping -q -c 5 ${NODE}-wlan2 2>/dev/null | grep -q "[1-5] received")
then
	echo "No connection to ${NODE}."
fi
