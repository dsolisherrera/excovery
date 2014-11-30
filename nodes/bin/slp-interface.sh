#!/bin/bash

f=`dirname "$0"`
. ${f}/config.inc

BMF_INTERFACE=bmf0
HOSTNAME=$(hostname)

BMF_addr=$(ifconfig $BMF_INTERFACE | grep "inet Adresse:" | cut -d: -f2 | awk '{ print $1}')
sed "s/bmf/$BMF_addr/g" ${MY_SYS}/etc/slpd/slp.conf >  ${MY_SYS}/etc/slpd/config/slp-$HOSTNAME.conf
