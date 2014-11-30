#!/bin/bash

if [ -a ${1} ]
then
	/usr/bin/dsh -f $1 -M -c "~/bin/prepare.sh"
else
	/usr/bin/dsh -f <( for i in ${*} ; do echo ${i} ; done ) -M -c "~/bin/prepare.sh"
fi

sleep 60
