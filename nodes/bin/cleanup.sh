#!/bin/bash
#
#
# clean up after experimentor
#
f=`dirname "$0"`
. ${f}/config.inc

# stop packet ID tagger
for PID in $(ps aux | grep "exp_netfilter" | grep -v grep | awk '{print $2}')
do
	sudo kill ${PID}
done
#remove old drop rules in case there are some
R=$(sudo iptables --list-rules | grep "5353" | sed 's/-A/-D/g')
echo "$R" |
while read i
do
	sudo iptables $i
done
#remove old drop rules in case there are some
R=$(sudo iptables --list-rules | grep "50698" | sed 's/-A/-D/g')
echo "$R" |
while read i
do
	sudo iptables $i
done

sudo modprobe -r nfnetlink_queue


# clean up old programs that might interfere
sudo killall -q avahi-browse
sudo killall -q avahi-publish
sudo killall -q avahi-daemon
sudo killall -q -9 iperf
sudo killall -q olsrd
sudo killall -q dbus-daemon
sleep 1
#stop Node_Manager
for PID in $(ps aux | grep "Node_ManagerRPC.py" | grep -v grep | awk '{print $2}')
do
	sudo kill ${PID}
done

sudo ifdown bmf0
sudo ifconfig bmf0 down

sudo ifdown wlan0
sudo ifconfig wlan0 down

sudo service dbus stop
sudo service dbus start
