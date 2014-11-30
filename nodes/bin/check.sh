#!/bin/sh
# This is to be run on the nodes
##################################

WIRELESS_INTERFACE=wlan2
BMF_INTERFACE=bmf0

IF_WLAN=0
IF_BMF=0
DBUS_OK=0
RPC_OK=0
PACKET_TAGGER_OK=0
PACKET_TAGGER_MODULE_OK=0
ROUTES_OK=0

# check for bmf0 up and ip, wlan0/2 up and ip
IF_WLAN=$(sudo ifconfig $WIRELESS_INTERFACE | grep "inet A" -c -i | awk '{print $1}')
IF_BMF=$(sudo ifconfig $BMF_INTERFACE | grep "inet A" -c -i | awk '{print $1}')
# check for dbus
for PID in $(ps aux | grep "dbus-daemon" | grep -v grep | awk '{print $2}')
do
	DBUS_OK=1
done

# check for rpc
for PID in $(ps aux | grep "Node_ManagerRPC.py" | grep -v grep | awk '{print $2}')
do
	RPC_OK=1
done

# check for packet tagger
PACKET_TAGGER_MODULE_OK=$(lsmod | grep nfnetlink_queue -c | awk '{print $1}')
if [ $PACKET_TAGGER_MODULE_OK -gt 0 ]; then
	PACKET_TAGGER_MODULE_OK=1
fi

for PID in $(ps aux | grep "exp_netfilter" | grep -v grep | awk '{print $2}')
do
	PACKET_TAGGER_OK=1
done

#check for many routes at least 10 are considered connected
ROUTES=$(sudo route | grep wlan2 -c | awk '{print $1}')
if [ $ROUTES -gt 10 ]; then
	ROUTES_OK=1
fi

RESULT=$(($IF_WLAN+$IF_BMF+$DBUS_OK+$RPC_OK+$PACKET_TAGGER_OK+$PACKET_TAGGER_MODULE_OK+$ROUTES_OK))

if [ $RESULT -eq 7 ]; then
	exit 0
else
	echo "\tCheck failed: WLan: $IF_WLAN bmf0: $IF_BMF routes: $ROUTES_OK exp_netfiler: $PACKET_TAGGER_OK"
	exit 1
fi


