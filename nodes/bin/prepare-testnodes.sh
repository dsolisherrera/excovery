#!/bin/bash

f=`dirname "$0"`
. ${f}/config.inc

CONFIG_FILE_OLSRD="${MY_SYS}/etc/olsrd_testnodes.conf"

sudo service dbus stop
sudo killall -q iperf

# PREREQUISITES
sudo modprobe ipv6

# STARTUP NECESSARY INTERFACES
for IF in 0 1 2
do
        sudo ifdown wlan${IF}
	sleep 1
	sudo ifconfig wlan${IF} down
	sleep 1
done

sudo ifdown bmf0
sleep 1
sudo ifconfig bmf0 down

sleep $(($RANDOM % 4))
sleep 1

sudo ifup wlan0
sudo ifconfig wlan0 up
sleep 1
sudo iwconfig wlan0 txpower 27

# START DBUS
sudo killall -q dbus-daemon
sudo rm -rf /tmp/dbus*
sudo rm -rf ${MY_SYS}/var/run/dbus/pid
sleep 1
sudo ${MY_BIN}/dbus-daemon --config-file=${MY_SYS}/etc/dbus-1/system.conf
sleep 1

# RESTARTS RPC SERVER SCRIPT ON NODE
for PID in $(ps aux | grep "Node_ManagerRPC.py" | grep -v grep | awk '{print $2}')
do
	sudo kill ${PID}
done
sudo python ${MY_HOME}/Node_ManagerRPC.py 1>/dev/null 2>&1 &
sleep 1

# stop packet ID tagger
for PID in $(ps aux | grep "exp_netfilter" | grep -v grep | awk '{print $2}')
do
	sudo kill ${PID}
done
sleep 1
#remove old drop rules in case there are some
R=$(sudo iptables --list-rules | grep "50698" | sed 's/-A/-D/g')
echo "$R" |
while read i
do
	sudo iptables $i
done

# start packet ID tagger
#remove old drop rules in case there are some
R=$(sudo iptables --list-rules | grep "5353" | sed 's/-A/-D/g')
echo "$R" |
while read i
do
	sudo iptables $i
done
sudo LD_LIBRARY_PATH=${MY_LIB} ${MY_BIN}/exp_netfilter 1>/dev/null 2>&1 &
sudo iptables -A OUTPUT -p udp --dport 5353 -j NFQUEUE
sudo iptables -A OUTPUT -p udp --dport 427 -j NFQUEUE


sleep 1

# START OLSR
sudo killall -q olsrd
sleep $[ ( $RANDOM % 2 )  + 1 ]
sudo LD_LIBRARY_PATH=${MY_LIB} ${MY_SBIN}/olsrd -f ${CONFIG_FILE_OLSRD}
sleep 1

# Prepare avahi
sudo mkdir -p /tmp/avahi_services
sudo mkdir -p /tmp/avahi_run

sudo killall -q avahi-browse
sudo killall -q avahi-publish
sudo killall -q avahi-daemon
sudo killall -q -9 iperf

