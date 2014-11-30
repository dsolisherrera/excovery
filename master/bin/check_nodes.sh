#!/bin/bash

if [ -a ${1} ]
then
	/usr/bin/dsh -f ${1} -M -c "~/bin/check.sh"
else
	/usr/bin/dsh -f <( for i in ${*} ; do echo ${i} ; done ) -M -c "~/bin/check.sh"
fi

sleep 15
