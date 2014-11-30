#!/bin/bash

f=`dirname "$0"`
. ${f}/config.inc

CONFIG_FILE_OLSRD="${MY_SYS}/etc/olsrd_testnodes.conf"

#remove old drop rules in case there are some
R=$(sudo iptables --list-rules | grep "50698" | sed 's/-A/-D/g')
echo "$R" |
while read i
do
	sudo iptables $i
done

# RESTARTS RPC SERVER SCRIPT ON NODE
for PID in $(ps aux | grep "Node_ManagerRPC.py" | grep -v grep | awk '{print $2}')
do
	sudo kill ${PID}
done
sudo python ${MY_HOME}/Node_ManagerRPC.py 1>/dev/null 2>&1 &
sleep 1

sudo killall -9 iperf
sudo killall -9 tshark
sudo killall -9 dumpcap
