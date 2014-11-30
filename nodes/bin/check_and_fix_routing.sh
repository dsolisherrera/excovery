#!/bin/bash
# This is to be run on the nodes
##################################

f=`dirname "$0"`
. ${f}/config.inc

CONFIG_FILE_OLSRD="${MY_SYS}/etc/olsrd_mesh.conf"

WIRELESS_INTERFACE=wlan0
BMF_INTERFACE=bmf0

IF_WLAN=0
IF_BMF=0
DBUS_OK=0
RPC_OK=0
PACKET_TAGGER_OK=0
PACKET_TAGGER_MODULE_OK=0
ROUTES_OK=0

#check for many routes at least 10 are considered connected
ROUTES=$(sudo route | grep wlan2 -c | awk '{print $1}')
if [ $ROUTES -gt 10 ]; then
	ROUTES_OK=1
fi

if [ $ROUTES_OK -eq 0 ]
then
	# RESTART OLSR
	sleep $(($RANDOM % 60))
	sudo killall -q olsrd
	sleep 1
	sudo LD_LIBRARY_PATH=${MY_LIB} ${MY_SBIN}/olsrd -f ${CONFIG_FILE_OLSRD}
	sleep 10

	#check for many routes at least 10 are considered connected
	ROUTES=$(sudo route | grep wlan2 -c | awk '{print $1}')
	if [ $ROUTES -gt 10 ]; then
		ROUTES_OK=1
		exit 0
	fi

	#check for many routes at least 10 are considered connected
	ROUTES=$(sudo route | grep wlan2 -c | awk '{print $1}')
	if [ $ROUTES -gt 10 ]; then
		ROUTES_OK=1
		exit 0
	else
		echo "Routes not OK!"
	fi
fi

