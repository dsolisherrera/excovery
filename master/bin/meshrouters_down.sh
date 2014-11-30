#!/bin/sh

for NODE in $(/testbed/bin/list-hostgroup meshrouters) ; do
	ping -q -c1 -t1 ${NODE} 2>&1 >/dev/null
	if [ $? -ne 0 ] ; then
		echo "${NODE}"
	fi
done
